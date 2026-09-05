"""LLM Factory - settings.llm_provider 기반으로 적합한 구현체 반환."""
from __future__ import annotations
import hashlib

from ...config import settings
from .base import BaseLLM


_LLM_CACHE: dict[str, tuple[BaseLLM, str]] = {}  # {provider: (instance, api_key_hash)}


def _api_key_hash(provider: str) -> str:
    """provider별 API 키 해시 반환 (캐시 무효화 감지용)."""
    key_map = {
        "gemini": settings.google_api_key,
        "openai": settings.openai_api_key,
        "claude": settings.anthropic_api_key,
        "deepseek": settings.deepseek_api_key,
        "tencent": settings.tencent_api_key or "",
        "nvidia": settings.nvidia_api_key or "",
        "ollama": settings.ollama_host,  # ollama는 host로 식별
    }
    key = key_map.get(provider, "")
    return hashlib.md5((key or "").encode()).hexdigest()


def clear_llm_cache() -> None:
    """LLM 인스턴스 캐시 강제 무효화 (관리자 API에서 호출)."""
    _LLM_CACHE.clear()


def get_llm(provider: str | None = None) -> BaseLLM:
    """provider=None 이면 settings.llm_provider 사용. 다른 provider도 임시로 받을 수 있음."""
    name = (provider or settings.llm_provider).lower()

    # API 키 변경 감지 → 캐시 무효화
    current_hash = _api_key_hash(name)
    cached = _LLM_CACHE.get(name)
    if cached and cached[1] == current_hash:
        return cached[0]

    # 새 인스턴스 생성
    if name == "gemini":
        from .gemini import GeminiLLM
        instance = GeminiLLM(api_key=settings.google_api_key or "", model=settings.gemini_model)

    elif name == "openai":
        from .openai import OpenAILLM
        instance = OpenAILLM(api_key=settings.openai_api_key or "", model=settings.openai_model)

    elif name == "claude":
        from .claude import ClaudeLLM
        instance = ClaudeLLM(api_key=settings.anthropic_api_key or "", model=settings.claude_model)

    elif name == "ollama":
        from .ollama import OllamaLLM
        instance = OllamaLLM(host=settings.ollama_host, model=settings.ollama_model)

    elif name == "deepseek":
        from .deepseek import DeepSeekLLM
        instance = DeepSeekLLM(
            api_key=settings.deepseek_api_key or "",
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        )

    elif name == "tencent":
        from .tencent import TencentLLM
        instance = TencentLLM(
            api_key=settings.tencent_api_key or "",
            model=settings.tencent_model,
            base_url=settings.tencent_base_url,
        )

    elif name == "nvidia":
        from .nvidia import NvidiaLLM
        instance = NvidiaLLM(
            models=settings.nvidia_model_list,
            base_url=settings.nvidia_base_url,
            timeout_sec=float(settings.llm_provider_timeout_sec or 90),
            enable_thinking=settings.nvidia_enable_thinking,
        )

    else:
        raise ValueError(f"Unknown LLM provider: {name}")

    _LLM_CACHE[name] = (instance, current_hash)
    return instance
