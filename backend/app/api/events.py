"""클라이언트 활동 이벤트 수신 + 관리자 조회.

엔드포인트:
  [클라이언트 / 모바일]
  - POST /mobile/events/batch  — 클라이언트 활동 배치 수신 (게스트 허용, 토큰 선택)

  [관리자]
  - GET  /admin/activity/summary     — 기간 집계(DAU/WAU/MAU, 이벤트분포, Top시청/검색)
  - GET  /admin/activity/events      — 필터 기반 이벤트 목록
  - GET  /admin/activity/user/{id}   — 특정 유저 타임라인
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from .auth import _verify_token, check_admin
from ..db import get_session
from ..models.orm import ActivityEvent

log = logging.getLogger("gospel-api.events")

# 클라이언트가 보낼 수 있는 이벤트 타입 allowlist (미지정/알수없음은 silently drop)
ALLOWED_EVENT_TYPES = {
    "session_start",
    "session_end",
    "page_view",
    "media_play_start",
    "media_play_progress",
    "media_play_complete",
    "search",
    "verse_annotation_create",
    "verse_annotation_update",
    "verse_annotation_delete",
    "share",
    "chat_send",
    "js_error",
    "button_click",
    "identify",
}

MAX_BATCH = 200  # 단일 배치 최대 이벤트 수


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic 스키마
# ═══════════════════════════════════════════════════════════════════════════
class ClientEvent(BaseModel):
    event_type: str
    ts: float
    payload: dict = Field(default_factory=dict)


class EventBatchIn(BaseModel):
    device_id: Optional[str] = None
    subscriber_id: Optional[str] = None  # 클라이언트 주장 — 서버 토큰으로 재검증
    session_id: Optional[str] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None
    events: list[ClientEvent] = Field(..., max_length=MAX_BATCH)


# ═══════════════════════════════════════════════════════════════════════════
# 클라이언트 수신 라우터
# ═══════════════════════════════════════════════════════════════════════════
mobile_router = APIRouter(prefix="/mobile/events", tags=["mobile-events"])


def _optional_user(authorization: Optional[str]) -> Optional[str]:
    """Bearer 토큰이 있으면 sub_id 반환, 없으면 None (게스트 허용)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return _verify_token(authorization[7:])


@mobile_router.post("/batch")
async def ingest_events(
    batch: EventBatchIn,
    authorization: Optional[str] = Header(default=None),
):
    """클라이언트 활동 이벤트 배치 수신.

    - 게스트(토큰 없음) 도 허용 → device_id 로만 귀속.
    - 서버는 클라이언트 주장(subscriber_id) 을 신뢰하지 않고, 토큰에서 추출한
      sub_id 를 우선 사용(스푸핑 방지).
    - DB write 는 이벤트 루프 밖(to_thread) 으로 → 202 즉시 반환(메인 플로우 무지연).
    """
    # 서버는 클라이언트 주장(subscriber_id) 을 신뢰하지 않음 — 검증된 토큰의 sub_id 만 사용.
    # (토큰 없음/무효 → 게스트, device_id 로만 귀속. 스푸핑 방지)
    owner = _optional_user(authorization)

    rows = []
    for ev in batch.events:
        if ev.event_type not in ALLOWED_EVENT_TYPES:
            continue
        # payload 크기 가드(4KB)
        try:
            import json

            size = len(json.dumps(ev.payload, ensure_ascii=False))
        except Exception:
            size = 0
        if size > 4096:
            ev.payload = {"_truncated": True}
        rows.append(
            ActivityEvent(
                subscriber_id=owner,
                device_id=batch.device_id,
                session_id=batch.session_id,
                event_type=ev.event_type,
                platform=batch.platform,
                app_version=batch.app_version,
                payload=ev.payload,
                created_at=datetime.now(timezone.utc),
            )
        )
    if not rows:
        return {"accepted": 0}

    # 비동기 저장 — 요청 스레드 블로킹 방지
    await asyncio.to_thread(_bulk_insert, rows)
    return {"accepted": len(rows)}


def _bulk_insert(rows: list[ActivityEvent]) -> None:
    with get_session() as s:
        s.bulk_save_objects(rows)
        # get_session() 컨텍스트 종료 시 auto-commit


# ═══════════════════════════════════════════════════════════════════════════
# 관리자 조회 라우터
# ═══════════════════════════════════════════════════════════════════════════
admin_router = APIRouter(
    prefix="/admin/activity",
    tags=["admin-activity"],
    dependencies=[Depends(check_admin)],
)


def _serialize(r: ActivityEvent) -> dict:
    return {
        "event_id": r.event_id,
        "subscriber_id": r.subscriber_id,
        "device_id": r.device_id,
        "session_id": r.session_id,
        "event_type": r.event_type,
        "platform": r.platform,
        "app_version": r.app_version,
        "payload": r.payload,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@admin_router.get("/summary")
def activity_summary(days: int = 30):
    """기간 집계 — 활성 유저(DAU/WAU/MAU), 이벤트 분포, Top 시청/검색."""
    days = max(1, min(int(days), 365))
    # SQLite 가 tz 를 보존하지 않으므로 naive UTC 로 통일해 비교
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    d1 = now - timedelta(hours=24)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    with get_session() as s:
        rows = (
            s.query(ActivityEvent)
            .filter(ActivityEvent.created_at >= since)
            .order_by(ActivityEvent.created_at.desc())
            .limit(50000)
            .all()
        )

    total = len(rows)
    events_by_type: Counter = Counter()
    dau_set, wau_set, mau_set = set(), set(), set()
    watch_start, watch_complete = Counter(), Counter()
    search_counter: Counter = Counter()
    media_meta: dict = {}

    for r in rows:
        ca = r.created_at.replace(tzinfo=None) if r.created_at else None
        events_by_type[r.event_type] += 1
        if ca is not None:
            if ca >= d1:
                dau_set.add(r.subscriber_id or ("d:" + str(r.device_id)))
            if ca >= d7:
                wau_set.add(r.subscriber_id or ("d:" + str(r.device_id)))
            if ca >= d30:
                mau_set.add(r.subscriber_id or ("d:" + str(r.device_id)))

        p = r.payload or {}
        if r.event_type == "media_play_start":
            mid = p.get("media_id")
            if mid:
                watch_start[mid] += 1
                media_meta.setdefault(
                    mid,
                    {
                        "title": p.get("title"),
                        "category": p.get("category"),
                        "media_type": p.get("media_type"),
                    },
                )
        elif r.event_type == "media_play_complete":
            mid = p.get("media_id")
            if mid:
                watch_complete[mid] += 1
                media_meta.setdefault(
                    mid,
                    {
                        "title": p.get("title"),
                        "category": p.get("category"),
                        "media_type": p.get("media_type"),
                    },
                )
        elif r.event_type == "search":
            q = (p.get("query") or "").strip()
            if q:
                search_counter[q] += 1

    top_media = []
    for mid, cnt in watch_complete.most_common(20):
        meta = media_meta.get(mid, {})
        top_media.append(
            {
                "media_id": mid,
                "title": meta.get("title"),
                "category": meta.get("category"),
                "media_type": meta.get("media_type"),
                "watch_count": cnt,
                "start_count": watch_start.get(mid, 0),
                "completion_rate": round(
                    cnt / watch_start.get(mid, cnt) * 100, 1
                )
                if watch_start.get(mid)
                else 0.0,
            }
        )

    return {
        "window_days": days,
        "total_events": total,
        "dau": len(dau_set),
        "wau": len(wau_set),
        "mau": len(mau_set),
        "events_by_type": [
            {"event_type": k, "count": v} for k, v in events_by_type.most_common()
        ],
        "top_media": top_media,
        "top_search": [
            {"query": k, "count": v} for k, v in search_counter.most_common(20)
        ],
    }


@admin_router.get("/events")
def list_activity_events(
    event_type: Optional[str] = None,
    subscriber_id: Optional[str] = None,
    media_id: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """필터 기반 이벤트 목록 (기간/타입/유저/media_id)."""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    with get_session() as s:
        q = s.query(ActivityEvent)
        if event_type:
            q = q.filter(ActivityEvent.event_type == event_type)
        if subscriber_id:
            q = q.filter(ActivityEvent.subscriber_id == subscriber_id)
        if from_:
            try:
                fdt = datetime.fromisoformat(from_).replace(tzinfo=None)
                q = q.filter(ActivityEvent.created_at >= fdt)
            except ValueError:
                pass
        if to:
            try:
                tdt = datetime.fromisoformat(to).replace(tzinfo=None)
                q = q.filter(ActivityEvent.created_at <= tdt)
            except ValueError:
                pass
        rows = (
            q.order_by(ActivityEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        result = [_serialize(r) for r in rows]

    # media_id 는 JSON payload 내부 → SQL 이식성 위해 파이썬 사이드 필터
    if media_id:
        result = [
            r for r in result if (r.get("payload") or {}).get("media_id") == media_id
        ]
    return result


@admin_router.get("/user/{subscriber_id}")
def user_timeline(subscriber_id: str, limit: int = 200):
    """특정 유저의 활동 타임라인."""
    limit = max(1, min(int(limit), 500))
    with get_session() as s:
        rows = (
            s.query(ActivityEvent)
            .filter(ActivityEvent.subscriber_id == subscriber_id)
            .order_by(ActivityEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_serialize(r) for r in rows]
