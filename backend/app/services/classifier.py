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
from typing import Optional

from ..models.schemas import Clarity, InputClassification, RiskLevel, SpiritualError, Tone
from ..prompts.classifier import CLASSIFIER_SYSTEM_PROMPT, CLASSIFIER_LANG_HINT
from .cache_utils import AsyncLRUCache

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


_classification_cache = AsyncLRUCache(max_size=2000, ttl_seconds=3600)  # 1시간 TTL, 최대 2000개


async def classify_input(query: str, target_lang: str = "ko") -> InputClassification:
    """사용자 입력을 4차원으로 분류 (clarity / tone / spiritual_error / risk_level).

    - Gemini JSON mode 우선 시도 (response_mime_type=application/json)
    - 실패 시 범용 LLM(chat_with_fallback) JSON 파싱으로 재시도
    - 3초 타임아웃 초과 또는 파싱 실패 시 보수적 기본값 반환 + 로그
    """
    norm_query = query.strip()

    system_prompt = CLASSIFIER_SYSTEM_PROMPT
    lang_hint = CLASSIFIER_LANG_HINT.get(target_lang, "")
    if lang_hint:
        system_prompt += lang_hint

    cache_key = (norm_query, target_lang)
    cached = await _classification_cache.get(cache_key)
    if cached is not None:
        return cached

    # Fast-path: 8자 미만이고 분류/상담 관심 키워드가 없으면 LLM 호출 생략 후 fallback 반환
    clean_q = norm_query.strip()
    if len(clean_q) < 8:
        classification_keywords = {
            # 한국어
            "구원", "예수", "하나님", "교회", "의심", "믿음", "천국", "지옥", "죽음",
            "죄", "회개", "영접", "확신", "짜증", "싫어", "화나", "죽고", "힘들", "슬퍼",
            # 영어
            "jesus", "god", "sin", "faith", "salvation", "church", "heaven", "hell",
            "pray", "bible", "hurt", "die", "kill", "sad", "fear", "anxi",
            # 중국어
            "耶稣", "上帝", "罪", "救恩", "天堂", "地狱", "教会", "祷告", "圣经",
            # 일본어
            "イエス", "神", "罪", "救い", "天国", "地獄", "教会", "祈り", "聖書",
        }
        if not any(kw.lower() in clean_q.lower() for kw in classification_keywords):
            return _FALLBACK

    from .llm.base import Message

    user_msg = f"분류할 사용자 입력:\n{query}"

    async def _call_gemini() -> Optional[InputClassification]:
        try:
            from ..config import settings
            from google import genai
            from google.genai import types
            from ..connections import connections

            client = connections.gemini()
            if not client:
                api_key = getattr(settings, "google_api_key", None) or getattr(settings, "gemini_api_key", None)
                if not api_key:
                    return None
                client = genai.Client(api_key=api_key)

            config = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=200,
                system_instruction=system_prompt,
                response_mime_type="application/json",
            )

            resp = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[types.Content(role="user", parts=[types.Part(text=user_msg)])],
                config=config,
            )
            return _parse_json(resp.text or "")
        except Exception as e:
            logger.debug("classifier gemini call failed: %s", e)
            return None

    async def _call_fallback_llm() -> Optional[InputClassification]:
        try:
            from .llm.fallback import chat_with_fallback
            resp, _, _ = await chat_with_fallback(
                [Message(role="user", content=user_msg)],
                system=system_prompt,
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
            await _classification_cache.set(cache_key, result)
            return result

        result = await asyncio.wait_for(_call_fallback_llm(), timeout=_TIMEOUT_SECONDS)
        if result is not None:
            await _classification_cache.set(cache_key, result)
            return result
    except asyncio.TimeoutError:
        logger.warning("classify_input timeout (>%.1fs) — using fallback", _TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning("classify_input error: %s — using fallback", e)

    _emit_fallback_event()
    return _FALLBACK


def _emit_fallback_event() -> None:
    """Langfuse classifier_fallback 이벤트 — trace 컨텍스트 없이 호출되므로 best-effort."""
    logger.warning("classify_input fallback event triggered")
    try:
        from .tracing import get_client
        lf = get_client()
        if lf:
            if hasattr(lf, "event"):
                lf.event(name="classifier_fallback")  # type: ignore[attr-defined]
            elif hasattr(lf, "trace"):
                lf.trace(name="classifier_fallback").update(status_message="classifier fallback triggered")
    except Exception as e:
        logger.debug("Failed to emit fallback tracing event: %s", e)
