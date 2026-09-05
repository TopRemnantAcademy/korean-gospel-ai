"""BUG-09 후속 회귀 테스트: /admin/subscribers/list 의 limit/offset/total 반영 검증.

환경(DB)과 무관하게 응답 스키마(limit/offset/total 필드)와
상한 캡(limit<=10000)이 지켜지는지 잠근다. 인증 누락 시 401/403 거부도 검증.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _admin_headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def test_subscribers_list_returns_pagination_fields(client):
    orig = settings.admin_api_key
    settings.admin_api_key = "test-admin-key"
    try:
        r = client.get(
            "/admin/subscribers/list?limit=5&offset=0",
            headers=_admin_headers("test-admin-key"),
        )
        assert r.status_code == 200
        body = r.json()
        assert "subscribers" in body
        assert body["limit"] == 5
        assert body["offset"] == 0
        assert isinstance(body["total"], int)
        assert len(body["subscribers"]) <= body["limit"]
    finally:
        settings.admin_api_key = orig


def test_subscribers_list_limit_cap(client):
    orig = settings.admin_api_key
    settings.admin_api_key = "test-admin-key"
    try:
        # BUG-09: limit 상한(le=10000) 초과 시 422 거부
        r = client.get(
            "/admin/subscribers/list?limit=10001&offset=0",
            headers=_admin_headers("test-admin-key"),
        )
        assert r.status_code == 422
        # 경계값 10000 은 정상 수용
        r2 = client.get(
            "/admin/subscribers/list?limit=10000&offset=0",
            headers=_admin_headers("test-admin-key"),
        )
        assert r2.status_code == 200
        assert r2.json()["limit"] == 10000
    finally:
        settings.admin_api_key = orig


def test_subscribers_list_rejects_missing_auth(client):
    orig = settings.admin_api_key
    settings.admin_api_key = "test-admin-key"
    try:
        r = client.get("/admin/subscribers/list")
        assert r.status_code in (401, 403)
    finally:
        settings.admin_api_key = orig
