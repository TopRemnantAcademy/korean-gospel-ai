"""NVIDIA NIM API (OpenAI-compatible) — Nemotron / DeepSeek-V4-Pro 등 텍스트 채팅.

base_url: https://integrate.api.nvidia.com/v1

여러 모델을 (model, api_key) 쌍으로 받아, 첫 모델이 실패하면 목록 순서대로
즉시 교체(fallback)한다. 모델별로 다른 API 키가 필요하면 호출侧에서 목록에
포함시킨다(설정: settings.nvidia_model_list → "model" 또는 "model:KEY").

Nemotron/DeepSeek-V4 는 reasoning 모델이라 delta 에 reasoning_content 가 먼저 오고
그 뒤 content 가 온다. 사용자에게는 content 만 스트리밍하고,
content 가 전혀 없을 때만 reasoning 을 폴백으로 내보낸다.

enable_thinking 은 지연시간을 크게 늘리므로 기본 비활성
(settings.nvidia_enable_thinking 으로 제어).

⚠️ 이미지 생성 모델(google/diffusiongemma 등)은 이 클라이언트에 넣지 않는다
   — 별도 nvidia_image_* 설정으로 관리 (텍스트 채팅과 응답 포맷이 다름).
"""
from __future__ import annotations

import httpx
from typing import Any, AsyncIterator, Optional

from .base import BaseLLM, LLMResponse, Message, text_from_message, text_from_delta


def _retryable(exc: Exception) -> bool:
    """연결 실패 시 교체(fallback)해 볼 가치가 있는 오류인가?

    ⚠️ 같은 패키지에 sibling ``openai.py`` 가 있어 basedpyright 가
    ``from openai import APIConnectionError`` 를 로컬 모듈로 오인한다.
    따라서 예외 클래스를 임포트하지 않고 런타임 속성(mod/이름)으로 판별한다.
    """
    cls = type(exc)
    mod = getattr(cls, "__module__", "") or ""
    if mod.startswith("openai"):
        name = cls.__name__
        if name in ("APIConnectionError", "APITimeoutError", "RateLimitError"):
            return True  # 연결/타임아웃/429 → 다른 모델로 우회 시도
        if name == "APIStatusError":
            # 5xx(서버 과부하/점검) 는 교체 의미 있음. 4xx(인증/콘텐츠정책) 는 무의미 → 중단.
            code = getattr(exc, "status_code", None)
            return code is not None and 500 <= int(code) <= 599
    # 그 외 네트워크/전송 오류
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError))


class NvidiaLLM(BaseLLM):
    provider_name = "nvidia"

    def __init__(
        self,
        models: list[tuple[str, str]],
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_sec: float = 90.0,
        enable_thinking: bool = False,
    ):
        try:
            import importlib

            _oai = importlib.import_module("openai")
        except ImportError as e:
            raise ImportError("openai 패키지가 필요합니다. pip install openai") from e

        # models: [(model_name, api_key), ...] — 첫 번째가 우선, 실패 시 다음으로 교체
        if not models:
            raise ValueError("NVIDIA 모델 목록이 비어 있습니다.")
        self._base_url = base_url
        self._timeout_sec = timeout_sec
        self._enable_thinking = enable_thinking
        self._entries: list[tuple[str, Any]] = []
        for model, key in models:
            if not key:
                raise ValueError(f"NVIDIA 모델 '{model}' 의 API 키가 없습니다.")
            _timeout = httpx.Timeout(timeout=timeout_sec, connect=10.0)
            client = _oai.AsyncOpenAI(api_key=key, base_url=base_url, timeout=_timeout)
            self._entries.append((model, client))
        self._model = self._entries[0][0]

    @property
    def model_name(self) -> str:
        return self._model

    def _build_msgs(self, messages: list[Message], system: Optional[str]) -> list[dict[str, str]]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for m in messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    def _extra_body(self) -> dict[str, Any]:
        # enable_thinking=False 로 두면 reasoning 없이 바로 답변 → 지연시간 최소화
        return {"chat_template_kwargs": {"enable_thinking": self._enable_thinking}}

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> LLMResponse:
        msgs = self._build_msgs(messages, system)
        last_exc: Optional[Exception] = None
        for model, client in self._entries:
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body=self._extra_body(),
                )
                if not resp.choices:
                    return LLMResponse(text="", prompt_tokens=0, completion_tokens=0,
                                       total_tokens=0, model=model, provider=self.provider_name)
                choice = resp.choices[0]
                text = text_from_message(choice.message)
                usage = resp.usage
                return LLMResponse(
                    text=text,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    total_tokens=usage.total_tokens if usage else 0,
                    model=model,
                    provider=self.provider_name,
                )
            except Exception as exc:  # noqa: BLE001 — 교체 여부 판정 후 처리
                if _retryable(exc):
                    last_exc = exc
                    continue  # 다음 모델로 즉시 교체
                raise  # 4xx 등 교체无意义 오류는 즉시 중단
        # 모든 모델이 retryable 실패 → 마지막 오류 재발생
        assert last_exc is not None
        raise last_exc

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """NVIDIA NIM 스트리밍 — OpenAI 호환 SSE. reasoning_content 는 숨김.

        첫 모델 생성 시작 전 실패 시에만 다음 모델로 교체.
        (이미 토큰을 내보낸 뒤 끊김은 교체 불가 → 그대로 종료)
        """
        msgs = self._build_msgs(messages, system)
        last_exc: Optional[Exception] = None
        for model, client in self._entries:
            try:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    extra_body=self._extra_body(),
                )
                seen_content = False
                reasoning_buf: list[str] = []
                async for chunk in stream:
                    # OpenAI 호환: 최종 청크(choices=[])에 usage 실측값이 온다.
                    if not chunk.choices:
                        self.capture_stream_usage(getattr(chunk, "usage", None))
                        continue
                    delta = chunk.choices[0].delta
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
                if not seen_content and reasoning_buf:
                    yield "".join(reasoning_buf)
                return
            except Exception as exc:  # noqa: BLE001
                if _retryable(exc):
                    last_exc = exc
                    continue
                raise
        assert last_exc is not None
        raise last_exc
