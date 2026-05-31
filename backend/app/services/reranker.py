"""Reranker 추상 + bge-reranker-v2-m3 구현 (한국어 강함)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Sequence


class BaseReranker(ABC):
    name: str = ""

    @abstractmethod
    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        """각 doc에 대한 점수 (높을수록 관련). 반환 길이 == len(docs)."""
        ...


class BgeReranker(BaseReranker):
    name = "bge_m3"
    model_id = "BAAI/bge-reranker-v2-m3"

    def __init__(self, model_id: str | None = None):
        from sentence_transformers import CrossEncoder
        self._ce = CrossEncoder(model_id or self.model_id, max_length=512)

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        if not docs:
            return []
        pairs = [(query, d) for d in docs]
        scores = self._ce.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]


class NoOpReranker(BaseReranker):
    name = "none"

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        # 점수 없음 - 입력 순서 보존을 위해 내림차순 임의값
        return [1.0 - i * 0.001 for i in range(len(docs))]


class CohereReranker(BaseReranker):
    name = "cohere"

    def __init__(self, api_key: str, model: str = "rerank-multilingual-v3.0"):
        if not api_key:
            raise ValueError("COHERE_API_KEY 가 필요합니다.")
        try:
            import cohere  # type: ignore
        except ImportError as e:
            raise ImportError("cohere 패키지가 필요합니다. pip install cohere") from e
        # 클라이언트는 connections.py 레지스트리에서 가져옴 (싱글턴)
        from ..connections import connections
        client = connections.cohere()
        self._co = client if client is not None else cohere.Client(api_key=api_key)
        self._model = model

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        if not docs:
            return []
        resp = self._co.rerank(model=self._model, query=query, documents=list(docs))
        # Cohere 응답은 정렬되어 옴. 원래 순서로 점수 매핑.
        scores = [0.0] * len(docs)
        for r in resp.results:
            scores[r.index] = float(r.relevance_score)
        return scores


@lru_cache(maxsize=4)
def get_reranker(name: str | None = None, *, cohere_api_key: str | None = None) -> BaseReranker:
    n = (name or "bge_m3").lower()
    if n in {"bge", "bge_m3", "bge-m3"}:
        return BgeReranker()
    if n == "none":
        return NoOpReranker()
    if n == "cohere":
        return CohereReranker(api_key=cohere_api_key or "")
    raise ValueError(f"Unknown reranker: {name}")
