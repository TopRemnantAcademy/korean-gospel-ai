"""LLM provider fallback — rate limit·일시 장애 시 체인의 다음 provider로 재시도.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: N1 — stream_with_fallback 첫 chunk probe (fallback 실효성 복원)
#       N14 — llm_fallback_enabled=False 우회 버그 수정 (skip or (...) → (skip or retryable) and ...)
# Reason: ORDERS.md N1, N14
# Status: COMPLETED
# =============================================================================
"""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator, Optional

from ...config import settings
from .base import BaseLLM, LLMResponse, Message
from .factory import get_llm

logger = logging.getLogger(__name__)

_RETRYABLE_RE = re.compile(
    r"rate.?limit|429|503|502|504|resource.?exhausted|quota|overloaded|"
    r"too many requests|capacity|unavailable|deadline exceeded|high demand",
    re.IGNORECASE,
)

_ALL_PROVIDERS = ("gemini", "deepseek", "openai", "claude", "ollama")


def is_retryable_error(exc: BaseException) -> bool:
    """일시적·용량 관련 오류만 다음 provider로 넘긴다."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    msg = f"{type(exc).__name__}: {exc}"
    return bool(_RETRYABLE_RE.search(msg))


def provider_has_credentials(name: str) -> bool:
    name = name.lower()
    if name == "gemini":
        return bool(settings.google_api_key)
    if name == "openai":
        return bool(settings.openai_api_key)
    if name == "claude":
        return bool(settings.anthropic_api_key)
    if name == "ollama":
        return True
    if name == "deepseek":
        return bool(settings.deepseek_api_key)
    return False


def resolve_fallback_chain(primary: str | None = None) -> list[str]:
    """시도 순서. 명시 체인 > primary + 키 있는 나머지."""
    if settings.llm_fallback_chain.strip():
        names = [p.strip().lower() for p in settings.llm_fallback_chain.split(",") if p.strip()]
    else:
        first = (primary or settings.llm_provider).lower()
        names = [first]
        for p in _ALL_PROVIDERS:
            if p != first and provider_has_credentials(p):
                names.append(p)

    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        if provider_has_credentials(n):
            out.append(n)
    return out


async def chat_with_fallback(
    messages: list[Message],
    *,
    primary_provider: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1500,
    system: Optional[str] = None,
) -> tuple[LLMResponse, BaseLLM, list[str]]:
    """(응답, 사용된 LLM, 시도한 provider 목록)."""
    chain = resolve_fallback_chain(primary_provider)
    if not chain:
        raise RuntimeError("사용 가능한 LLM provider가 없습니다. .env API 키를 확인하세요.")

    errors: list[str] = []
    for i, name in enumerate(chain):
        if i > 0 and not settings.llm_fallback_enabled:
            break
        try:
            llm = get_llm(name)
            resp = await llm.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system,
            )
            if i > 0:
                logger.warning(
                    "LLM fallback: %s → %s (%s)",
                    chain[0],
                    name,
                    errors[-1] if errors else "?",
                )
            return resp, llm, chain[: i + 1]
        except Exception as e:
            skip = isinstance(e, (ValueError, ImportError))
            retryable = is_retryable_error(e)
            errors.append(f"{name}: {e}")
            if (skip or retryable) and settings.llm_fallback_enabled and i < len(chain) - 1:
                logger.info("LLM skip/fallback from %s: %s", name, e)
                continue
            raise RuntimeError(
                f"LLM 호출 실패 (시도: {', '.join(chain[: i + 1])}). "
                f"마지막 오류: {e}"
            ) from e

    raise RuntimeError(
        f"LLM 호출 실패 — 모든 provider 소진. 시도: {chain}. 상세: {' | '.join(errors)}"
    )


async def stream_with_fallback(
    messages: list[Message],
    *,
    primary_provider: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1500,
    system: Optional[str] = None,
) -> tuple[BaseLLM, AsyncIterator[str], list[str]]:
    """스트리밍 시작 전 provider 선택. 중간 끊김은 재시도하지 않음."""
    chain = resolve_fallback_chain(primary_provider)
    if not chain:
        raise RuntimeError("사용 가능한 LLM provider가 없습니다. .env API 키를 확인하세요.")

    errors: list[str] = []
    for i, name in enumerate(chain):
        if i > 0 and not settings.llm_fallback_enabled:
            break
        try:
            llm = get_llm(name)
            # N1: 첫 chunk까지 받아본 후 반환 — 연결 실패·인증 오류를 fallback 루프 안에서 잡기 위함
            agen = llm.stream(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system,
            )
            first_chunk: str | None = None
            try:
                first_chunk = await agen.__anext__()
            except StopAsyncIteration:
                pass

            async def _gen(gen=agen, first=first_chunk) -> AsyncIterator[str]:
                if first is not None:
                    yield first
                async for piece in gen:
                    yield piece

            if i > 0:
                logger.warning(
                    "LLM stream fallback: %s → %s (%s)",
                    chain[0],
                    name,
                    errors[-1] if errors else "?",
                )
            return llm, _gen(), chain[: i + 1]
        except Exception as e:
            skip = isinstance(e, (ValueError, ImportError))
            retryable = is_retryable_error(e)
            errors.append(f"{name}: {e}")
            if (skip or retryable) and settings.llm_fallback_enabled and i < len(chain) - 1:
                continue
            raise RuntimeError(f"LLM stream 실패: {e}") from e

    raise RuntimeError(f"LLM stream 실패 — provider 소진: {chain}")
