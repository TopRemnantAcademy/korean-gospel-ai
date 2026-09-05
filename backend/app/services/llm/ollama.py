"""Ollama 로컬 오픈소스 LLM (stub) - HTTP 호출 기반이라 SDK 불필요."""
from __future__ import annotations
from typing import AsyncIterator, Optional
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

        from ...connections import connections
        client = connections.async_http_client()
        r = await client.post(
            f"{self._host}/api/chat",
            json={
                "model": self._model,
                "messages": msgs,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=120.0,
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

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Ollama 스트리밍 — /api/chat 에 stream=True 로 요청하여 토큰 단위 yield."""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)

        import json as _json
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": msgs,
                    "stream": True,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = _json.loads(line)
                    except Exception:
                        continue
                    if chunk.get("done"):
                        break
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
