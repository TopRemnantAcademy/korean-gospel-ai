"""Google Gemini 구현 (default LLM)."""
from __future__ import annotations
from typing import Optional

from .base import BaseLLM, LLMResponse, Message


class GeminiLLM(BaseLLM):
    provider_name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        if not api_key:
            raise ValueError("GOOGLE_API_KEY 가 설정되어 있지 않습니다.")
        # 클라이언트는 connections.py 레지스트리에서 가져옴 (싱글턴)
        from ...connections import connections
        client = connections.gemini()
        if client is None:
            # fallback: 직접 초기화 (connections 미사용 경로)
            from google import genai  # type: ignore
            client = genai.Client(api_key=api_key)
        self._client = client
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
        from google.genai import types

        # Gemini는 'user'/'model' role만 받음 → 'assistant' → 'model' 변환
        contents = []
        for m in messages:
            role = "user" if m.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system if system else None,
        )

        # SDK 의 generate_content 는 동기 메서드라서 to_thread 로 비동기화
        import asyncio
        resp = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self._model,
            contents=contents,
            config=config,
        )

        text = resp.text or ""
        usage = getattr(resp, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=self._model,
            provider=self.provider_name,
            raw={},
        )


    async def stream(
        self,
        messages,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        system=None,
    ):
        """Gemini streaming - 글자가 흘러나오는 효과."""
        from google.genai import types
        import asyncio

        contents = []
        for m in messages:
            role = "user" if m.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system if system else None,
        )

        # SDK는 sync iterator - to_thread로 청크 받기
        def _iter():
            return self._client.models.generate_content_stream(
                model=self._model, contents=contents, config=config,
            )
        try:
            stream_iter = await asyncio.to_thread(_iter)
            for chunk in stream_iter:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except Exception as e:
            yield f"[stream error: {e}]"
