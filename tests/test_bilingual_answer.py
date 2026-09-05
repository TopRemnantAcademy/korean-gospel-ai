"""이중언어 병기 답변(bilingual) 스키마/헬퍼 단위 테스트."""
import asyncio

from backend.app.models.schemas import ChatRequest, ChatResponse, PolicyInfo
from backend.app.api import chat as chat_module


def test_schemas_accept_bilingual_fields():
    req = ChatRequest(query="안녕하세요", bilingual=True)
    assert req.bilingual is True

    resp = ChatResponse(
        answer="你好",
        sources=[],
        policy=PolicyInfo(input_allowed=True),
        llm_provider="nvidia",
        llm_model="m",
        embedder="none",
        elapsed_ms=1,
        answer_parallel="안녕하세요",
    )
    assert resp.answer_parallel == "안녕하세요"


def test_translate_to_korean_uses_fallback(monkeypatch):
    class _FakeResp:
        text = "안녕하세요"

    async def _fake_fallback(messages, **kw):
        return _FakeResp(), "nvidia", 1

    monkeypatch.setattr(chat_module, "chat_with_fallback", _fake_fallback)

    out = asyncio.run(chat_module._translate_to_korean("你好", "zh"))
    assert out == "안녕하세요"


def test_translate_to_korean_ko_is_noop_and_failure_none(monkeypatch):
    calls = {"n": 0}

    async def _fake_fallback(messages, **kw):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_module, "chat_with_fallback", _fake_fallback)

    # ko 입력은 LLM 호출 없이 None
    assert asyncio.run(chat_module._translate_to_korean("hi", "ko")) is None
    assert calls["n"] == 0

    # 실패 시에도 None (본문만 반환, 안전)
    assert asyncio.run(chat_module._translate_to_korean("你好", "zh")) is None
