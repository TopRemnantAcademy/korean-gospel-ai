"""Ollama 로컬 오픈소스 LLM (stub) - HTTP 호출 기반이라 SDK 불필요."""
from __future__ import annotations
from typing import Optional
import httpx

from .base import BaseLLM, LLMResponse, Message


class OllamaLLM(BaseLLM):
    provider_name = "ollama"

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self._host = host.rstrip("/")
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
        msgs.extend({"role": m.role, "content": m.content} for m in messages)

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": msgs,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            r.raise_for_status()
            data = r.json()

        text = data.get("message", {}).get("content", "")
        return LLMResponse(
            text=text,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            model=self._model,
            provider=self.provider_name,
        )
