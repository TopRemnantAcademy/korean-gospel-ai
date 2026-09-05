"""P4 #8 — 신고/오류 제보 시스템 단위 테스트 (순수 헬퍼)."""
from starlette.requests import Request

from backend.app.api.support import _dedup_hash, _fingerprint, _ALLOWED_TYPES


def _make_request(client_host: str = "5.6.7.8") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/support/tickets",
            "headers": [],
            "client": (client_host, 1234),
            "query_string": b"",
        }
    )


def test_dedup_hash_stable_and_distinct():
    h1 = _dedup_hash("bug", "msg-1", "앱이 터집니다")
    h2 = _dedup_hash("bug", "msg-1", "앱이 터집니다")
    assert h1 == h2  # 동일 입력 → 동일 해시
    h3 = _dedup_hash("bug", "msg-1", "다른 내용")
    assert h1 != h3  # 내용 다르면 해시 다름


def test_fingerprint_prefers_sub_id():
    req = _make_request()
    assert _fingerprint("anon-123", req) == "sub:anon-123"
    assert _fingerprint(None, req) == "ip:5.6.7.8"


def test_allowed_types():
    assert _ALLOWED_TYPES == {"bug", "report", "abuse", "error", "other"}
