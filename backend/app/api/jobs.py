"""GET /jobs/{job_id} — 백그라운드 작업 상태 폴링."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.job_service import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def job_status(job_id: str):
    """작업 상태 조회. 프론트엔드가 2초 간격으로 폴링."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job
