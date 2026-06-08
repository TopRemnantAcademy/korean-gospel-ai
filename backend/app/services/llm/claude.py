"""Anthropic Claude 구현 (stub)."""
from __future__ import annotations
from typing import Optional

from .base import BaseLLM, LLMResponse, Message


class ClaudeLLM(BaseLLM):
    provider_name = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY 가 설정되어 있지 않습니다.")
        try:
            from anthropic import AsyncAnthropic  # type: ignore
        except ImportError as e:
            raise ImportError(
                "anthropic 패키지가 필요합니다. requirements.txt 에서 주석 해제 후 설치."
            ) from e
        # 클라이언트는 connections.py 레지스트리에서 가져옴 (싱글턴)
        from ...connections import connections
        client = connections.anthropic()
        self._client = client if client is not None else AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> LLMResponse:
        # Claude는 system을 별도 파라미터로 받고, messages는 user/assistant만.
        msgs = [{"role": m.role, "content": m.content} for m in messages if m.role in {"user", "assistant"}]

        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=msgs,
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        usage = resp.usage
        return LLMResponse(
            text=text,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
            total_tokens=(usage.input_tokens + usage.output_tokens) if usage else 0,
            model=self._model,
            provider=self.provider_name,
        )
