"""Tencent Cloud Maas DeepSeek-V4 LLM (OpenAI 호환)."""
from __future__ import annotations
from typing import Optional

from .base import BaseLLM, LLMResponse, Message, text_from_message, text_from_delta
from ...config import settings


class TencentLLM(BaseLLM):
    provider_name = "tencent"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash-202605",
        base_url: str = "https://tokenhub-intl.tencentcloudmaas.com/v1",
        timeout_sec: Optional[float] = None,
    ):
        if not api_key:
            raise ValueError("Tencent API 키가 필요합니다.")

        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("openai 패키지가 필요합니다. pip install openai") from e

        import httpx
        ts = timeout_sec or float(settings.llm_provider_timeout_sec)
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(ts, connect=10.0),
        )
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def _build_msgs(self, messages: list[Message], system: Optional[str]) -> list[dict]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        return msgs

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> LLMResponse:
        temperature = settings.tencent_temperature if temperature is None else temperature
        max_tokens = settings.tencent_max_tokens if max_tokens is None else max_tokens
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=self._build_msgs(messages, system),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        if not resp.choices:
            return LLMResponse(text="", model=self._model, provider=self.provider_name)
        msg = resp.choices[0].message
        # Reasoning models (e.g. DeepSeek-V4) return the answer in
        # `reasoning_content`; `content` can be empty. Fall back to it.
        text = text_from_message(msg)
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
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ):
        temperature = settings.tencent_temperature if temperature is None else temperature
        max_tokens = settings.tencent_max_tokens if max_tokens is None else max_tokens
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=self._build_msgs(messages, system),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        seen_content = False
        reasoning_buf: list[str] = []
        async for chunk in resp:
            # OpenAI 호환: 최종 청크(choices=[])에 usage 실측값이 온다.
            if not chunk.choices:
                self.capture_stream_usage(getattr(chunk, "usage", None))
                continue
            delta = chunk.choices[0].delta
            # 최종 답변은 content 에 온다. reasoning_content 는 모델의 생각
            # 과정이므로 사용자에게 노출하지 않는다. reasoning-only 모델 폴백을
            # 위해서만 버퍼링한다.
            piece = text_from_delta(delta)
            if piece:
                seen_content = True
                yield piece
            else:
                r = getattr(delta, "reasoning_content", None)
                if r:
                    reasoning_buf.append(r)
        # choices 가 있는 마지막 청크에도 usage 가 붙을 수 있으므로 보강
        self.capture_stream_usage(getattr(chunk, "usage", None))
        # 폴백: content 가 전혀 없고 reasoning 에만 답이 있는 모델의 경우,
        # 버퍼링한 reasoning 을 최종 답변으로 내보낸다(사용자 노출 최소화).
        if not seen_content and reasoning_buf:
            yield "".join(reasoning_buf)
