"""Enhanced RAG — 임베딩 래퍼.

기존 embedding 팩토리(get_embedder)를 그대로 재사용한다.
CachedEmbedder 가 TTL LRU 캐시를 제공하므로 동일 텍스트 중복 임베딩 비용이 없다.
"""
from __future__ import annotations

import numpy as np

from ..embedding.factory import get_embedder


class RAGEmbedder:
    def __init__(self, name: str = "kure"):
        # get_embedder 는 CachedEmbedder 를 반환 (내부 BaseEmbedder 래핑)
        self._inner = get_embedder(name)
        self.name = self._inner.name
        self.dim = self._inner.dim

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._inner.embed_query(text)
