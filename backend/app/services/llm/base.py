"""LLM 추상 인터페이스. 어떤 provider도 이 인터페이스만 구현하면 교체 가능."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


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
