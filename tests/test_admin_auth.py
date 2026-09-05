"""P0-3 / P0-4 — 관리자 인증 게이트 및 /ready 엔드포인트 기능 테스트.

기존 enhanced_rag 테스트는 파이프라인 내부(청킹/BM25/융합)만 다루고,
HTTP 인증 계층(require_admin → 401/503)과 /ready 를 전혀 검증하지 않았다.
이 테스트는 그 보안 제어가 실제로 동작함을 CI 에서 잠근다.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.api.enhanced_rag import require_admin


# ── P0-4: /ready 엔드포인트 ────────────────────────────────────────────────
def test_ready_endpoint_structure():
    from backend.app.main import app

    c = TestClient(app)
    r = c.get("/ready")
    # /ready 는 레디니스 프로브 — 준비 완료(200) 또는 미준비(503) 모두 유효한 상태.
    # (컬렉션이 비어있거나 LLM 키가 없으면 의도적으로 503 을 반환)
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["status"] in ("ready", "not_ready")
    # ready → version 포함, not_ready → problems 포함 (둘 중 하나는 반드시 존재)
    assert "version" in body or "problems" in body


# ── P0-3: require_admin 의존성 로직 (모델 로딩 없이 빠르게) ──────────────────
def test_require_admin_rejects_missing_key():
    orig = settings.admin_api_key
    settings.admin_api_key = "configured-secret"  # .env 처럼 실제 키가 설정된 상태
    try:
        with pytest.raises(HTTPException) as exc:
            require_admin(x_api_key=None)
        assert exc.value.status_code == 401
    finally:
        settings.admin_api_key = orig


def test_require_admin_rejects_wrong_key():
    orig = settings.admin_api_key
    settings.admin_api_key = "configured-secret"
    try:
        with pytest.raises(HTTPException) as exc:
            require_admin(x_api_key="totally-wrong")
        assert exc.value.status_code == 401
    finally:
        settings.admin_api_key = orig


def test_require_admin_fail_closed_on_default_key():
    """ADMIN_API_KEY 가 비어있거나 'change-me' 이면 무조건 503 (인증 우회 방지)."""
    orig = settings.admin_api_key
    settings.admin_api_key = "change-me"
    try:
        with pytest.raises(HTTPException) as exc:
            require_admin(x_api_key="change-me")
        assert exc.value.status_code == 503
    finally:
        settings.admin_api_key = orig


def test_require_admin_passes_with_correct_key():
    orig = settings.admin_api_key
    settings.admin_api_key = "configured-secret"
    try:
        # 정상 키 → 의존성은 None 을 반환(게이트 통과)
        assert require_admin(x_api_key="configured-secret") is None
    finally:
        settings.admin_api_key = orig


# ── P0-3: 실제 /rag/* 라우트가 키 없이 200 을 절대 반환하지 않음 ─────────────
def test_rag_endpoints_denied_without_key():
    from backend.app.main import app

    c = TestClient(app)
    # .env 에 ADMIN_API_KEY 가 설정돼 있으면 401, 미설정/change-me 면 503.
    # 어느 쪽이든 200 이 나오면 인증 게이트가 뚫린 것.
    r = c.get("/rag/documents")
    assert r.status_code in (401, 503), f"예상치 못한 상태: {r.status_code}"
    assert r.status_code != 200
