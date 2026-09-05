"""OpenAI 구현 (stub: 의존성 lazy import). 사용하려면 requirements 의 openai 주석 해제."""
from __future__ import annotations
from typing import Optional

from .base import BaseLLM, LLMResponse, Message, text_from_message


class OpenAILLM(BaseLLM):
    provider_name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OPENAI_API_KEY 가 설정되어 있지 않습니다.")
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as e:
            raise ImportError(
                "openai 패키지가 설치되어 있지 않습니다. "
                "requirements.txt에서 'openai' 주석을 해제하고 pip install 하세요."
            ) from e
        # 클라이언트는 connections.py 레지스트리에서 가져옴 (싱글턴)
        from ...connections import connections
        client = connections.openai_client()
        self._client = client if client is not None else AsyncOpenAI(api_key=api_key)
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
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in messages:
            msgs.append({"role": m.role, "content": m.content})

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not resp.choices:
            return LLMResponse(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0,
                              model=self._model, provider=self.provider_name)
        choice = resp.choices[0]
        text = text_from_message(choice.message)
        usage = resp.usage
        return LLMResponse(
            text=text,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            model=self._model,
            provider=self.provider_name,
        )
