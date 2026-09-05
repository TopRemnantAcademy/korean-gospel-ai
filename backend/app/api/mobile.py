"""GET/POST /mobile/* — 모바일 PWA 전용 엔드포인트 (회원 본인 데이터 + 앱 콘텐츠).

기획안 (.omo/drafts/web-counseling-app-full-suite.md) 기반:
  앱 = 상담 + 성경 + 찬양 + 묵상 + 푸시 (웹은 상담만)

엔드포인트:
  [공개]
  - GET  /mobile/legal              — 위기상담 안내 + 개인정보 처리방침
  - GET  /mobile/music              — 찬양/묵상 음원 카탈로그
  - GET  /mobile/music/{id}/stream  — 음원 파일 스트리밍 (Range 지원)
  - GET  /mobile/bible/read         — 성경 본문 읽기 (공개 도메인)
  [회원]
  - GET  /mobile/profile            — 현재 로그인 사용자 프로필
  - GET  /mobile/history            — 내 대화 기록 (search/limit)
  - GET  /mobile/verse/daily        — 재방문 인사 + 오늘의 말씀
  - GET  /mobile/bible/search       — RAG 기반 성경/설교 검색
  - GET  /mobile/bible/refs         — 색인된 구절 레퍼런스 브라우징
  - POST /mobile/push/subscribe     — 푸시 알림 구독 등록 (FCM 토큰)
  - DELETE /mobile/push/subscribe   — 푸시 알림 구독 해제
  - POST /mobile/push/test          — 자신에게 테스트 알림 발송
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from .auth import get_current_user
from ..config import settings
from ..services import memory_service
from ..services.subscriber_service import get_or_create
from ..services import annotation_service

log = logging.getLogger("gospel-api.mobile")

router = APIRouter(prefix="/mobile", tags=["mobile"])


# ═══════════════════════════════════════════════════════════════════════════════
# 경량 인메모리 TTL 캐시 (정적 엔드포인트용)
#   - Redis 미설정 환경에서도 동시 20+ 읽기 요청을 DB/연산 없이 즉시 응답.
#   - 스레드 안전(threading.RLock), TTL 만료 시 재계산.
#   - 전역 공유(單 프로세스) — 다중 worker 운영 시 각 worker 가 독자 캐시 보유(수용).
# ═══════════════════════════════════════════════════════════════════════════════
import threading
import time as _time

_cache_lock = threading.RLock()
_cache_store: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl_sec: int, producer):
    """TTL 캐시 래퍼 — hit 시 즉시 반환, miss/expire 시 producer() 재계산."""
    now = _time.time()
    with _cache_lock:
        item = _cache_store.get(key)
        if item is not None:
            exp, val = item
            if exp > now:
                return val
    val = producer()
    with _cache_lock:
        _cache_store[key] = (_time.time() + ttl_sec, val)
    return val


# ═══════════════════════════════════════════════════════════════════════════════
# 공개 엔드포인트 (Bearer 없이도 접근 가능)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/legal")
def get_legal_info():
    """위기상담 안내 + 개인정보 처리방침 (공개)."""
    return {
        "counseling_disclaimer": (
            "이 앱의 상담 내용은 기독교 영적 지원을 목적으로 하며, "
            "전문 심리 치료나 의학적 진단을 대체하지 않습니다."
        ),
        "privacy_summary": (
            "수집 항목: 이메일, 대화 내용(상담 목적), 기기 정보, 푸시 토큰(알림 수신 동의 시). "
            "목적: 상담 서비스 제공 및 맞춤 영적 지원. "
            "보관: 계정 삭제 시 즉시 파기. "
            "제3자 제공: 없음. "
            "서버 위치: 대한민국."
        ),
    }


@router.get("/app-config")
def get_app_config():
    """모바일 앱 설정 + 버전 게이트 (공개, 캐시 60s).

    클라이언트는 구동 시 로컬 versionCode 를 응답의 min_version_code/latest_version_code 와 비교:
      - versionCode < min_version_code  → force_update=true (강제 업데이트 차단)
      - versionCode < latest_version_code → latest_available=true (권장 업데이트)
    update_url 가 비어있으면 클라이언트 기본 다운로드 페이지(download.html) 사용.
    """
    from ..config import settings

    def _produce():
        min_code = settings.mobile_min_version_code
        latest_code = max(settings.mobile_latest_version_code, min_code)
        return {
            "min_version_code": min_code,
            "latest_version_code": latest_code,
            "latest_version_name": settings.mobile_latest_version_name,
            "force_update": False,  # 실제 강제 여부는 클라이언트가 로컬 code 와 비교해 판정
            "update_url": settings.mobile_update_url or "",
            "api_base_hint": "",  # 클라이언트가 이미 알고 있으므로 비워둠
        }

    # 버전 게이트는 거의 변하지 않음 → 60s TTL 인메모리 캐시 (동시 20+ 구동 시 DB/연산 0)
    return _cached("app-config", 60, _produce)


@router.get("/push/vapid")
def get_vapid_key():
    """Web Push VAPID 공개키 (공개). 클라이언트 pushManager.subscribe 에 사용."""
    from ..services.push_service import get_vapid_public_key

    key = get_vapid_public_key()
    if not key:
        return {"enabled": False, "public_key": None}
    return {"enabled": True, "public_key": key}


@router.get("/music")
def get_music_catalog(response: Response):
    """찬양/묵상 음원 카탈로그 (공개).

    data/music/ 의 파일 트랙 + generated Web Audio 폴백을 통합.
    공개 정적 카탈로그이므로 60초 캐싱(인메모리 TTL + HTTP Cache-Control).
    """
    from ..services.music_service import get_catalog

    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"

    def _produce():
        catalog = get_catalog()
        return {"tracks": catalog, "total": len(catalog)}

    return _cached("music-catalog", 60, _produce)


@router.get("/music/{track_id}/stream")
def stream_music(track_id: str):
    """음원 파일 스트리밍 (공개, Range 요청 지원).

    FileResponse 가 Range 헤더를 처리해 부분 요청(seek)을 지원.
    파일이 없는 generated 트랙이면 404.
    """
    from ..services.music_service import get_track_file

    result = get_track_file(track_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="음원 파일이 없습니다. 이 트랙은 Web Audio 합성 타입입니다.",
        )
    path, media_type = result
    return FileResponse(str(path), media_type=media_type, filename=path.name)


# ── 영성훈련 콘텐츠 (YouTube/Spotify 링크) ─────────────────────────────────────

@router.get("/content")
def list_content(
    response: Response,
    category: Optional[str] = Query(None, description="lecture|music|devotion"),
    source: Optional[str] = Query(None, description="youtube|spotify|other"),
    lang: Optional[str] = Query(None, description="ko|zh|en|ja — 지정 시 해당 언어 콘텐츠만 노출 (중국어 앱은 zh)"),
):
    """영성훈련 콘텐츠 링크 카탈로그 (공개).

    관리자가 등록한 YouTube 강의 / Spotify 찬양 / 묵상 콘텐츠를 반환.
    embed_url 은 클라이언트에서 iframe으로 직접 삽입 가능.
    lang 지정 시 해당 언어 콘텐츠만 노출 — 중국어 앱은 lang=zh 로 호출해 한글 안 읽음.
    공개 정적 카탈로그이므로 60초 캐싱 — DB/CDN 부하 감소.
    """
    from ..services.content_service import list_content as _list

    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    items = _list(category=category, source=source, lang=lang, active_only=True)
    return {"items": items, "total": len(items)}


# ── 성경 본문 읽기 (공개 도메인) ────────────────────────────────────────────────

@router.get("/bible/read")
def bible_read(
    book: str = Query(..., max_length=30, pattern=r"^[가-힣一-鿿A-Za-z0-9 _-]+$", description="책명 예: 创世记"),
    chapter: int = Query(..., ge=1, le=200, description="장"),
    verse: Optional[int] = Query(None, ge=1, le=200, description="특정 절 (선택, 하위호환)"),
    verse_start: Optional[int] = Query(None, ge=1, le=200, description="범위 시작 절"),
    verse_end: Optional[int] = Query(None, ge=1, le=200, description="범위 끝 절"),
    version: str = Query("simpl", pattern=r"^(simpl|trad|kjv)$", description="성경 버전: simpl(간체)/trad(번체)/kjv(영어)"),
):
    """성경 본문 읽기 (공개).

    공개 도메인 개역개정(1998) 텍스트 기반.
    - verse 지정 시 해당 절 1개
    - verse_start/verse_end 지정 시 절 범위
    - 둘 다 없으면 장 전체
    - version: simpl(간체 기본)/trad(번체 화합본)
    모바일 성경 선택기(몇 장 몇 절)에서 사용. 데이터 미색인 시 안내 메시지.
    """
    from ..services.bible_service import get_verse_range, get_book_structure

    struct = get_book_structure(book, version=version)
    if struct is None:
        return {
            "book": book,
            "chapter": chapter,
            "available": False,
            "verses": [],
            "text": None,
            "message": (
                f"{book} 본문이 아직 색인되지 않았습니다. "
                "운영자가 성경 본문을 data/bible/ 디렉토리에 추가하면 표시됩니다."
            ),
        }

    # verse 단일 지정은 범위로 변환 (하위호환)
    if verse is not None:
        verse_start, verse_end = verse, verse

    verses = get_verse_range(book, chapter, verse_start, verse_end, version=version)
    if verses is None:
        return {
            "book": book,
            "chapter": chapter,
            "available": False,
            "verses": [],
            "text": None,
            "message": f"{book} {chapter}장 본문이 아직 색인되지 않았습니다.",
        }

    # 참조 문자열 구성
    if verse_start is not None:
        ref = f"{book} {chapter}:{verse_start}" + (f"-{verse_end}" if verse_end and verse_end != verse_start else "")
    else:
        ref = f"{book} {chapter}장"

    chapter_count = struct["total_chapters"]
    return {
        "book": book,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
        "reference": ref,
        "verses": verses,
        "verse_count": len(verses),
        "chapter_count": chapter_count,
        "text": "\n".join(f"{v['v']}:{v['t']}" for v in verses),
        "available": True,
    }


# 위 bible_read 의 정적 캐시 버전 — 매번 파일 I/O(get_book_structure) 회피
@router.get("/bible/read/cached")
def bible_read_cached(
    book: str = Query(..., max_length=30, pattern=r"^[가-힣一-鿿A-Za-z0-9 _-]+$", description="책명 예: 创世记"),
    chapter: int = Query(..., ge=1, le=200, description="장"),
    verse: Optional[int] = Query(None, ge=1, le=200, description="특정 절 (선택, 하위호환)"),
    verse_start: Optional[int] = Query(None, ge=1, le=200, description="범위 시작 절"),
    verse_end: Optional[int] = Query(None, ge=1, le=200, description="범위 끝 절"),
    version: str = Query("simpl", pattern=r"^(simpl|trad|kjv)$", description="성경 버전: simpl(간체)/trad(번체)/kjv(영어)"),
):
    """성경 본문 읽기 (공개, 300s TTL 캐시).

    bible_read 와 동일하나 정적 본문이므로 5분 캐시로 동시 읽기 부하 제거.
    """
    from ..services.bible_service import get_verse_range, get_book_structure

    cache_key = f"bible-read:{book}:{chapter}:{verse}:{verse_start}:{verse_end}:{version}"

    def _produce():
        struct = get_book_structure(book, version=version)
        if struct is None:
            return {
                "book": book, "chapter": chapter, "available": False, "verses": [],
                "text": None,
                "message": f"{book} 본문이 아직 색인되지 않았습니다.",
            }
        if verse is not None:
            vs, ve = verse, verse
        else:
            vs, ve = verse_start, verse_end
        verses = get_verse_range(book, chapter, vs, ve, version=version)
        if verses is None:
            return {
                "book": book, "chapter": chapter, "available": False, "verses": [],
                "text": None,
                "message": f"{book} {chapter}장 본문이 아직 색인되지 않았습니다.",
            }
        ref = f"{book} {chapter}:{vs}" + (f"-{ve}" if ve and ve != vs else "") if vs is not None else f"{book} {chapter}장"
        return {
            "book": book, "chapter": chapter, "verse_start": vs, "verse_end": ve,
            "reference": ref, "verses": verses, "verse_count": len(verses),
            "chapter_count": struct["total_chapters"],
            "text": "\n".join(f"{v['v']}:{v['t']}" for v in verses),
            "available": True,
        }

    return _cached(cache_key, 300, _produce)


# ═══════════════════════════════════════════════════════════════════════════════
# 회원 전용 엔드포인트 (Bearer 필수)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/profile")
def get_my_profile(current_user: str = Depends(get_current_user)):
    """현재 로그인 사용자 프로필."""
    return get_or_create(current_user)


@router.get("/history")
def my_history(
    limit: int = Query(200, ge=1, le=500),
    search: Optional[str] = None,
    current_user: str = Depends(get_current_user),
):
    """내 대화 기록. memory_service.all_interactions 를 본인 subscriber_id 로 필터링."""
    return memory_service.all_interactions(
        subscriber_id=current_user, limit=limit, search=search,
    )


@router.delete("/history/{interaction_id}")
def delete_history(
    interaction_id: str,
    current_user: str = Depends(get_current_user),
):
    """내 대화 기록 항목 삭제(본인 소유만 — 타인 삭제 차단)."""
    deleted = memory_service.delete_interaction(interaction_id, subscriber_id=current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="interaction not found or not owned")
    return {"deleted": True}


@router.get("/annotations")
def list_annotations(current_user: str = Depends(get_current_user)):
    """내 말씀 하이라이트/북마크/메모 목록."""
    return annotation_service.list_annotations(current_user)


@router.post("/annotations")
def upsert_annotation(
    payload: dict = Body(...),
    current_user: str = Depends(get_current_user),
):
    """구절 하이라이트/메모 등록·갱신. body: {book, chapter, verse, color?, note?}."""
    book = str(payload.get("book", "")).strip()
    if not book:
        raise HTTPException(status_code=400, detail="book is required")
    try:
        chapter = int(payload.get("chapter", 0))
        verse = int(payload.get("verse", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="chapter/verse must be integers")
    if chapter <= 0 or verse <= 0:
        raise HTTPException(status_code=400, detail="chapter/verse must be positive")
    return annotation_service.upsert_annotation(
        subscriber_id=current_user,
        book=book,
        chapter=chapter,
        verse=verse,
        color=payload.get("color"),
        note=payload.get("note"),
    )


@router.delete("/annotations/{annotation_id}")
def delete_annotation(
    annotation_id: str,
    current_user: str = Depends(get_current_user),
):
    """말씀 메모/하이라이트 삭제(본인 소유만)."""
    deleted = annotation_service.delete_annotation(annotation_id, subscriber_id=current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="annotation not found or not owned")
    return {"deleted": True}


@router.delete("/annotations/ref/{book}/{chapter}/{verse}")
def delete_annotation_by_ref(
    book: str,
    chapter: int,
    verse: int,
    current_user: str = Depends(get_current_user),
):
    """(책/장/절) 기준 삭제 — 프론트 ref 기반 동기화용."""
    deleted = annotation_service.delete_annotation_by_ref(
        subscriber_id=current_user, book=book, chapter=chapter, verse=verse,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="annotation not found")
    return {"deleted": True}


@router.get("/verse/daily")
async def daily_verse(
    current_user: str = Depends(get_current_user),
):
    """재방문 인사 + 오늘의 말씀 (묵상).

    greeting_service.generate_greeting() 재사용.
    사용자별 30s TTL 캐시 — 동시 재방문 시 DB/LLM 조회 중복 방지.
    """
    from ..services.greeting_service import generate_greeting

    def _produce():
        return generate_greeting(current_user, mode="auto", target_lang="ko")

    result = _cached(f"daily-verse:{current_user}", 30, _produce)
    return {
        "greeting": result["greeting"],
        "mode_used": result["mode_used"],
        "days_since_last_visit": result["days_since_last_visit"],
        "is_first_visit": result["is_first_visit"],
        "welcome_verse": settings.welcome_verse,
        "subscriber_id": current_user,
    }


# ── 성경/설교 검색 (회원) ──────────────────────────────────────────────────────

@router.get("/bible/search")
async def bible_search(
    q: str = Query(..., min_length=1, max_length=200, description="검색어"),
    top_k: int = Query(5, ge=1, le=20),
    current_user: str = Depends(get_current_user),
):
    """RAG 기반 성경/설교 본문 검색."""
    try:
        from ..services.retriever import get_retriever
        from ..services.search_v4 import get_search_engine

        retriever = get_retriever()
        engine = get_search_engine(retriever)
        results = await engine.search(query=q, top_k=top_k)

        return {
            "query": q,
            "total": len(results),
            "results": [
                {
                    "id": r.id,
                    "text": (
                        r.compressed_context.compressed_text
                        if r.compressed_context
                        else r.text[:500]
                    ),
                    "source_title": r.source_title,
                    "source_type": r.source_type,
                    "reliability": round(r.reliability_score, 2),
                    "score": round(r.final_score, 4),
                }
                for r in results
            ],
        }
    except Exception as exc:
        log.warning("[mobile/bible/search] 검색 실패: %s", exc)
        return {"query": q, "total": 0, "results": []}


@router.get("/bible/refs")
def bible_refs(
    book: Optional[str] = Query(None, description="성경 책명 예: 요한복음"),
    current_user: str = Depends(get_current_user),
):
    """색인된 설교에서 참조된 성경 구절 브라우징."""
    from ..db import get_session
    from ..models.orm import DocumentVersion

    with get_session() as s:
        rows = (
            s.query(DocumentVersion.scripture_refs)
            .filter(
                DocumentVersion.state == "published",
                DocumentVersion.scripture_refs.isnot(None),
            )
            .all()
        )
        all_refs: list[str] = []
        for (refs,) in rows:
            if isinstance(refs, list) and refs:
                all_refs.extend(refs)

        unique_refs = sorted(set(all_refs))
        if book:
            unique_refs = [r for r in unique_refs if r.startswith(book)]

    return {"refs": unique_refs, "total": len(unique_refs)}


# ── 푸시 알림 (회원) ────────────────────────────────────────────────────────────

@router.post("/push/subscribe")
def push_subscribe(payload: dict = Body(...)):
    """Web Push 구독 등록. body: {"token": "<PushSubscription JSON>", "platform": "web", "sub_id": "<subscriber_id>"}.

    무인증(sub_id 기반) 허용 — 게스트 포함 모든 사용자가 구독 가능.
    (푸시 토큰은 서버 VAPID 개인키로만 발송 가능하므로 구독 등록 자체는 저위험)
    sub_id 에 해당하는 Subscriber 가 없으면 생성(게스트 자동 가입).
    """
    token = str(payload.get("token", "")).strip()
    platform = str(payload.get("platform", "web")).strip()
    sub_id = str(payload.get("sub_id") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token 이 필요합니다.")
    if not sub_id:
        raise HTTPException(status_code=400, detail="sub_id 가 필요합니다.")

    from ..db import get_session
    from ..models.orm import Subscriber

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            sub = Subscriber(subscriber_id=sub_id, consent={})
            s.add(sub)
            s.flush()
        consent = dict(sub.consent or {})
        tokens = consent.get("push_tokens", [])
        entry = {"token": token, "platform": platform}
        if not any(t.get("token") == token for t in tokens):
            tokens.append(entry)
            consent["push_tokens"] = tokens
            consent["push_enabled"] = True
            sub.consent = consent
            s.flush()

    return {"ok": True, "subscribed": True, "token_count": len(tokens)}


@router.delete("/push/subscribe")
def push_unsubscribe(payload: Optional[dict] = Body(default=None)):
    """Web Push 구독 해제. body: {"token": "...", "sub_id": "..."} (token 생략 시 전체 해제)."""
    token = str((payload or {}).get("token", "")).strip()
    sub_id = str((payload or {}).get("sub_id") or "").strip()
    if not sub_id:
        raise HTTPException(status_code=400, detail="sub_id 가 필요합니다.")

    from ..db import get_session
    from ..models.orm import Subscriber

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="subscriber not found")
        consent = dict(sub.consent or {})
        tokens = consent.get("push_tokens", [])
        if token:
            tokens = [t for t in tokens if t.get("token") != token]
        else:
            tokens = []
        consent["push_tokens"] = tokens
        consent["push_enabled"] = len(tokens) > 0
        sub.consent = consent
        s.flush()

    return {"ok": True, "subscribed": False, "token_count": len(tokens)}


@router.post("/push/test")
def push_test(current_user: str = Depends(get_current_user)):
    """자신에게 테스트 알림 발송."""
    from ..services.push_service import send_to_subscriber

    result = send_to_subscriber(
        sub_id=current_user,
        title=" 알림 테스트",
        body="푸시 알림이 정상적으로 도착했습니다.",
        data={"type": "test", "url": "/"},
    )
    return result
