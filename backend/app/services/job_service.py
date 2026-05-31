"""BackgroundJob CRUD — 비동기 작업 진행 상태 관리.

각 단계 업데이트는 별도 세션으로 즉시 커밋 → 폴링하는 프론트엔드가 바로 볼 수 있음.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from ..db import get_session
from ..models.orm import BackgroundJob


def create_job(job_type: str) -> str:
    """새 작업 레코드를 만들고 job_id를 반환한다."""
    with get_session() as s:
        job = BackgroundJob(
            job_type=job_type,
            status="pending",
            current_stage="⏳ 대기 중...",
            stage_detail="",
            progress_pct=0,
        )
        s.add(job)
        s.flush()
        job_id = job.job_id
        s.commit()
    return job_id


def update_stage(
    job_id: str,
    stage: str,
    detail: str = "",
    pct: int = 0,
    status: str = "running",
) -> None:
    """단계 정보를 즉시 커밋 (별도 세션 사용)."""
    with get_session() as s:
        job = s.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = status
        job.current_stage = stage
        job.stage_detail = detail
        job.progress_pct = min(max(pct, 0), 100)
        job.updated_at = datetime.utcnow()
        s.commit()


def complete_job(job_id: str, result: dict) -> None:
    """작업 성공 완료."""
    with get_session() as s:
        job = s.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = "done"
        job.current_stage = "✅ 완료"
        job.stage_detail = ""
        job.progress_pct = 100
        job.result_json = result
        job.updated_at = datetime.utcnow()
        s.commit()


def fail_job(job_id: str, error: dict) -> None:
    """작업 실패."""
    with get_session() as s:
        job = s.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.current_stage = "❌ 실패"
        job.error_json = error
        job.updated_at = datetime.utcnow()
        s.commit()


def cleanup_stale_jobs(older_than_minutes: int = 30) -> int:
    """서버 재시작 시 미완료(pending/running) 작업을 자동 실패 처리.

    이유: uvicorn 재시작 → asyncio 태스크 전부 소멸 → 해당 잡은
    영원히 'running' 상태로 남아 폴링하는 프론트가 무한 대기하게 됨.
    """
    from datetime import timedelta
    from sqlalchemy import select
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    with get_session() as s:
        stmt = select(BackgroundJob).where(
            BackgroundJob.status.in_(["pending", "running"]),
            BackgroundJob.created_at < cutoff,
        )
        stale = s.execute(stmt).scalars().all()
        for job in stale:
            job.status = "failed"
            job.current_stage = "❌ 서버 재시작으로 취소됨"
            job.error_json = {
                "error": "서버가 재시작되어 작업이 취소되었어요. 다시 시도해주세요.",
            }
            job.updated_at = datetime.utcnow()
        count = len(stale)
        s.commit()
    return count


def get_job(job_id: str) -> Optional[dict]:
    """job 상태 딕셔너리 반환. 없으면 None."""
    with get_session() as s:
        job = s.get(BackgroundJob, job_id)
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "job_type": job.job_type,
            "status": job.status,
            "current_stage": job.current_stage,
            "stage_detail": job.stage_detail,
            "progress_pct": job.progress_pct,
            "result_json": job.result_json,
            "error_json": job.error_json,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }
