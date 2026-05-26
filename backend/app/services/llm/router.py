"""멀티 LLM 협업 라우터 — 사용자 신호 분류, 문서 자동 태깅, 대화 요약, 출력 검증.

chat.py 의 주 대화 흐름에서 호출되는 보조 판단 레이어.
DeepSeek 우선 + fallback chain 을 통해 JSON 구조 응답을 강제한다.
"""
from __future__ import annotations
import json
from typing import Dict, Any

from .fallback import chat_with_fallback
from .base import Message
from ...config import settings

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

async def auto_tag_document(text: str, doc_type: str) -> dict:
    """DeepSeek로 자료 자동 메타 제안.
    Returns {target_audience[], target_stage[], emotion_tone, difficulty, suggested_tags[], suggested_refs[]}.
    """
    sys_prompt = f"""당신은 {doc_type} 문서를 분석하여 대상과 태그를 추출하는 기독교 문서 분류가입니다.
추출할 필드:
- target_audience: ["seeker", "new_believer", "growing", "leader", "darakbang"] 중 해당되는 것 배열
- target_stage: ["exploring", "hurting", "healing", "growing", "mentoring"] 중 배열
- emotion_tone: comforting, challenging, teaching, worship, prophetic 중 하나
- difficulty: 1~5 (초신자용 1, 신학적/심화 5)
- suggested_tags: 자유로운 태그 배열
- suggested_refs: 성경 구절 참조 배열 (예: ["John 3:16"])

JSON으로만 응답하세요."""
    return await _call_llm_json(sys_prompt, text[:3000]) # 앞부분만으로 판단

async def summarize_history(messages: list) -> str:
    """장기 대화 메모리 압축 (DeepSeek)."""
    text_msgs = []
    for m in messages:
        text_msgs.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
    history_text = "\n".join(text_msgs)
    
    sys_prompt = "다음 대화 내용을 핵심 주제와 사용자의 상태 변화 중심으로 3문장 이내로 요약하세요."
    messages_llm = [Message(role="user", content=history_text)]
    resp, _, _ = await chat_with_fallback(
        messages_llm,
        primary_provider="deepseek",
        system=sys_prompt,
        temperature=0.3,
        max_tokens=500
    )
    return resp.text

async def judge_output_strict(question: str, answer: str, profile: dict = None) -> dict:
    """DeepSeek-judge — Gemini judge 보완 또는 대체."""
    sys_prompt = "당신은 기독교 AI의 답변을 평가하는 엄격한 평가자입니다. 답변이 이단적이거나, 공격적이거나, 성경과 어긋나면 pass: false를 반환하세요."
    user_prompt = f"질문: {question}\n\n답변: {answer}\n\n결과를 JSON으로 반환하세요. {{'pass': boolean, 'score': 1~10, 'notes': '이유'}}"
    return await _call_llm_json(sys_prompt, user_prompt)
