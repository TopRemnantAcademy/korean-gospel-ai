"""GET /jobs/{job_id} — 백그라운드 작업 상태 폴링."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.job_service import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def job_status(job_id: str):
    """작업 상태 조회. 프론트엔드가 2초 간격으로 폴링.

    보안: error_json 에 포함된 ``traceback`` 키는 내부 파일 경로·모듈명·라이브러리
    버전을 노출하므로 클라이언트 응답에서 제거한다 (DB 에는 내부 디버깅용 보존).
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    # Strip internal traceback from client-facing response
    if job.get("error_json") and isinstance(job["error_json"], dict):
        job["error_json"] = {
            k: v for k, v in job["error_json"].items() if k != "traceback"
        }
    return job
