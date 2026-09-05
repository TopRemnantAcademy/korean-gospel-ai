"""미디어 발행/알림 스케줄러 (2026-07-29).

설계:
  - publish_at (발행 예정) 이 도래한 항목 → active=True 로 전환 (앱에 노출)
  - notify_at (알림 예정) 이 도래하고 아직 발송 안 한(notified_at None) 항목 →
    Web Push 브로드캐스트 후 notified_at 기록 (중복 발송 방지)

관리자 업로드 시 결정되는 모드:
  immediate : notify_at = 업로드 시각(또는 예약 발행 시각)
  batch     : notify_at = 다음 저녁 21:00 KST (여러 건을 한 번에 묶어 알림)
  none      : notify_at = None (알림 안 보냄)

매 60초 tick 으로 처리하므로 "즉시" 모드도 최대 ~60초 지연.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..db import get_session
from ..models.orm import MediaAsset
from . import media_service, push_service

log = logging.getLogger("media_publisher")

_scheduler: "BackgroundScheduler | None" = None


def _publish_due() -> int:
    """발행 예정(publish_at) 이 도래한 숨김 항목을 active=True 로 전환."""
    now = datetime.utcnow()  # naive UTC (DB 저장 포맷과 일치)
    with get_session() as s:
        due = (
            s.query(MediaAsset)
            .filter(
                MediaAsset.publish_at.isnot(None),
                MediaAsset.publish_at <= now,
                MediaAsset.active.is_(False),
            )
            .all()
        )
        for a in due:
            a.active = True
            a.updated_at = now  # 버전 감지 일관성
        if due:
            s.flush()
    return len(due)


def _notify_due() -> dict:
    """알림 예정(notify_at) 이 도래하고 미발송(notified_at None) 항목을 브로드캐스트.

    보장 사항:
      - active(발행 완료) 콘텐츠만 알림 → 예약 발행 전 알림 누락 방지
      - 발송 시도 후에만 notified_at 기록 → 발송 실패 시 다음 tick 에 재시도(유실 방지)
    """
    now = datetime.utcnow()  # naive UTC (DB 저장 포맷과 일치)
    with get_session() as s:
        due = (
            s.query(MediaAsset)
            .filter(
                MediaAsset.notify_at.isnot(None),
                MediaAsset.notify_at <= now,
                MediaAsset.notified_at.is_(None),
                MediaAsset.active.is_(True),
            )
            .all()
        )
        if not due:
            return {"count": 0, "sent": 0, "failed": 0, "skipped": 0}
        items = [
            {"id": a.asset_id, "title": a.title, "category": a.category} for a in due
        ]
        asset_ids = [a.asset_id for a in due]
    # 세션 밖에서 실제 네트워크 발송 (실패 시 notified_at 미기록 → 재시도)
    try:
        result = push_service.broadcast_media_update(items)
    except Exception as _e:
        log.error("[media_publisher] 알림 브로드캐스트 실패 (재시도 예정): %s", _e)
        return {"count": len(due), "sent": 0, "failed": 0, "skipped": 0}
    # 발송 시도 후에만 notified_at 기록(중복 발송 방지)
    try:
        with get_session() as s2:
            (
                s2.query(MediaAsset)
                .filter(MediaAsset.asset_id.in_(asset_ids))
                .update(
                    {MediaAsset.notified_at: now},
                    synchronize_session=False,
                )
            )
            s2.flush()
    except Exception as _e:
        log.warning("[media_publisher] notified_at 기록 실패(무시): %s", _e)
    return {
        "count": len(due),
        "sent": result.get("sent", 0),
        "failed": result.get("failed", 0),
        "skipped": result.get("skipped", 0),
    }


def tick() -> dict:
    published = _publish_due()
    notified = _notify_due()
    if published or notified.get("count"):
        log.info(
            "[media_publisher] tick: published=%d, notified=%d (sent=%d)",
            published,
            notified.get("count", 0),
            notified.get("sent", 0),
        )
    return {"published": published, **notified}


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        tick,
        IntervalTrigger(seconds=60),
        id="media_publisher_tick",
        replace_existing=True,
    )
    _scheduler.start()
    log.info("[media_publisher] scheduler started (every 60s)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("[media_publisher] scheduler stopped")
