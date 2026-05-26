"""EPIC G-4.6: 아첨금지 Layer C — 자동 재생성 루프 (1회 제한).
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-4.6 — regenerate_strict() 구현 (1회 재시도, fail-open)
# Reason: ORDERS_COUNSELING.md G-4.6 — 검출만 하고 손쓰지 않으면 무의미;
#         단 무한 재생성은 비용 폭발 → 1회 제한
# Related: services/flattery_filter.py (Layer A), services/policy.py (Layer B),
#          prompts/system.py (build_strict_addendum)
# Status: COMPLETED
# =============================================================================
"""
from __future__ import annotations
import logging
from typing import Optional

from .llm.base import Message

logger = logging.getLogger(__name__)


async def regenerate_strict(
    messages: list[Message],
    system_prompt: str,
    target_lang: str,
    violation_flags: list[str],
    primary_provider: Optional[str] = None,
) -> tuple[str, str]:
    """위반 답변을 STRICT 모드로 1회 재생성한다.

    Returns:
        (new_text, status) — status: "ok" | "regen_failed" | "regen_error"
    """
    from .llm.fallback import chat_with_fallback
    from .flattery_filter import check_flattery
    from .policy import judge_output
    from ..prompts.system import build_strict_addendum

    strict_addendum = build_strict_addendum(violation_flags, target_lang)
    strict_system = system_prompt + strict_addendum

    try:
        resp, _, _ = await chat_with_fallback(
            messages,
            primary_provider=primary_provider,
            system=strict_system,
            temperature=0.2,   # 재생성은 더 낮은 temperature 로 절제 강화
            max_tokens=1500,
        )
        new_text = resp.text or ""

        # 재생성 결과를 Layer A + B 재검사
        filter_result = check_flattery(new_text, target_lang)
        judge_result = await judge_output("", new_text, target_lang)  # question 은 이미 검사됨

        if not filter_result.violated and not judge_result.violation_flags:
            logger.info("regen: succeeded (violations cleared)")
            return new_text, "ok"

        logger.warning("regen: still violated after retry — fail open, returning original+mark")
        return new_text, "regen_failed"

    except Exception as e:
        logger.error("regen: error during regeneration: %s", e)
        return "", "regen_error"
