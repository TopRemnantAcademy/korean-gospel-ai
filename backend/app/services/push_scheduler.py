"""푸시 알림 스케줄러 — 매일 오늘의 말씀을 구독자에게 발송.

APScheduler 기반. FastAPI lifespan 에서 시작/종료.

설정 (.env):
  PUSH_ENABLED=true — 스케줄러 활성화
  PUSH_HOUR_KST=7 — 발송 시각 (한국 표준시, 기본 7시)

의존성: pip install apscheduler
없으면 스케줄러를 시작하지 않고 로그만 남김 (graceful degradation).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..config import settings

log = logging.getLogger("gospel-api.push-scheduler")

_scheduler: Optional["asyncio.Task"] = None
_aps_scheduler = None


async def _daily_verse_push():
    """매일 구독자에게 오늘의 말씀 푸시 발송 (비동기 래퍼)."""
    try:
        from .push_service import _get_all_subscribed

        subs = _get_all_subscribed()
        if not subs:
            return

        log.info("[push-scheduler] 일일 말씀 발송 시작: %d명", len(subs))

        # 각 사용자별로 맞춤 인사 생성 후 발송
        from .greeting_service import generate_greeting
        from .push_service import _send

        sent_total = 0
        for sub_id, tokens in subs:
            try:
                greeting_result = await generate_greeting(sub_id, mode="auto", target_lang="ko")
                greeting = greeting_result.get("greeting", "")
                # 인사가 너무 길면 앞 100자만
                body = greeting[:100] + ("..." if len(greeting) > 100 else "")
                result = _send(
                    tokens,
                    title="오늘의 말씀",
                    body=body,
                    data={"type": "daily_verse", "url": "/"},
                )
                sent_total += result.get("sent", 0)
            except Exception as exc:
                log.warning("[push-scheduler] %s 발송 실패: %s", sub_id, exc)

        log.info("[push-scheduler] 일일 말씀 발송 완료: %d건", sent_total)
    except Exception as exc:
        log.error("[push-scheduler] 일일 발송 작업 예외: %s", exc)


def start_scheduler():
    """스케줄러 시작. PUSH_ENABLED=true 일 때만 동작."""
    global _aps_scheduler

    push_enabled = bool(settings.push_enabled)
    if not push_enabled:
        log.info("[push-scheduler] PUSH_ENABLED=false — 스케줄러 비활성화")
        return

    hour_kst = int(settings.push_hour_kst)

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning(
            "[push-scheduler] apscheduler 미설치 — 스케줄러 시작 불가. "
            "pip install apscheduler 필요."
        )
        return

    _aps_scheduler = AsyncIOScheduler()
    # AsyncIOScheduler 는 자체 이벤트 루프에서 실행되므로 코루틴을 직접 잡으로 등록.
    # (새 이벤트 루프를 만들면 httpx/LLM 클라이언트의 루프와 충돌)
    _aps_scheduler.add_job(
        _daily_verse_push,  # async def 코루틴을 직접 등록
        CronTrigger(hour=hour_kst, minute=0, timezone="Asia/Seoul"),
        id="daily_verse_push",
        replace_existing=True,
    )
    _aps_scheduler.start()
    log.info("[push-scheduler] 시작 — 매일 KST %02d시 발송", hour_kst)


async def stop_scheduler():
    """스케줄러 종료 (FastAPI lifespan shutdown)."""
    global _aps_scheduler
    if _aps_scheduler:
        _aps_scheduler.shutdown(wait=False)
        _aps_scheduler = None
        log.info("[push-scheduler] 종료")
