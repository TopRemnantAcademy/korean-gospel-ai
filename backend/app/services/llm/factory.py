"""LLM Factory - settings.llm_provider 기반으로 적합한 구현체 반환."""
from __future__ import annotations
from functools import lru_cache

from ...config import settings
from .base import BaseLLM


@lru_cache(maxsize=4)
def get_llm(provider: str | None = None) -> BaseLLM:
    """provider=None 이면 settings.llm_provider 사용. 다른 provider도 임시로 받을 수 있음."""
    name = (provider or settings.llm_provider).lower()

    if name == "gemini":
        from .gemini import GeminiLLM
        return GeminiLLM(api_key=settings.google_api_key or "", model=settings.gemini_model)

    if name == "openai":
        from .openai import OpenAILLM
        return OpenAILLM(api_key=settings.openai_api_key or "", model=settings.openai_model)

    if name == "claude":
        from .claude import ClaudeLLM
        return ClaudeLLM(api_key=settings.anthropic_api_key or "", model=settings.claude_model)

    if name == "ollama":
        from .ollama import OllamaLLM
        return OllamaLLM(host=settings.ollama_host, model=settings.ollama_model)

    if name == "deepseek":
        from .deepseek import DeepSeekLLM
        return DeepSeekLLM(
            api_key=settings.deepseek_api_key or "",
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        )

    raise ValueError(f"Unknown LLM provider: {name}")
