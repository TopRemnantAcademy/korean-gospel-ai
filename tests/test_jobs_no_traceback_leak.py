"""회귀 테스트: GET /jobs/{job_id} 응답에서 traceback 노출 방지.

보안 결함: error_json 에 포함된 2000자 traceback 이 무인증으로 클라이언트에
반환되어 내부 파일 경로/모듈명/라이브러리 버전을 노출하던 문제 수정.
"""
from __future__ import annotations

from backend.app.api import jobs as jobs_module
from backend.app.api.jobs import job_status


def test_traceback_stripped_from_response(monkeypatch):
    """error_json 의 traceback 키는 응답에서 제거되어야 한다."""
    fake_job = {
        "job_id": "test-job-123",
        "job_type": "ingest",
        "status": "failed",
        "current_stage": "processing",
        "stage_detail": "error during embed",
        "progress_pct": 45,
        "result_json": None,
        "error_json": {
            "error": "ConnectionError: Qdrant unreachable",
            "traceback": "Traceback (most recent call last):\n  File '/app/backend/...'",
        },
        "created_at": "2026-07-23T00:00:00",
        "updated_at": "2026-07-23T00:01:00",
    }
    monkeypatch.setattr(jobs_module, "get_job", lambda jid: fake_job)
    result = job_status("test-job-123")
    assert "error_json" in result
    assert "traceback" not in result["error_json"], "traceback must not leak to client"
    assert "error" in result["error_json"], "non-traceback keys must be preserved"


def test_error_message_preserved(monkeypatch):
    """error 키(사용자용 메시지)는 보존되어야 한다."""
    fake_job = {
        "job_id": "j2",
        "job_type": "ingest",
        "status": "failed",
        "current_stage": "",
        "stage_detail": "",
        "progress_pct": 0,
        "result_json": None,
        "error_json": {"error": "timeout", "traceback": "long trace"},
        "created_at": None,
        "updated_at": None,
    }
    monkeypatch.setattr(jobs_module, "get_job", lambda jid: fake_job)
    result = job_status("j2")
    assert result["error_json"]["error"] == "timeout"


def test_no_error_json_passes_through(monkeypatch):
    """error_json 이 None 이면 응답도 그대로 None."""
    fake_job = {
        "job_id": "j3",
        "job_type": "ingest",
        "status": "completed",
        "current_stage": "done",
        "stage_detail": "",
        "progress_pct": 100,
        "result_json": {"doc_id": "abc"},
        "error_json": None,
        "created_at": None,
        "updated_at": None,
    }
    monkeypatch.setattr(jobs_module, "get_job", lambda jid: fake_job)
    result = job_status("j3")
    assert result["error_json"] is None
    assert result["status"] == "completed"


def test_empty_error_json_handled(monkeypatch):
    """error_json 이 빈 딕셔너리여도 정상 처리."""
    fake_job = {
        "job_id": "j4",
        "job_type": "ingest",
        "status": "running",
        "current_stage": "",
        "stage_detail": "",
        "progress_pct": 10,
        "result_json": None,
        "error_json": {},
        "created_at": None,
        "updated_at": None,
    }
    monkeypatch.setattr(jobs_module, "get_job", lambda jid: fake_job)
    result = job_status("j4")
    assert result["error_json"] == {}
