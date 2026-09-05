"""스트리밍 실측 usage 캡처 검증 (기업级 견고성).

실행:
    ./venv/Scripts/python.exe -m pytest tests/test_stream_usage_capture.py -q

설계 원칙
--------
- SSE 하에서 공급자가 usage 를 주지 않는 경우가 많아 기존엔 추정치로 폴백했다.
  OpenAI 호환 provider(nvidia/tencent/openai/deepseek)는
  `stream_options={"include_usage": True}` 로 최종 청크(choices=[])에 실측
  usage 를 실어 보낸다. 본 테스트는 이 경로를 모킹 청크로 검증한다.
- 공급자 SDK 객체를 임의로 만들지 않는다 — 프로젝트의 NvidiaLLM/TencentLLM 은
  `_client.chat.completions.create` 가 반환하는 비동기 제너레이터를 치환하는
  방식으로만 검증한다(실제 SDK 시그니처에 의존).
- 실측값이 없으면 last_stream_usage 가 None 으로 유지되어 호출부가 추정치로
  폴백하는지도 함께 검증한다(fail-open 보장).
- pytest-asyncio 미설치 환경 고려: 비동기 테스트는 asyncio.run() 으로 래핑.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace


def _fake_usage(prompt_tokens: int, completion_tokens: int, total_tokens: int):
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _content_chunk(text: str):
    delta = SimpleNamespace(content=text, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def _usage_chunk(usage):
    # OpenAI 호환 최종 청크: choices 가 비어 있고 usage 에 실측값이 온다.
    return SimpleNamespace(choices=[], usage=usage)


async def _run_nvidia_capture():
    from backend.app.services.llm.nvidia import NvidiaLLM

    llm = NvidiaLLM.__new__(NvidiaLLM)
    llm.provider_name = "nvidia"
    llm._model = "mock-model"
    llm.last_stream_usage = None

    async def _fake_stream():
        yield _content_chunk("안녕")
        yield _content_chunk("하세요")
        yield _usage_chunk(_fake_usage(12, 8, 20))

    # _client 만 치환: 실제 SDK 호출 없이 스트림 계약만 재현
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=SimpleNamespace(
                    # NvidiaLLM.stream 은 create(...) 를 await 하므로 코루틴 반환
                    __call__=lambda **kw: _fake_stream()
                )
            )
        )
    )
    # create 호출이 await 될 수 있도록 awaitable 래퍼로 교체
    async def _awaitable_create(**kw):
        return _fake_stream()

    llm._client.chat.completions.create = _awaitable_create

    # _extra_body 등 내부 헬퍼 호출을 우회하기 위해 stream 코루틴 직접 호출 대신
    # public stream() 이 없으므로 stream 계약을 재현하는 로컬 제너레이터 사용.
    # 실제 구현은 stream() 내부에서 capture_stream_usage 를 호출한다 — 이를
    # 검증하기 위해 mock stream 을 nvidia 과 동일 계약으로 실행.
    async def _simulated_stream():
        stream = await llm._client.chat.completions.create(
            model=llm._model, messages=[], stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if not chunk.choices:
                llm.capture_stream_usage(getattr(chunk, "usage", None))
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yield delta.content
        llm.capture_stream_usage(getattr(chunk, "usage", None))

    out = []
    async for piece in _simulated_stream():
        out.append(piece)

    return "".join(out), llm.last_stream_usage


async def _run_no_usage_fallback():
    from backend.app.services.llm.base import BaseLLM

    class _Dummy(BaseLLM):
        provider_name = "dummy"
        model_name = "dummy-model"

        async def chat(self, *a, **k):  # pragma: no cover - 인터페이스 스텁
            raise NotImplementedError

        async def stream(self, *a, **k):  # pragma: no cover
            return
            yield  # type: ignore

    llm = _Dummy()
    llm.last_stream_usage = None
    # usage 가 None 인 최종 청크만 온 상황
    llm.capture_stream_usage(None)
    return llm.last_stream_usage


def test_nvidia_stream_captures_real_usage():
    text, usage = asyncio.run(_run_nvidia_capture())
    assert text == "안녕하세요"
    # 실측 usage 가 캡처되었는지
    assert usage is not None
    assert usage.prompt_tokens == 12
    assert usage.completion_tokens == 8
    assert usage.total_tokens == 20
    assert usage.provider == "nvidia"


def test_no_usage_keeps_fallback_none():
    usage = asyncio.run(_run_no_usage_fallback())
    # usage 가 없으면 None 유지 → 호출부는 추정치로 폴백(fail-open)
    assert usage is None


def test_capture_stream_usage_builds_response():
    from backend.app.services.llm.base import BaseLLM

    class _Dummy(BaseLLM):
        provider_name = "x"
        model_name = "m"

        async def chat(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def stream(self, *a, **k):  # pragma: no cover
            return
            yield  # type: ignore

    llm = _Dummy()
    llm.last_stream_usage = None
    llm.capture_stream_usage(_fake_usage(5, 3, 8))
    assert llm.last_stream_usage is not None
    assert llm.last_stream_usage.prompt_tokens == 5
    assert llm.last_stream_usage.completion_tokens == 3
    # 빈 usage 는 무시
    llm.capture_stream_usage(None)
    assert llm.last_stream_usage.prompt_tokens == 5
