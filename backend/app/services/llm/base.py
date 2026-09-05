"""LLM 추상 인터페이스. 어떤 provider도 이 인터페이스만 구현하면 교체 가능."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


def text_from_message(msg) -> str:
    """OpenAI 호환 메시지에서 본문 추출.

    Reasoning 모델(deepseek-v4 등)은 최종 답을 ``content`` 가 아닌
    ``reasoning_content`` 에 담아 오는 경우가 있다. 두 필드를 모두 확인한다.
    모든 OpenAI 호환 provider(tencent/deepseek/openai)가 동일 규칙을 쓰도록
    단일 헬퍼로 중앙화한다(파트5 P5-1).
    """
    return (getattr(msg, "content", None) or getattr(msg, "reasoning_content", None) or "") or ""


def text_from_delta(delta) -> str:
    """OpenAI 호환 스트리밍 delta 에서 최종 답변 텍스트 추출.

    Reasoning 모델(deepseek-v4 등)은 생각 과정을 ``reasoning_content`` 에,
    최종 답변을 ``content`` 에 담아 보낸다. 사용자에게는 최종 답변만 노출해야
    하므로 여기서는 ``content`` 만 반환한다. ``content`` 가 비어 있는
    reasoning-only 청크는 무시하며, reasoning-only 모델에 대비한 폴백은 각
    provider 의 ``stream()`` 에서 reasoning 을 버퍼링해 마지막에 모아 내보내는
    방식으로 처리한다(파트5 P5-1 보완).
    """
    return getattr(delta, "content", None) or ""


@dataclass
class Message:
    role: str       # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    provider: str = ""
    raw: dict = field(default_factory=dict)   # provider-specific 원본

    @property
    def cost_estimate_usd(self) -> float:
        # provider별로 override 가능. 기본은 0 (free tier 가정).
        return 0.0


class BaseLLM(ABC):
    """모든 LLM provider가 구현해야 하는 인터페이스."""

    provider_name: str = ""

    # 스트리밍 경로에서 공급자가 최종 청크에 실어 보낸 usage(실측 토큰).
    # SSE 는 공급자가 usage 를 주지 않는 경우가 많아 기본값은 None 이며,
    # OpenAI 호환 provider(nvidia/tencent/openai/deepseek)는 stream_options 로
    # 최종 청크 usage 를 받아 채운다. None 이면 호출부는 추정치로 폴백한다.
    last_stream_usage: Optional["LLMResponse"] = None

    def capture_stream_usage(self, usage) -> None:
        """OpenAI 호환 최종 청크의 usage 객체에서 실측 토큰을 보관한다.

        usage 가 없으면(None) 아무 것도 하지 않는다(추정치 폴백 보존).
        """
        if not usage:
            return
        self.last_stream_usage = LLMResponse(
            text="",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            model=self._model if getattr(self, "_model", None) else "",
            provider=self.provider_name,
        )

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """싱글 턴 또는 멀티 턴 채팅. system은 별도 인자(provider별 처리)."""
        ...

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """스트리밍. 미구현 시 chat()을 1번 호출 후 통째로 yield."""
        resp = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens, system=system
        )
        yield resp.text

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
