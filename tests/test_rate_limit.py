"""P4 #3 — Rate limit 견고화 회귀 테스트 (XFF 인지 + 경로 커버)."""
from starlette.requests import Request

from backend.app.middleware.rate_limit import (
    _real_client_ip,
    _is_rate_path,
    _hit,
    _count,
)


def _make_request(headers: dict, client_host: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/chat",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 1234),
        "query_string": b"",
    }
    return Request(scope)


def test_rate_path_covers_ingest_admin_documents():
    assert _is_rate_path("/chat")
    assert _is_rate_path("/chat/stream")
    assert _is_rate_path("/auth/login")
    assert _is_rate_path("/rag/ingest")
    assert _is_rate_path("/admin/content")
    assert _is_rate_path("/documents")
    assert not _is_rate_path("/health")
    assert not _is_rate_path("/ready")


def test_real_client_ip_from_x_forwarded_for():
    # X-Forwarded-For: 9.9.9.9(위조 가능한 최좌측), 10.0.0.1(신뢰 프록시가 붙인 최우측)
    # 보안 원칙: 신뢰 프록시 모드에선 최우측 hop 을 실제 클라이언트로 간주 → 10.0.0.1
    req = _make_request({"X-Forwarded-For": "9.9.9.9, 10.0.0.1"})
    assert _real_client_ip(req) == "10.0.0.1"


def test_real_client_ip_fallback_to_client_host():
    req = _make_request({})  # XFF 없음
    assert _real_client_ip(req) == "1.2.3.4"


def test_in_memory_count_hit():
    key = "ip_min:test_user_123"
    # 초기화
    _count(key, 60)
    _hit(key, 60)
    _hit(key, 60)
    _hit(key, 60)
    assert _count(key, 60) == 3
