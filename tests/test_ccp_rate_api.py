"""CCP 원가 단가(rate card) 관리 API 테스트.

① 사용자 요청: 실제 LLM 단가 + 환율 기준일을 Admin Hub UI 에서 직접 입력.
이 테스트는 해당 UI 가 호출하는 백엔드 REST API(GET/POST /admin/ccp/rates)가
인증 게이트와 SCD Type 2 이력 보존(기존 구간 종료 + 신규 구간 개시)을 올바르게
수행하는지 검증한다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings


@pytest.fixture
def client():
    from backend.app.main import app

    return TestClient(app)


@pytest.fixture
def admin_headers():
    """check_admin 은 Authorization: Bearer 를 수용한다 (X-API-Key 는 query 파라미터로 바인딩됨)."""
    orig = settings.admin_api_key
    settings.admin_api_key = "test-admin-key"
    try:
        yield {"Authorization": f"Bearer test-admin-key"}
    finally:
        settings.admin_api_key = orig


def test_list_requires_auth(client):
    r = client.get("/admin/ccp/rates")
    assert r.status_code in (401, 403, 503)


def test_create_requires_auth(client):
    r = client.post(
        "/admin/ccp/rates",
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "input_price_per_1k": 0.3,
            "output_price_per_1k": 1.0,
            "currency": "KRW",
            "source_note": "probe",
        },
    )
    assert r.status_code in (401, 403, 503)


def test_create_and_list_rate(client, admin_headers):
    payload = {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "input_price_per_1k": 0.3,
        "output_price_per_1k": 1.0,
        "currency": "KRW",
        "source_note": "Google 가격표 2026-08-03, 환율 1USD=1380KRW 기준 2026-08-01",
    }
    r = client.post("/admin/ccp/rates", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider"] == "gemini"
    assert body["rate_card_id"]
    assert body["effective_to"] is None  # 현재 유효

    # 목록 조회
    lst = client.get("/admin/ccp/rates", headers=admin_headers)
    assert lst.status_code == 200
    rows = lst.json()
    assert any(x["rate_card_id"] == body["rate_card_id"] for x in rows)


def test_scd_type2_closes_previous(client, admin_headers):
    """동일 (provider, model) 신규 단가 추가 시 기존 유효 구간이 종료된다."""
    base = {
        "provider": "nvidia",
        "model": "nv-small",
        "input_price_per_1k": 0.1,
        "output_price_per_1k": 0.2,
        "currency": "KRW",
        "source_note": "probe v1",
    }
    r1 = client.post("/admin/ccp/rates", json=base, headers=admin_headers)
    assert r1.status_code == 201
    id1 = r1.json()["rate_card_id"]

    r2 = client.post(
        "/admin/ccp/rates",
        json={**base, "output_price_per_1k": 0.25, "source_note": "probe v2"},
        headers=admin_headers,
    )
    assert r2.status_code == 201
    id2 = r2.json()["rate_card_id"]
    assert id1 != id2

    lst = client.get("/admin/ccp/rates", headers=admin_headers).json()
    ids = {x["rate_card_id"] for x in lst}
    # 목록 조회는 현재 유효 구간(effective_to IS NULL)만 반환 → 신규 id2 만 노출
    assert id2 in ids
    assert id1 not in ids  # 구구간은 SCD Type 2 로 종료되어 목록에서 제외
