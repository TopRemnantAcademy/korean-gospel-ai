"""Embedder Factory - 이름으로 적합한 구현체 반환. 인스턴스는 캐시(모델 로딩 비싸므로)."""
from __future__ import annotations
from functools import lru_cache

from .base import BaseEmbedder


@lru_cache(maxsize=8)
def get_embedder(name: str) -> BaseEmbedder:
    """name in {'kure', 'bge_m3', 'e5', 'hf_inference', 'voyage'}"""
    n = name.lower().strip()
    if n in {"kure", "kure_v1", "kurev1"}:
        from .kure import KureEmbedder
        return KureEmbedder()
    if n in {"bge_m3", "bge-m3", "bge"}:
        from .bge import BgeM3Embedder
        return BgeM3Embedder()
    if n in {"e5", "e5_large", "multilingual_e5"}:
        from .e5 import E5Embedder
        return E5Embedder()
    if n in {"hf_inference", "hf-inference", "hf"}:
        from .hf_inference import HfInferenceEmbedder
        return HfInferenceEmbedder()
    if n in {"voyage", "voyage_3", "voyage-3"}:
        from .voyage import VoyageEmbedder
        return VoyageEmbedder()
    raise ValueError(f"Unknown embedder: {name}")


def list_supported() -> list[str]:
    return ["kure", "bge_m3", "e5", "hf_inference", "voyage"]

