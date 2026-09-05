"""T3 — 채팅 응답 계약 + 인사 fast-path + ZZ 정규화 통합 테스트.

실제 LLM/임베더/Qdrant 없이 채팅 경로의 순수 계약을 검증한다.
"""
from __future__ import annotations

from backend.app.models.schemas import ChatResponse, PolicyInfo, SourceItem
from backend.app.api import chat_pipeline
from backend.app.services.normalizer import preprocess_for_chunking


def test_chat_response_contract():
    """백엔드 채팅 응답이 명시적 Pydantic 모델(ChatResponse)로 직렬화됨 (T1)."""
    resp = ChatResponse(
        answer="하나님은 사랑이십니다.",
        sources=[SourceItem(id="src1", text="요한일서 4장 8절", score=0.91)],
        policy=PolicyInfo(input_allowed=True, reason="clean"),
        llm_provider="nvidia",
        llm_model="nemotron",
        embedder="kure",
        elapsed_ms=123,
    )
    assert resp.answer
    assert isinstance(resp.sources, list) and resp.sources[0].score > 0.9
    assert resp.policy.input_allowed is True
    dumped = resp.model_dump()
    assert {"answer", "sources", "policy", "llm_provider", "target_lang"} <= set(dumped.keys())


def test_greeting_fastpath_true():
    assert chat_pipeline.is_greeting_or_smalltalk("안녕하세요") is True
    assert chat_pipeline.is_greeting_or_smalltalk("감사합니다") is True
    assert chat_pipeline.is_greeting_or_smalltalk("你好") is True
    assert chat_pipeline.is_greeting_or_smalltalk("hello") is True


def test_greeting_fastpath_false_for_real_question():
    assert chat_pipeline.is_greeting_or_smalltalk("하나님의 사랑은 무엇인가요?") is False
    # 인사 뒤 실제 질문이 오면 매치되지 않아 RAG 경로로 안전하게 fallback
    assert chat_pipeline.is_greeting_or_smalltalk("안녕하세요 하나님의 사랑이란?") is False


def test_greeting_fastpath_rejects_long_text():
    assert chat_pipeline.is_greeting_or_smalltalk("안녕" * 20) is False
    assert chat_pipeline.is_greeting_or_smalltalk("") is False


def test_zz_preprocess_inserts_periods_and_fixes_spacing():
    """ZZ-1(단어결합) + ZZ-3(마침표 추정)가 STT 원고에 적용됨."""
    stt = "하나님 의 말씀은 은혜입니다 그런데 많은 이들이 믿음을 얻지 못합니다"
    out = preprocess_for_chunking(stt)
    assert ". " in out, "문장 끝 마침표가 삽입되어야 함 (ZZ-3)"
    assert "하나님 의" in out, "이미 단일 공백인 조사 경계는 보존됨 (ZZ-1)"
