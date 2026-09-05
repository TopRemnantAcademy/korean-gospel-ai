"""歌曲生成路由：提交任务 + 轮询状态 + 我的作品 + 续写/翻唱/Remix。

生成异步：提交后建 Song(pending)，后台任务调编排层（Suno API），
轮询直到完成，写回 audio_url 等。前端轮询 GET /api/songs/{id}。
任务类型（task）对齐 Suno 真实产品能力：generate/custom/extend/cover/remix。
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.models import Song, SyncRecord, User
import app.moderation as moderation
from app.orchestrator.base import GenerateRequest
from app.orchestrator.client import generate, get_orchestrator
from app.orchestrator.selection import (
    resolve_engine,
    resolve_cost_cny,
    resolve_price_cny,
    compute_margin_cny,
    resolve_engine_chain,
    resolve_tier_model_version,
)
from app.quota import enforce_generate_limits, daily_generated_count
from app.entitlements import (
    resolve_limits,
    can_play_full,
    can_download,
    preview_seconds,
)
from app.routers.auth import get_current_user
from app.schemas import (
    GenerateReq, GenerateResp, SongOut, SpawnReq,
    CropReq, SpeedReq, AlignedLyricsReq, SoundReq, UploadReq, UploadResp,
)

router = APIRouter(prefix="/api/songs", tags=["songs"])


class VisibilityReq(BaseModel):
    """PATCH /{song_id} 修改公开状态。"""

    is_public: bool


def _to_out(song: Song, user: Optional[User] = None) -> SongOut:
    """序列化歌曲。未订阅者只拿到「试听片段」链接，完整音频 URL 不泄露。

    ⚠ 실패-닫힘(fail-closed): 프리뷰 자산이 아직 없으면 미구독자에게는 audio_url=None 을 준다.
      완곡 URL 로 되돌리면 게이트가 무력화되므로 절대 그렇게 하지 않는다
      (프리뷰 생성 실패 시에만 발생 — 그 땐 재생 불가가 정답).
    """
    user_id = user.id if user is not None else None
    full = can_play_full(user)
    audio = (song.audio_url or None) if full else (song.preview_audio_url or None)
    return SongOut(
        id=song.id,
        title=song.title,
        custom_id=song.custom_id or None,
        style=song.style or None,
        prompt=song.prompt or None,
        lyric=song.lyric or None,
        audio_url=audio,
        cover_url=song.cover_url or None,
        status=song.status,
        make_instrumental=song.make_instrumental,
        task_type=song.task_type,
        model_version=song.model_version or None,
        duration=song.duration,
        parent_song_id=song.parent_song_id,
        moderation_status=song.moderation_status,
        is_public=song.is_public,
        play_count=song.play_count,
        is_owner=bool(user_id is not None and song.user_id == user_id),
        content_category=song.content_category or None,
        cost_cny=float(song.cost_cny) if song.cost_cny is not None else None,
        preview_audio_url=song.preview_audio_url or None,
        preview_seconds=song.preview_seconds,
        can_play_full=full,
        can_download=can_download(user),
        created_at=song.created_at.isoformat() if song.created_at else "",
    )


def _create_song(req: GenerateReq, user: User, db: Session) -> Song:
    # 单位经济核算：成本=引擎(模型)单价×首数；价格=适用套餐标准价；毛利=价格-成本
    engine_name = resolve_engine(db, req.content_category)
    n = int(settings.mureka_n or 1) if engine_name == "mureka" else 1  # Mureka 按首计费
    tier_key = user.tier_key
    # 모델 결정 우선순위: ① 사용자가 명시한 model_version ② 티어 바인딩 모델(lite→mureka-7.6) ③ 엔진 기본
    # ⚠ ② 가 빠지면 저가 티어가 "가격만 낮고 원가는 그대로" → 마진 음수(절감 효과 0).
    model_version = (req.model_version or "").strip() or resolve_tier_model_version(db, tier_key)
    cost = resolve_cost_cny(db, req.content_category, n=n, model_version=model_version or None)
    price = resolve_price_cny(db, tier_key, req.content_category)
    margin = compute_margin_cny(price, cost)
    song = Song(
        user_id=user.id,
        title=req.title or "未命名",
        style=req.style or "",
        prompt=req.prompt or "",
        lyric=req.lyric or "",
        make_instrumental=req.make_instrumental,
        status="pending",
        task_type=req.task,
        model_version=model_version,
        parent_song_id=req.source_song_id,
        is_public=bool(req.is_public),
        vocal_gender=req.vocal_gender,
        clip_seconds=req.clip_seconds,
        content_category=req.content_category or "general",
        engine_name=engine_name,
        cost_cny=cost,
        price_cny=price,
        margin_cny=margin,
        tier_key=tier_key,
    )
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


def _apply_postprocess(remote_url: str) -> str:
    """下载远程音频 -> 本地后处理 -> 回传，返回新 URL；任意失败返回原 URL。"""
    import logging
    import os

    from app import postprocess
    from app.storage.s3 import download_to_temp, upload

    try:
        local_in = download_to_temp(remote_url)
        local_out = local_in + ".pp.wav"
        postprocess.run_postprocess(local_in, local_out)
        key = f"postprocess/{os.path.basename(local_out)}"
        return upload(local_out, key)
    except Exception as e:  # 后处理非关键路径，失败保留原音频
        logging.getLogger(__name__).warning("音频后处理跳过（保留原音频）：%s", e)
        return remote_url


def _preview_cache_dir() -> str:
    """试听片段本地缓存目录（相对路径按 CWD=backend 解析）。"""
    import os

    d = settings.preview_cache_dir or ".cache/preview"
    return d if os.path.isabs(d) else os.path.join(os.getcwd(), d)


def _preview_cache_path(song_id: int) -> str:
    import os

    return os.path.join(_preview_cache_dir(), f"{int(song_id)}.preview.mp3")


def _store_preview_local(song_id: int, src_path: str) -> str:
    """把裁剪好的片段放进本地缓存，返回可访问的端点路径（幂等：重复覆盖无副作用）。"""
    import os
    import shutil

    dst = _preview_cache_path(song_id)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src_path, dst)
    return f"/api/songs/{song_id}/preview"


def _make_preview(remote_url: str, song_id: int) -> str:
    """완곡 URL → 앞 N초만 자른「试听片段」을 저장하고 그 URL 을 반환.

    저장 위치는 2가지:
      · storage_* 설정됨  → 객체 스토리지에 업로드(운영 권장, CDN 경유)
      · 미설정            → 로컬 캐시 + GET /api/songs/{id}/preview 로按需 생성·서빙
        (⚠ 이 폴백이 없으면 미구독자는 프리뷰 생성 실패로 "아무 소리도 못 듣게" 된다.
          게이트가 기능정지로 변하므로 절대 빼먹지 말 것.)

    실패 시 빈 문자열. 이때 미구독자는 `_to_out` 에서 audio_url=None 이 되어 재생 불가
    (fail-closed) — 완곡으로 폴백하면 게이트가 무력화되므로 절대 그렇게 하지 않는다.
    """
    import logging
    import os

    from app import postprocess
    from app.storage.s3 import download_to_temp, upload, is_configured

    try:
        local_in = download_to_temp(
            remote_url,
            timeout_total=settings.preview_fetch_timeout,
            max_bytes=int(settings.preview_fetch_max_mb * 1024 * 1024),
        )
        local_out = local_in + ".preview.mp3"
        postprocess.trim(local_in, local_out, preview_seconds())
        if is_configured():
            key = f"preview/{song_id}_{os.path.basename(local_out)}"
            return upload(local_out, key)
        return _store_preview_local(song_id, local_out)
    except Exception as e:  # 프리뷰 실패는 게이트 유지로 처리(완곡 노출 금지)
        logging.getLogger(__name__).warning("试听片段生成失败（未订阅者将无法播放）：%s", e)
        return ""


async def _process_song(song_id: int):
    db = SessionLocal()
    song = None
    try:
        song = db.get(Song, song_id)
        if not song:
            return
        song.status = "processing"
        db.commit()

        # 引擎由下方 generate(req, song.engine_name) 按后台路由构造
        continue_id = None
        if song.task_type in ("extend", "cover", "remix") and song.parent_song_id:
            parent = db.get(Song, song.parent_song_id)
            if parent:
                # 续写/翻唱基于父歌 custom_id（UUID）；无则回退 external_id（task_id）
                continue_id = parent.custom_id or parent.external_id
        req = GenerateRequest(
            prompt=song.prompt or None,
            style=song.style or None,
            lyric=song.lyric or None,
            title=song.title,
            vocal_gender=song.vocal_gender,
            make_instrumental=song.make_instrumental,
            task=song.task_type,
            model_version=song.model_version or None,
            continue_song_id=continue_id,
            clip_seconds=song.clip_seconds,
        )
        try:
            # P2 Failover：按内容分类构造引擎链（首要 + 其余已启用按优先级），一引擎拦截即换下一引擎
            chain = resolve_engine_chain(db, song.content_category)
            result = await generate(req, engine_chain=chain)
        except ValueError as e:
            song.status = "failed"
            song.moderation_note = f"引擎未接入: {e}"
            db.commit()
            return
        song.status = result.status
        song.external_id = result.external_id
        song.custom_id = result.custom_id or ""
        song.audio_url = result.audio_url or ""
        song.cover_url = result.cover_url or ""
        song.lyric = result.lyric or song.lyric
        song.title = result.title or song.title
        song.model_version = result.model_version or song.model_version
        song.duration = result.duration or 0
        # 音频后处理（F1/F2/F3/F4）：下载 -> 本地处理 -> 回传。默认关；失败不影响主流程。
        if settings.enable_audio_postprocess and song.audio_url:
            # [D32] 동기 블로킹 후처리(ffmpeg + 파일 IO) 를 이벤트루프 밖 스레드풀로.
            # 단일 호스트 공존 1대에서 블라스트 레이디어스 확대 차단(§21.3).
            song.audio_url = await run_in_threadpool(_apply_postprocess, song.audio_url)
        # 프리미엄 게이트: 완곡은 그대로 두고, 미구독자용「앞 N초」프리뷰를 별도 자산으로 생성.
        # [D32] 과 동일하게 ffmpeg+IO 는 스레드풀로(이벤트루프 블로킹 방지).
        if (
            settings.enable_preview_clip
            and result.status == "completed"
            and song.audio_url
            and not song.preview_audio_url
        ):
            preview_url = await run_in_threadpool(_make_preview, song.audio_url, song.id)
            if preview_url:
                song.preview_audio_url = preview_url
                song.preview_seconds = preview_seconds()
        # P3 音频机审：生成完成后对最终音频做内容审核；未通过标记 rejected。
        # 仅在 pending（未人工审核）时生效，不覆盖 admin 已 approved/rejected。
        if (
            result.status == "completed"
            and settings.enable_audio_moderation
            and song.moderation_status == "pending"
            and song.audio_url
            and not moderation.moderate_audio(song.audio_url)
        ):
            song.moderation_status = "rejected"
        # E4 自动流转：文本已通过 check_lyric（generate_song / _moderate_spawn），
        # 音频通过（或未启用音频审核）→ 生成成功后自动置已审核。不覆盖 admin 已审核结论。
        # [D33] 심의가 설정된 경로일 때만 자동 approved 로 승격.
        # enable_moderation=False(미설정) 면 미심의 상태(pending) 로 유지 —
        # explore/sync 가 명시적 approved 만 통과시키므로 무심의 노출을 막는다.
        elif (
            result.status == "completed"
            and settings.enable_moderation
            and song.moderation_status == "pending"
        ):
            song.moderation_status = "approved"
        # P2 明确审核提示：最终 failed 且判定为内容拦截 → 标记 rejected + 原因（前端可见）
        if song.status == "failed" and getattr(result, "moderation_blocked", False):
            song.moderation_status = "rejected"
            if result.moderation_note:
                song.moderation_note = result.moderation_note
        db.commit()
    except Exception:
        if song is not None:
            song.status = "failed"
            db.commit()
    finally:
        db.close()


def _spawn_from_parent(
    song_id: int, task: str, body: SpawnReq, db: Session, user: User,
    require_owner: bool = False,
) -> Song:
    parent = db.get(Song, song_id)
    if not parent:
        raise HTTPException(status_code=404, detail="源歌曲不存在")
    if require_owner and parent.user_id != user.id:
        raise HTTPException(status_code=404, detail="源歌曲不存在")
    if not require_owner and not parent.is_public and parent.user_id != user.id:
        raise HTTPException(status_code=403, detail="仅可对公开歌曲或自己的歌曲翻唱或 Remix")
    if parent.status != "completed":
        raise HTTPException(status_code=400, detail="源歌曲尚未生成完成")
    req = GenerateReq(
        task=task,
        source_song_id=parent.id,
        prompt=body.prompt if body.prompt is not None else parent.prompt,
        style=body.style if body.style is not None else parent.style,
        lyric=body.lyric if body.lyric is not None else "",
        title=body.title or f"{parent.title} · {task}",
        make_instrumental=body.make_instrumental
        if body.make_instrumental is not None
        else parent.make_instrumental,
        model_version=body.model_version,
        clip_seconds=body.clip_seconds,
        content_category=parent.content_category,
    )
    return _create_song(req, user, db)


def _moderate_spawn(body: SpawnReq) -> None:
    """续写/翻唱机审：仅校验本次新提供的内容（沿用父歌已审内容时不拦截）。"""
    if not settings.enable_moderation:
        return
    text = body.lyric or body.prompt or ""
    if text and not moderation.check_lyric(text):
        raise HTTPException(status_code=400, detail="内容未通过审核，请修改后重试")


@router.post("/generate", response_model=GenerateResp)
async def generate_song(
    req: GenerateReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 生成前置：突发限流 + 每日配额（429 / 402）
    enforce_generate_limits(user, db)
    # 歌词机审（MVP：敏感词；生产接 ASR + 审核模型，见 PROMPT.md）
    text_to_check = req.lyric or req.prompt or ""
    if settings.enable_moderation and not moderation.check_lyric(text_to_check):
        raise HTTPException(status_code=400, detail="内容未通过审核，请修改后重试")

    song = _create_song(req, user, db)
    bg.add_task(_process_song, song.id)
    return GenerateResp(song_id=song.id, status=song.status)


@router.post("/{song_id}/extend", response_model=GenerateResp)
async def extend_song(
    song_id: int,
    body: SpawnReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_generate_limits(user, db)
    _moderate_spawn(body)
    song = _spawn_from_parent(song_id, "extend", body, db, user, require_owner=True)
    bg.add_task(_process_song, song.id)
    return GenerateResp(song_id=song.id, status=song.status)


@router.post("/{song_id}/cover", response_model=GenerateResp)
async def cover_song(
    song_id: int,
    body: SpawnReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_generate_limits(user, db)
    _moderate_spawn(body)
    song = _spawn_from_parent(song_id, "cover", body, db, user, require_owner=False)
    bg.add_task(_process_song, song.id)
    return GenerateResp(song_id=song.id, status=song.status)


@router.post("/{song_id}/remix", response_model=GenerateResp)
async def remix_song(
    song_id: int,
    body: SpawnReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_generate_limits(user, db)
    _moderate_spawn(body)
    song = _spawn_from_parent(song_id, "remix", body, db, user, require_owner=False)
    bg.add_task(_process_song, song.id)
    return GenerateResp(song_id=song.id, status=song.status)


@router.get("/explore", response_model=list[SongOut])
def explore_songs(
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """发现页公开流：已公开 + 已审核通过 + 生成完成，按播放量 / 时间排序。匿名可访问。

    q 为可选关键字，按标题 / 歌词做不区分大小写匹配（参数化 ilike，防注入）。
    """
    filters = [
        Song.is_public.is_(True),
        Song.moderation_status == "approved",
        Song.status == "completed",
    ]
    if q:
        like = f"%{q}%"
        filters.append(or_(Song.title.ilike(like), Song.lyric.ilike(like)))
    rows = (
        db.query(Song)
        .filter(*filters)
        .order_by(Song.play_count.desc(), Song.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_to_out(s) for s in rows]


@router.post("/sound", response_model=GenerateResp)
async def create_sound(
    req: SoundReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_generate_limits(user, db)
    engine_name = settings.music_provider or "mureka"
    cost = resolve_cost_cny(db, None, n=1)
    tier_key = user.tier_key
    price = resolve_price_cny(db, tier_key, None)
    margin = compute_margin_cny(price, cost)
    song = Song(
        user_id=user.id,
        title=req.title,
        style=req.tags or "",
        task_type="sound",
        make_instrumental=True,
        status="pending",
        model_version=req.model_version or "",
        engine_name=engine_name,
        cost_cny=cost,
        price_cny=price,
        margin_cny=margin,
        tier_key=tier_key,
    )
    db.add(song)
    db.commit()
    db.refresh(song)
    bg.add_task(_process_sound, song.id, req)
    return GenerateResp(song_id=song.id, status=song.status)


@router.post("/upload", response_model=UploadResp)
async def upload_audio(
    req: UploadReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传参考音频，返回 custom_id（供 extend/cover 使用）。"""
    provider = get_orchestrator()
    custom_id = await provider.upload(req.audio_url)
    return UploadResp(custom_id=custom_id)


@router.get("/{song_id}", response_model=SongOut)
def get_song(song_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.get(Song, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return _to_out(song, user)


@router.delete("/{song_id}", status_code=200)
def delete_song(song_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除自己的歌曲；子歌血缘解绑（parent_song_id 置 NULL）避免外键悬挂。

    [F5] 删除传播(2026-09-01): 关联 SyncRecord 를 ``revoked`` 로 마킹한다.
    这样 FLOW APP 在 ``GET /api/v1/sync/flow`` 拉取歌单时会排除已删除歌曲
    (list_flow 仅返回 status=="synced")，避免孤儿残留(설계 §11.4).
    """
    song = db.get(Song, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    # [F5] 删除传播 — 关联同步记录标记 revoked
    rec = db.query(SyncRecord).filter_by(song_id=song_id).first()
    if rec:
        rec.status = "revoked"
        db.commit()
    db.query(Song).filter(Song.parent_song_id == song.id).update({Song.parent_song_id: None})
    db.delete(song)
    db.commit()
    return {"detail": "deleted", "id": song_id}


@router.patch("/{song_id}", response_model=SongOut)
def update_visibility(
    song_id: int,
    body: VisibilityReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """生成后切换公开状态（is_public）。仅所有者可改。"""
    song = db.get(Song, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    song.is_public = bool(body.is_public)
    db.commit()
    db.refresh(song)
    return _to_out(song, user)


def _owned_completed(song_id: int, db: Session, user: User) -> Song:
    """取歌曲并校验：存在 + 所有者 + 生成完成。否则抛 404/403/400。"""
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    if song.user_id != user.id:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    if song.status != "completed":
        raise HTTPException(status_code=400, detail="源歌曲尚未生成完成")
    return song


async def _process_post(song_id: int, op: str, **params) -> None:
    """后期处理后台任务：调供应商 op 方法，按操作类型写回结果到原 Song。

    op ∈ crop / speed / whole_song（写回 audio_url）/ aligned_lyrics（写回 lyric）。
    供应商方法不是 MusicProvider 抽象契约，由各实现自行提供（见 orchestrator/*）。
    """
    db = SessionLocal()
    song = None
    try:
        song = db.get(Song, song_id)
        if not song:
            return
        song.status = "processing"
        db.commit()
        provider = get_orchestrator()
        result = await getattr(provider, op)(**params)
        song.status = result.status
        if op in ("crop", "speed", "whole_song"):
            song.audio_url = result.audio_url or song.audio_url
        elif op == "aligned_lyrics":
            song.lyric = result.lyric or song.lyric
        if result.duration:
            song.duration = result.duration
        db.commit()
    except Exception:
        if song is not None:
            song.status = "failed"
            db.commit()
    finally:
        db.close()


async def _process_sound(song_id: int, req: SoundReq) -> None:
    """生成音效后台任务：调供应商 sound 方法，写回新 Song。"""
    db = SessionLocal()
    song = None
    try:
        song = db.get(Song, song_id)
        if not song:
            return
        song.status = "processing"
        db.commit()
        provider = get_orchestrator()
        result = await provider.sound(
            title=req.title,
            tags=req.tags or "",
            mv=req.model_version or "chirp-crow",
            tempo=req.tempo,
            key=req.key,
            loop=req.loop,
        )
        song.status = result.status
        song.audio_url = result.audio_url or ""
        song.custom_id = result.custom_id or ""
        song.model_version = result.model_version or song.model_version
        song.duration = result.duration or 0
        db.commit()
    except Exception:
        if song is not None:
            song.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/{song_id}/crop", response_model=GenerateResp)
async def crop_song(
    song_id: int,
    body: CropReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    song = _owned_completed(song_id, db, user)
    clip_id = song.custom_id or song.external_id
    bg.add_task(_process_post, song.id, "crop", clip_id=clip_id, start_time=body.start_time, end_time=body.end_time)
    return GenerateResp(song_id=song.id, status="processing")


@router.post("/{song_id}/speed", response_model=GenerateResp)
async def speed_song(
    song_id: int,
    body: SpeedReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    song = _owned_completed(song_id, db, user)
    clip_id = song.custom_id or song.external_id
    bg.add_task(_process_post, song.id, "speed", clip_id=clip_id, speed=body.speed)
    return GenerateResp(song_id=song.id, status="processing")


@router.post("/{song_id}/aligned-lyrics", response_model=GenerateResp)
async def aligned_lyrics_song(
    song_id: int,
    body: AlignedLyricsReq,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    song = _owned_completed(song_id, db, user)
    suno_id = song.custom_id or song.external_id
    bg.add_task(_process_post, song.id, "aligned_lyrics", lyrics=body.lyrics, suno_id=suno_id)
    return GenerateResp(song_id=song.id, status="processing")


@router.post("/{song_id}/whole-song", response_model=GenerateResp)
async def whole_song_endpoint(
    song_id: int,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    song = _owned_completed(song_id, db, user)
    clip_id = song.custom_id or song.external_id
    bg.add_task(_process_post, song.id, "whole_song", clip_id=clip_id)
    return GenerateResp(song_id=song.id, status="processing")





@router.get("", response_model=list[SongOut])
def list_songs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    songs = (
        db.query(Song)
        .filter(Song.user_id == user.id)
        .order_by(Song.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_to_out(s, user) for s in songs]


@router.get("/me/billing")
def my_billing(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사용자 본인 사용량 원장 + 단위경제 요약(GAP-005).

    Req6 에서 관리자용(config_dashboard/stats)으로만 집계했던
    cost_cny/price_cny/margin_cny 를 사용자도 **자기 곡 범위**에서 확인할 수 있게 한다.
    (공개 SongOut 에는 미노출 — 타인 곡 경제정보 유출 방지)
    """
    songs = db.query(Song).filter(Song.user_id == user.id).all()
    total_cost = sum(float(s.cost_cny or 0) for s in songs)
    total_price = sum(float(s.price_cny or 0) for s in songs)
    total_margin = round(total_price - total_cost, 4)
    daily_used = daily_generated_count(db, user.id)
    return {
        "tier_key": resolve_limits(db, user.tier_key)["tier_key"],
        "total_songs": len(songs),
        "total_cost_cny": round(total_cost, 4),
        "total_revenue_cny": round(total_price, 4),
        "total_margin_cny": total_margin,
        "daily_quota_used": daily_used,
        "daily_quota_limit": resolve_limits(db, user.tier_key)["daily_quota"],
        "recent": [
            {
                "id": s.id,
                "title": s.title,
                "status": s.status,
                "cost_cny": float(s.cost_cny or 0),
                "price_cny": float(s.price_cny or 0),
                "margin_cny": float(s.margin_cny or 0),
                "tier_key": s.tier_key,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sorted(songs, key=lambda x: (x.created_at is None, x.created_at or ""), reverse=True)[:20]
        ],
    }


@router.post("/{song_id}/play", response_model=SongOut)
def play_song(
    song_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """播放计数 +1（供前端播放时调用）。自己或已公开的歌均可计数。"""
    song = db.get(Song, song_id)
    if not song or (song.user_id != user.id and not song.is_public):
        raise HTTPException(status_code=404, detail="歌曲不存在")
    song.play_count = (song.play_count or 0) + 1
    db.commit()
    db.refresh(song)
    return _to_out(song, user)


@router.get("/{song_id}/download")
def download_song(
    song_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """订阅者下载完整音频；未订阅 403。

    S3 公开 URL 直接重定向无法设置 Content-Disposition（浏览器会「播放」而非「下载」），
    故后端取回临时文件后以 attachment 下发（代价：占用本机带宽，MVP 可接受）。
    ⚠ 这里给的是**完整音频**；未订阅者在 `_to_out` 侧连试听片段以外的链接都拿不到。
    """
    from fastapi.responses import FileResponse

    from app.storage.s3 import download_to_temp

    song = db.get(Song, song_id)
    if not song or (song.user_id != user.id and not song.is_public):
        raise HTTPException(status_code=404, detail="歌曲不存在")
    if not can_download(user):
        raise HTTPException(status_code=403, detail="订阅后可下载完整音频")
    if not song.audio_url:
        raise HTTPException(status_code=404, detail="音频不可用")
    try:
        local = download_to_temp(song.audio_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail="音频下载失败") from e
    filename = f"{(song.title or '').strip() or 'song'}.mp3"
    return FileResponse(local, media_type="audio/mpeg", filename=filename)


@router.get("/{song_id}/preview")
def preview_audio(
    song_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """未订阅者的试听片段（前 N 秒）——对象存储未配置时的按需生成回退。

    · 命中本地缓存直接返回；未命中则下载完整音频 → ffmpeg 裁剪 → 入缓存 → 返回。
    · [SEC] 어떤 경우에도 완곡을 스트리밍하지 않는다(길이 = preview_seconds 로 고정).
    · [SEC] 소유자 또는 공개 곡만 접근 가능(미소유·비공개 → 404, 존재 여부 노출 금지).
    · 생성 실패 시 404(fail-closed) — 완곡으로 폴백하지 않는다.
    · ⚠ 인증이 필요하므로 <audio src> 로 직접 걸 수 없다 → 프런트는 fetch+blob 으로 재생.
    """
    import logging
    import os

    from fastapi.responses import FileResponse

    from app import postprocess
    from app.storage.s3 import download_to_temp

    song = db.get(Song, song_id)
    if not song or (song.user_id != user.id and not song.is_public):
        raise HTTPException(status_code=404, detail="试听片段不可用")
    if not song.audio_url:
        raise HTTPException(status_code=404, detail="试听片段不可用")

    cached = _preview_cache_path(song_id)
    if os.path.exists(cached):
        return FileResponse(cached, media_type="audio/mpeg", filename=f"{song_id}_preview.mp3")

    try:
        # [REL] 사용자 대면 경로: 업스트림이 느리면 요청이 무한정 붙잡히므로 전체 상한을 건다
        #       (httpx timeout 은 읽기 간 유휴 기준 → "천천히 꾸준히" 흐르는 응답은 못 막음).
        local_in = download_to_temp(
            song.audio_url,
            timeout_total=settings.preview_fetch_timeout,
            max_bytes=int(settings.preview_fetch_max_mb * 1024 * 1024),
        )
        local_out = local_in + ".preview.mp3"
        postprocess.trim(local_in, local_out, preview_seconds())
        _store_preview_local(song_id, local_out)
    except Exception as e:  # fail-closed: 완곡 대신 404
        logging.getLogger(__name__).warning("试听片段按需生成失败（song_id=%s）：%s", song_id, e)
        raise HTTPException(status_code=404, detail="试听片段生成失败") from e
    return FileResponse(cached, media_type="audio/mpeg", filename=f"{song_id}_preview.mp3")
