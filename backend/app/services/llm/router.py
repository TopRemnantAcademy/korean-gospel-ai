"""사용자 신호 분류 라우터 — classify_user_signal 단일 책임.

chat.py 의 주 대화 흐름에서 호출.
DeepSeek 우선 + fallback chain 으로 JSON 응답을 강제한다.

미사용 함수(auto_tag_document, summarize_history, judge_output_strict)는
ORDERS.md C4 결정에 따라 삭제됨 — 필요 시 각 서비스(cleanup, memory, safety)에 재구현.
"""
from __future__ import annotations
import json

from .fallback import chat_with_fallback
from .base import Message

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create llm router.py for C4
# Reason: 사용자의 질문/상태를 분류하거나 문서를 자동 태깅하는 고급 LLM 작업 분리
# Related: backend/app/api/chat.py
# Status: COMPLETED
# =============================================================================

async def _call_llm_json(system_prompt: str, user_text: str) -> dict:
    """JSON 출력을 강제하는 헬퍼 함수"""
    messages = [Message(role="user", content=user_text)]
    # C4 요구사항: DeepSeek 우선, 없으면 fallback (Gemini 등)
    # primary_provider를 "deepseek"로 고정하되, fallback chain에 의해 없으면 넘어감
    resp, llm, _ = await chat_with_fallback(
        messages,
        primary_provider="deepseek",
        system=system_prompt + "\n\n반드시 JSON 형식으로만 응답하세요. 백틱(```json) 없이 순수 JSON 텍스트만 출력하세요.",
        temperature=0.1,
        max_tokens=1000
    )
    
    text = resp.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except Exception:
        return {}

async def classify_user_signal(text: str) -> dict:
    """DeepSeek로 사용자 발화에서 신호 추출.
    Returns {emotional_state, journey_hint, faith_hint, urgency, key_topics[]}.
    """
    sys_prompt = """당신은 사용자 발화를 분석하여 영적/정서적 상태를 추출하는 분석가입니다.
추출할 필드:
- emotional_state: calm, anxious, grieving, curious, hopeful, distressed 중 하나
- journey_hint: exploring, hurting, healing, growing, mentoring 중 하나 (명확할 때만)
- faith_hint: seeker, new_believer, growing, leader, darakbang 중 하나 (명확할 때만)
- urgency: 1~5 (5가 가장 위급)
- key_topics: 주요 관심사 키워드 배열

JSON으로만 응답하세요."""
    return await _call_llm_json(sys_prompt, text)

