"""트렌딩 집계 + 초안 정리 스케줄러.

- 1분 주기: 질문/답변 집계 스냅샷 갱신
- 1시간 주기: 만료된 초안 정리
- 통찰 생성: Top 20 진입 신규 항목에 대해 최초 1회
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

from ..db import get_session

log = logging.getLogger("gospel-api.scheduler")

_SCHEDULER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_scheduler():
    """백그라운드 스레드에서 실행되는 스케줄러 루프."""
    log.info("[trending-scheduler] 시작됨 (1분 주기 집계, 1시간 주기 초안 정리)")

    last_aggregation = _now() - timedelta(minutes=2)
    last_draft_cleanup = _now() - timedelta(hours=2)

    while not _STOP_EVENT.wait(timeout=10):
        now = _now()

        # ── 1분 주기: 집계 ──
        if (now - last_aggregation).total_seconds() >= 60:
            try:
                from . import trending_service

                q_count = trending_service.compute_trending_snapshots(
                    snapshot_type="question",
                    period_days=30,
                    min_count=2,
                )
                a_count = trending_service.compute_trending_snapshots(
                    snapshot_type="answer",
                    period_days=30,
                    min_count=2,
                )
                log.info("[trending-scheduler] 집계 완료: 질문=%d, 답변=%d", q_count, a_count)

                # 의미론적 클러스터링 (증분 강화, TRENDING_SEMANTIC_CLUSTER=1 시)
                # 모델 미사용 환경에서는 no-op 로 안전 종료.
                try:
                    merged = trending_service.semantic_cluster_snapshots()
                    if merged > 0:
                        log.info("[trending-scheduler] 의미론적 병합: %d건", merged)
                except Exception as _se:
                    log.warning("[trending-scheduler] 의미론적 클러스터 건너뜀: %s", _se)

                # 신규 Top 20 진입 항목에 통찰 생성 (비동기)
                try:
                    loop = asyncio.new_event_loop()
                    result = loop.run_until_complete(
                        _generate_insights_async(limit=5)
                    )
                    loop.close()
                    if result.get("generated", 0) > 0:
                        log.info("[trending-scheduler] 신규 통찰 생성: %d건", result["generated"])
                except Exception as _ie:
                    log.warning("[trending-scheduler] 통찰 생성 실패: %s", _ie)

            except Exception as e:
                log.warning("[trending-scheduler] 집계 실패: %s", e)

            last_aggregation = now

        # ── 1시간 주기: 초안 정리 ──
        if (now - last_draft_cleanup).total_seconds() >= 3600:
            try:
                with get_session() as s:
                    from ..models.orm import QAEditDraft

                    deleted = (
                        s.query(QAEditDraft)
                        .filter(QAEditDraft.expires_at < now)
                        .delete()
                    )
                    s.flush()
                    if deleted > 0:
                        log.info("[trending-scheduler] 만료된 초안 %d건 정리 완료", deleted)
            except Exception as e:
                log.warning("[trending-scheduler] 초안 정리 실패: %s", e)

            last_draft_cleanup = now

    log.info("[trending-scheduler] 종료됨")


async def _generate_insights_async(limit: int = 5) -> dict:
    """비동기 통찰 생성 (스케줄러 전용)."""
    from .insight_engine import generate_insights_for_top_questions

    return await generate_insights_for_top_questions(limit=limit)


def start_scheduler():
    """트렌딩 스케줄러 시작."""
    global _SCHEDULER_THREAD, _STOP_EVENT

    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        log.warning("[trending-scheduler] 이미 실행 중")
        return

    _STOP_EVENT.clear()
    _SCHEDULER_THREAD = threading.Thread(
        target=_run_scheduler,
        name="trending-scheduler",
        daemon=True,
    )
    _SCHEDULER_THREAD.start()


def stop_scheduler():
    """트렌딩 스케줄러 종료."""
    _STOP_EVENT.set()
    if _SCHEDULER_THREAD:
        _SCHEDULER_THREAD.join(timeout=5)
