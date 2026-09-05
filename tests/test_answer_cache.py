"""P4 #1 — 생성 답변 캐시(정규화 키 + TTL) 회귀 테스트."""
import time

from backend.app.services.answer_cache import normalize_query, set_answer, get_answer


def test_normalize_query_strips_punctuation_and_case():
    assert normalize_query("  Hello, World!  ") == "hello world"
    assert normalize_query("기도해줘!!!  ") == "기도해줘"
    assert normalize_query("  여러 칸   공백  ") == "여러 칸 공백"


def test_set_get_roundtrip_in_memory():
    key = "answer_cache:기도해줘:ko"
    payload = {"answer": "기도는 마음을 주님께 여는 것입니다.", "sources": []}
    set_answer(key, payload, ttl=600)
    got = get_answer(key)
    assert got is not None
    assert got["answer"] == payload["answer"]


def test_expired_entry_returns_none():
    key = "answer_cache:만료테스트:ko"
    set_answer(key, {"answer": "x"}, ttl=0)
    # ttl=0 이면 즉시 만료 처리
    time.sleep(0.01)
    assert get_answer(key) is None


def test_redis_unavailable_falls_back_to_memory(monkeypatch):
    # redis_url 미설정 → 메모리 캐시 경로
    from backend.app import config as _cfg

    monkeypatch.setattr(_cfg.settings, "redis_url", None)
    key = "answer_cache:redisfallback:en"
    set_answer(key, {"answer": "hi"}, ttl=60)
    assert get_answer(key)["answer"] == "hi"
