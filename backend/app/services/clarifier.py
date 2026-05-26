"""EPIC G-2: 재질문 생성기 — clarity=ambiguous 일 때 호출.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-2 — generate_clarifying_question() 구현
# Reason: ORDERS_COUNSELING.md G-2 — 모호한 질문에 추측 답하지 않고 재질문 반환
# Related: prompts/clarifier.py (NEW), api/chat.py (MODIFY)
# Status: COMPLETED
# =============================================================================
"""
from __future__ import annotations
import logging

from ..models.schemas import InputClassification
from ..prompts.clarifier import get_clarifier_prompt

logger = logging.getLogger(__name__)

# 언어별 기본 재질문 (LLM 호출 실패 시 fallback)
_FALLBACK_QUESTION = {
    "ko": "어떤 상황에서 그런 마음이 드시는지 조금 더 말씀해 주시겠습니까?",
    "en": "Could you share a little more about the situation you are facing?",
    "zh": "请问您是在哪种情况下有这样的感受,能再告诉我一些吗?",
}


async def generate_clarifying_question(
    query: str,
    classification: InputClassification,
    target_lang: str = "ko",
) -> str:
    """모호한 질문에 대한 재질문 1~2문장을 생성한다.

    LLM 호출 실패 시 언어별 기본 재질문을 반환한다.
    """
    from .llm.fallback import chat_with_fallback
    from .llm.base import Message

    system_prompt = get_clarifier_prompt(target_lang)
    user_msg = f"사용자 질문: {query}"

    try:
        resp, _, _ = await chat_with_fallback(
            [Message(role="user", content=user_msg)],
            system=system_prompt,
            temperature=0.3,
            max_tokens=150,
        )
        text = (resp.text or "").strip()
        if text and "?" in text:
            return text
        # 물음표 없으면 기본값 — LLM 이 지시를 무시한 경우
        logger.warning("clarifier: LLM response missing '?' — using fallback")
    except Exception as e:
        logger.warning("clarifier: LLM call failed (%s) — using fallback", e)

    return _FALLBACK_QUESTION.get(target_lang, _FALLBACK_QUESTION["ko"])
