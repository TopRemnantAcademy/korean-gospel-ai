"""EPIC G-1: 사용자 입력 4차원 분류기.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-1 — classify_input() 구현 (Gemini JSON mode + 범용 fallback)
# Reason: ORDERS_COUNSELING.md G-1 — 상담 품질 차원 분류 (clarity/tone/spiritual_error/risk_level)
# Related: models/schemas.py (Enum 추가), prompts/classifier.py (NEW), api/chat.py (MODIFY)
# Status: COMPLETED
# =============================================================================
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
import time
from typing import Optional

from ..models.schemas import Clarity, InputClassification, RiskLevel, SpiritualError, Tone
from ..prompts.classifier import CLASSIFIER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_FALLBACK = InputClassification(
    clarity=Clarity.clear,
    tone=Tone.calm,
    spiritual_error=SpiritualError.none,
    risk_level=RiskLevel.low,
    rationale="fallback — 분류 실패",
)

_TIMEOUT_SECONDS = 3.0


def _parse_json(text: str) -> Optional[InputClassification]:
    """LLM 응답 텍스트에서 JSON 추출 후 InputClassification 파싱."""
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
        return InputClassification(
            clarity=Clarity(data.get("clarity", "clear")),
            tone=Tone(data.get("tone", "calm")),
            spiritual_error=SpiritualError(data.get("spiritual_error", "none")),
            risk_level=RiskLevel(data.get("risk_level", "low")),
            rationale=str(data.get("rationale", "")),
        )
    except (ValueError, KeyError):
        return None


async def classify_input(query: str, target_lang: str = "ko") -> InputClassification:
    """사용자 입력을 4차원으로 분류 (clarity / tone / spiritual_error / risk_level).

    - Gemini JSON mode 우선 시도 (response_mime_type=application/json)
    - 실패 시 범용 LLM(chat_with_fallback) JSON 파싱으로 재시도
    - 3초 타임아웃 초과 또는 파싱 실패 시 보수적 기본값 반환 + 로그
    """
    from .llm.factory import get_llm
    from .llm.base import Message

    user_msg = f"분류할 사용자 입력:\n{query}"

    async def _call_gemini() -> Optional[InputClassification]:
        try:
            from ..config import settings
            from google import genai
            from google.genai import types

            api_key = getattr(settings, "google_api_key", None) or getattr(settings, "gemini_api_key", None)
            if not api_key:
                return None

            client = genai.Client(api_key=api_key)
            config = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=200,
                system_instruction=CLASSIFIER_SYSTEM_PROMPT,
                response_mime_type="application/json",
            )

            def _sync_call():
                return client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[types.Content(role="user", parts=[types.Part(text=user_msg)])],
                    config=config,
                )

            resp = await asyncio.to_thread(_sync_call)
            return _parse_json(resp.text or "")
        except Exception as e:
            logger.debug("classifier gemini call failed: %s", e)
            return None

    async def _call_fallback_llm() -> Optional[InputClassification]:
        try:
            from .llm.fallback import chat_with_fallback
            resp, _, _ = await chat_with_fallback(
                [Message(role="user", content=user_msg)],
                system=CLASSIFIER_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=200,
            )
            return _parse_json(resp.text or "")
        except Exception as e:
            logger.debug("classifier fallback llm call failed: %s", e)
            return None

    try:
        result = await asyncio.wait_for(_call_gemini(), timeout=_TIMEOUT_SECONDS)
        if result is not None:
            return result

        result = await asyncio.wait_for(_call_fallback_llm(), timeout=_TIMEOUT_SECONDS)
        if result is not None:
            return result
    except asyncio.TimeoutError:
        logger.warning("classify_input timeout (>%.1fs) — using fallback", _TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning("classify_input error: %s — using fallback", e)

    _emit_fallback_event()
    return _FALLBACK


def _emit_fallback_event() -> None:
    """Langfuse classifier_fallback 이벤트 — trace 컨텍스트 없이 호출되므로 best-effort."""
    try:
        from .tracing import get_client
        lf = get_client()
        if lf:
            lf.event(name="classifier_fallback")  # type: ignore[attr-defined]
    except Exception:
        pass
