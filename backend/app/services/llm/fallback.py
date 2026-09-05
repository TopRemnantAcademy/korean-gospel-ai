"""LLM provider fallback — 실제 오류(연결 불가·잔액 부족·서버 에러) 시에만 다음 provider로 전환.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-29
# Task: F4 — 폴백 정책 재설계
#   · 비스트리밍: llm_provider_timeout_sec 내 미응답 시 다음 provider로 전환
#     (느린 응답은 폴백 사유 아님 — 완전 무응답·HTTP 에러만 폴백)
#   · 스트리밍: 첫 chunk probe 15초 유지 (무응답 감지용)
#     이후 스트리밍 중 시간 초과 없음 → 끝까지 기다림
#   · is_retryable_error: TimeoutError/asyncio.TimeoutError 제거
#     (스트리밍 첫 chunk 전용 - stream_with_fallback 에서 별도 처리)
#     ConnectionError·HTTP 오류 코드만 retryable
# =============================================================================
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
from typing import AsyncIterator, Optional

from ...config import settings
from .base import BaseLLM, LLMResponse, Message
from .factory import get_llm

logger = logging.getLogger(__name__)

_RETRYABLE_RE = re.compile(
    r"rate.?limit|429|503|502|504|resource.?exhausted|quota|overloaded|"
    r"too many requests|capacity|unavailable|deadline exceeded|high demand|"
    r"402|insufficient.?balance|payment.?required|billing|credit|no.?credit",
    re.IGNORECASE,
)

# 스트리밍: 첫 chunk 가 이 시간 안에 오지 않으면 "완전 무응답" 판정 → fallback
# OPT-SPEED: nvidia 1순위(실측 TTFT 0.48s) 기준 8s 로 단축 → 지연 폴백도 빠르게.
_FIRST_CHUNK_TIMEOUT = 8.0

_ALL_PROVIDERS = ("gemini", "deepseek", "tencent", "nvidia", "openai", "claude", "ollama")


def is_retryable_error(exc: BaseException) -> bool:
    """실제 오류(연결 불가, HTTP 에러, 잔액 부족)만 다음 provider로 넘긴다.

    ※ 단순히 느린 응답(TimeoutError)은 retryable 이 아님.
       폴백은 '완전 무응답 또는 실제 오류' 시에만 발동.
    """
    if isinstance(exc, ConnectionError):
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
    if name == "tencent":
        return bool(settings.tencent_api_key)
    if name == "nvidia":
        return bool(settings.nvidia_api_key)
    return False


def resolve_fallback_chain(primary: str | None = None) -> list[str]:
    """시도 순서. 명시 체인 > primary + 키 있는 나머지.

    명시 체인(llm_fallback_chain)이 있어도 호출자가 명시한 primary 는
    체인 맨 앞에 배치한다 (기존엔 체인이 설정되면 primary 인자를 통째로
    무시해 router.py 의 primary_provider="deepseek" 같은 의도가 묻혀버리는 버그).
    키가 없는 provider 는 아래에서 어차피 필터링되므로 안전하다.
    """
    if settings.llm_fallback_chain.strip():
        names = [
            p.strip().lower()
            for p in settings.llm_fallback_chain.split(",")
            if p.strip()
        ]
        if primary:
            p = primary.strip().lower()
            names = [p] + [n for n in names if n != p]
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
        raise RuntimeError(
            "사용 가능한 LLM provider가 없습니다. .env API 키를 확인하세요."
        )

    errors: list[str] = []
    for i, name in enumerate(chain):
        if i > 0 and not settings.llm_fallback_enabled:
            break
        try:
            llm = get_llm(name)
            # 타임아웃 복구 — settings.llm_provider_timeout_sec 내에 무응답 시 폴백
            timeout_val = float(settings.llm_provider_timeout_sec or 20.0)
            resp = await asyncio.wait_for(
                llm.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system=system,
                ),
                timeout=timeout_val,
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
            retryable = is_retryable_error(e) or isinstance(e, asyncio.TimeoutError)
            _label = (
                f"timeout>{timeout_val}s"
                if isinstance(e, asyncio.TimeoutError)
                else str(e)
            )
            errors.append(f"{name}: {_label}")
            if (
                (skip or retryable)
                and settings.llm_fallback_enabled
                and i < len(chain) - 1
            ):
                logger.warning(
                    "LLM fallback %s → %s | 사유: %s", name, chain[i + 1], _label
                )
                continue
            raise RuntimeError(
                "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            ) from e

    raise RuntimeError(
        "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
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
        raise RuntimeError(
            "사용 가능한 LLM provider가 없습니다. .env API 키를 확인하세요."
        )

    errors: list[str] = []
    for i, name in enumerate(chain):
        if i > 0 and not settings.llm_fallback_enabled:
            break
        try:
            llm = get_llm(name)
            # [P0-13] get_llm 은 provider별 공유 싱글톤을 반환한다. last_stream_usage 가
            # 인스턴스 속성이라 동시 스트림 A/B 가 서로의 usage 를 덮어써 토큰 과금
            # 귀속이 오염되었다. 요청별 shallow copy 로 usage 를 요청 스코프에 격리한다
            # (HTTP 클라이언트 등 무거운 리소스는 참조 공유 — 오버헤드 없음).
            llm = copy.copy(llm)
            # 이전 턴의 스트리밍 실측 usage 가 남아있지 않도록 초기화
            # (OpenAI 호환 provider 는 이번 스트림 최종 청크에서 다시 채운다).
            llm.last_stream_usage = None
            # 첫 chunk probe: 연결은 됐지만 아무 데이터도 안 오면 "완전 무응답" 판정 → fallback
            # _FIRST_CHUNK_TIMEOUT(15s) 이내에 첫 토큰이 오지 않으면 asyncio.TimeoutError
            # 이후 스트리밍은 끝까지 기다림 (시간 초과 없음)
            agen = llm.stream(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system,
            )
            first_chunk: str | None = None
            try:
                first_chunk = await asyncio.wait_for(
                    agen.__anext__(), timeout=_FIRST_CHUNK_TIMEOUT
                )
            except StopAsyncIteration:
                pass
            # asyncio.TimeoutError (첫 chunk 무응답) → 외부 except로 전달 → 다음 provider

            async def _gen(gen=agen, first=first_chunk) -> AsyncIterator[str]:
                if first is not None:
                    yield first
                async for piece in gen:  # 스트리밍 완료까지 무한 대기
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
            # 부분 소비된 async generator 를 정리하지 않으면 연결이 누수된다.
            if "agen" in dir() and agen is not None:
                try:
                    await agen.aclose()
                except Exception:
                    pass
            skip = isinstance(e, (ValueError, ImportError))
            # 스트리밍 첫 chunk 무응답도 retryable (is_retryable_error + asyncio.TimeoutError)
            retryable = is_retryable_error(e) or isinstance(e, asyncio.TimeoutError)
            _label = (
                f"첫chunk무응답>{_FIRST_CHUNK_TIMEOUT:.0f}s"
                if isinstance(e, asyncio.TimeoutError)
                else str(e)
            )
            errors.append(f"{name}: {_label}")
            if (
                (skip or retryable)
                and settings.llm_fallback_enabled
                and i < len(chain) - 1
            ):
                logger.warning(
                    "LLM stream fallback %s → %s | 사유: %s", name, chain[i + 1], _label
                )
                continue
            raise RuntimeError(
                "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            ) from e

    raise RuntimeError(
        "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    )
