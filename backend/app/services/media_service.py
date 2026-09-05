"""업로드된 오디오 미디어 관리 서비스 (찬양 음원 / 설교 음성).

관리자가 파일을 업로드하면 data/media/{category}/ 에 저장하고 메타데이터를 DB에 보관.
모바일 앱은 /mobile/media 카탈로그로 목록을 받고 /mobile/media/{id}/stream 으로 스트리밍.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from ..config import settings
from ..db import get_session
from ..models.orm import MediaAsset

log = logging.getLogger("gospel-api.media")

MEDIA_DIR = settings.root_dir / "data" / "media"

# 스트리밍 지원 오디오 확장자 (선호 순)
_ALLOWED_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")
_MIME_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}
# 파일명에 허용할 문자 (경로 순회 방지 — 한글/영숫자/점/밑줄/하이픈만)
_SAFE_NAME_RE = re.compile(r"^[가-힣A-Za-z0-9._-]+$")


def _category_dir(category: str) -> Path:
    d = MEDIA_DIR / category
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_stored_name(original: str, directory: Path) -> str:
    """원본 파일명에서 안전한 저장명 생성 (중복 시 숫자 붙임)."""
    p = Path(original)
    stem = p.stem
    ext = p.suffix.lower()
    # 비허용 문자 제거
    stem = re.sub(r"[^가-힣A-Za-z0-9._-]", "_", stem).strip("._-") or "audio"
    base = f"{stem}{ext}"
    target = directory / base
    counter = 1
    while target.exists():
        base = f"{stem}_{counter}{ext}"
        target = directory / base
        counter += 1
    return base


def _next_kst_evening(now_utc: datetime) -> datetime:
    """다음 '저녁 배치 알림' 시각(KST 기준)을 UTC datetime 으로 반환.

    settings.media_notify_evening_hour_kst (기본 21) 시각 이전이면 오늘,
    지났으면 내일 그 시각. KST = UTC+9.
    """
    kst_hour = settings.media_notify_evening_hour_kst
    now_kst = now_utc + timedelta(hours=9)
    target_kst = now_kst.replace(hour=kst_hour, minute=0, second=0, microsecond=0)
    if target_kst <= now_kst:
        target_kst = target_kst + timedelta(days=1)
    return target_kst - timedelta(hours=9)


def save_upload(
    *,
    filename: str,
    data: bytes,
    title: str,
    category: str = "worship",
    artist: Optional[str] = None,
    description: Optional[str] = None,
    scripture_refs: Optional[list] = None,
    order_index: int = 0,
    active: bool = True,
    publish_at: Optional[datetime] = None,
    notify_mode: str = "immediate",
) -> dict:
    """오디오 파일 저장 + DB 레코드 생성. 반환: asset dict.

    publish_at : 발행(앱 노출) 예정 시각(UTC). 미래 시각이면 active 를 강제 False 로 두고,
                 media_publisher 스케줄러가 도래 시 활성화.
    notify_mode : "immediate"(지금 알림) | "batch"(저녁 배치로 묶어 1회) | "none"(알림 안함).
    """
    category = (category or "worship").strip().lower()
    if category not in ("worship", "sermon"):
        raise ValueError("category 는 'worship' 또는 'sermon' 이어야 합니다.")

    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise ValueError(
            f"지원하지 않는 오디오 형식입니다: {ext or '(없음)'}. "
            f"지원: {', '.join(_ALLOWED_EXTS)}"
        )

    cat_dir = _category_dir(category)
    stored_name = _safe_stored_name(filename, cat_dir)
    target = cat_dir / stored_name
    target.write_bytes(data)

    mime = _MIME_MAP.get(ext, "audio/mpeg")
    now = datetime.now(timezone.utc)

    # 예약 발행: 미래 시각이면 활성화를 미루고, 도래 시 스케줄러가 플립
    is_scheduled = publish_at is not None and publish_at > now
    effective_active = False if is_scheduled else bool(active)

    # 알림 시각 결정 — 콘텐츠가 '발행(active) 된 이후'에만 알림이 가도록 보장
    notify_at: Optional[datetime] = None
    if is_scheduled:
        if notify_mode == "immediate":
            notify_at = publish_at                       # 예약 발행 시각에 알림
        elif notify_mode == "batch":
            notify_at = _next_kst_evening(publish_at)    # 발행 이후 다음 저녁(21:00 KST)
        # notify_mode == "none" → 알림 안 보냄
    else:
        if notify_mode == "immediate":
            notify_at = now                              # 지금
        elif notify_mode == "batch":
            notify_at = _next_kst_evening(now)           # 오늘/내일 저녁
        # notify_mode == "none" → 알림 안 보냄
    # 순수 드래프트(비활성 + 예약 없음)는 어떤 모드든 알림 안 보냄
    if effective_active is False and publish_at is None:
        notify_at = None

    # SQLite 정합성(나머지 컬럼은 naive UTC)을 위해 tz 정보 제거 → 일관된 비교 보장
    if publish_at is not None and publish_at.tzinfo is not None:
        publish_at = publish_at.astimezone(timezone.utc).replace(tzinfo=None)
    if notify_at is not None and notify_at.tzinfo is not None:
        notify_at = notify_at.astimezone(timezone.utc).replace(tzinfo=None)

    asset = MediaAsset(
        title=title.strip(),
        category=category,
        artist=artist.strip() if artist else None,
        description=description,
        scripture_refs=scripture_refs or [],
        file_name=stored_name,
        storage_path=str(target),
        mime_type=mime,
        size_bytes=len(data),
        order_index=order_index,
        active=effective_active,
        publish_at=publish_at,
        notify_at=notify_at,
    )
    with get_session() as s:
        s.add(asset)
        s.flush()
        return _row_to_dict(asset)


def ensure_media_schema() -> None:
    """기존 DB 에 새 컬럼(publish_at/notify_at/notified_at)을 안전하게 추가. 멱등."""
    adds = [
        ("publish_at", "TIMESTAMP"),
        ("notify_at", "TIMESTAMP"),
        ("notified_at", "TIMESTAMP"),
    ]
    with get_session() as s:
        for col, typ in adds:
            try:
                s.execute(text(f"ALTER TABLE media_asset ADD COLUMN {col} {typ}"))
                s.flush()
                log.info("[media] schema column added: %s", col)
            except Exception as e:  # 이미 존재 / 미지원 → 무시
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    pass
                else:
                    log.warning("[media] ensure schema %s skipped: %s", col, e)


def list_admin(category: Optional[str] = None) -> list[dict]:
    """관리자용 전체 목록 (비활성 포함)."""
    with get_session() as s:
        q = s.query(MediaAsset)
        if category:
            q = q.filter(MediaAsset.category == category)
        rows = q.order_by(
            MediaAsset.category, MediaAsset.order_index, MediaAsset.created_at.desc()
        ).all()
        return [_row_to_dict(r) for r in rows]


def list_public(category: Optional[str] = None, active_only: bool = True) -> list[dict]:
    """공개 카탈로그 (모바일 앱용). stream_url 포함."""
    with get_session() as s:
        q = s.query(MediaAsset)
        if category:
            q = q.filter(MediaAsset.category == category)
        if active_only:
            q = q.filter(MediaAsset.active.is_(True))
        rows = q.order_by(
            MediaAsset.order_index, MediaAsset.created_at.desc()
        ).all()
        return [_public_dict(r) for r in rows]


def get_asset(asset_id: str) -> Optional[MediaAsset]:
    with get_session() as s:
        return s.query(MediaAsset).filter(MediaAsset.asset_id == asset_id).first()


def _resolve_storage_path(storage_path: str) -> Path:
    """DB에 절대/상대 혼재 가능성을 대비해 경로 정규화.

    - 절대 경로 -> 그대로 사용
    - 상대 경로 -> settings.root_dir 기준으로 결합
    """
    p = Path(storage_path)
    if not p.is_absolute():
        p = settings.root_dir / p
    return p


def get_file(asset_id: str) -> Optional[tuple[Path, str]]:
    """스트리밍용 (경로, mime) 반환. 파일 없으면 None."""
    asset = get_asset(asset_id)
    if not asset:
        return None
    path = _resolve_storage_path(asset.storage_path)
    if not path.exists():
        return None
    return path, asset.mime_type


def update_asset(asset_id: str, fields: dict) -> dict:
    """메타데이터 부분 수정. 화이트리스트 필드만."""
    _UPDATABLE = {
        "title", "category", "artist", "description",
        "scripture_refs", "order_index", "active",
    }
    with get_session() as s:
        asset = s.query(MediaAsset).filter(MediaAsset.asset_id == asset_id).first()
        if not asset:
            raise ValueError("미디어를 찾을 수 없습니다.")
        for key in (_UPDATABLE & fields.keys()):
            value = fields[key]
            if value is not None or key in ("description",):
                setattr(asset, key, value)
        s.flush()
        return _row_to_dict(asset)


def delete_media(asset_id: str) -> bool:
    """DB 레코드 + 디스크 파일 삭제."""
    with get_session() as s:
        asset = s.query(MediaAsset).filter(MediaAsset.asset_id == asset_id).first()
        if not asset:
            return False
        try:
            p = _resolve_storage_path(asset.storage_path)
            if p.exists():
                p.unlink()
        except OSError as exc:
            log.warning("[media] 파일 삭제 실패 (무시): %s", exc)
        s.delete(asset)
        s.flush()
    return True


def _row_to_dict(row: MediaAsset) -> dict:
    return {
        "asset_id": row.asset_id,
        "title": row.title,
        "category": row.category,
        "artist": row.artist,
        "description": row.description,
        "scripture_refs": row.scripture_refs or [],
        "file_name": row.file_name,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "duration_sec": row.duration_sec,
        "order_index": row.order_index,
        "active": row.active,
        "created_at": str(row.created_at) if row.created_at else None,
        "updated_at": str(row.updated_at) if row.updated_at else None,
        "publish_at": str(row.publish_at) if row.publish_at else None,
        "notify_at": str(row.notify_at) if row.notify_at else None,
        "notified_at": str(row.notified_at) if row.notified_at else None,
    }


def _public_dict(row: MediaAsset) -> dict:
    """모바일 앱용 — stream_url 포함 (상대경로, API_BASE 와 결합)."""
    d = _row_to_dict(row)
    d["stream_url"] = f"/mobile/media/{row.asset_id}/stream"
    return d


def media_version() -> dict:
    """공개 카탈로그 변경 감지용 경량 버전.

    모바일이 저비용으로 '갱신 필요 여부'만 판단 (전체 목록 다운로드 전).
    version = "총개수:최근수정시각" — 둘 중 하나라도 바뀌면 카탈로그 재조회.
    """
    from sqlalchemy import func

    with get_session() as s:
        total, max_upd = s.query(
            func.count(MediaAsset.asset_id),
            func.max(MediaAsset.updated_at),
        ).filter(MediaAsset.active.is_(True)).first()
        total = total or 0
        version = f"{total}:{max_upd.isoformat() if max_upd else '0'}"
        return {
            "version": version,
            "total": total,
            "max_updated_at": max_upd.isoformat() if max_upd else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
