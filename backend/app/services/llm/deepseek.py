"""DeepSeek API (OpenAI-compatible).
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-29
# Task: httpx 타임아웃 명시 — fallback.py wait_for 와 이중 안전장치
#       기본 600초 read timeout → connect 5s / read 25s / total 25s 로 단축
# =============================================================================
"""
from __future__ import annotations
from typing import Optional

from .base import BaseLLM, LLMResponse, Message, text_from_message, text_from_delta


class DeepSeekLLM(BaseLLM):
    provider_name = "deepseek"

    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com",
                 timeout_sec: float = 25.0):
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 가 설정되어 있지 않습니다.")
        try:
            from openai import AsyncOpenAI  # type: ignore
            import httpx
        except ImportError as e:
            raise ImportError("pip install openai httpx") from e
        # 클라이언트는 connections.py 레지스트리에서 가져옴 (타임아웃 포함 싱글턴)
        from ...connections import connections
        client = connections.deepseek()
        if client is None:
            # fallback: 직접 초기화
            _timeout = httpx.Timeout(timeout=timeout_sec, connect=5.0)
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=_timeout)
        self._client = client
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def _build_msgs(self, messages: list[Message], system: Optional[str]) -> list[dict]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> LLMResponse:
        msgs = self._build_msgs(messages, system)
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

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ):
        """DeepSeek 스트리밍 — OpenAI 호환 SSE."""
        msgs = self._build_msgs(messages, system)
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        seen_content = False
        reasoning_buf: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            piece = text_from_delta(delta)
            if piece:
                seen_content = True
                yield piece
            else:
                r = getattr(delta, "reasoning_content", None)
                if r:
                    reasoning_buf.append(r)
        # 폴백: content 가 없고 reasoning 에만 답이 있는 모델 대비
        if not seen_content and reasoning_buf:
            yield "".join(reasoning_buf)
