"""Enhanced RAG — 컨텍스트 인지 리랭커.

전략:
- heuristic     : dense/sparse 정규점수 + 쿼리 어휘 커버리지 + MMR 다양성
                  (외부 모델 없이 동작 → 기본값, 오프라인 안전)
- llm           : chat_with_fallback 로 각 후보 관련도(0~1) 산출 (LLM-as-judge)
                  실패 시 자동으로 heuristic 으로 폴백
- cross_encoder : BGE reranker-v2-m3 (로컬 CrossEncoder). 미설치 시 heuristic 폴백
- none          : RRF 순서 그대로 유지

모든 전략은 RetrievedChunk.rerank_score / score 를 채워 반환한다.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Optional

from ..llm.base import Message
from ..llm.fallback import chat_with_fallback

from .bm25 import tokenize
from .config import RAGConfig
from .types import RetrievedChunk

logger = logging.getLogger(__name__)


def _minmax(vals: list[float]) -> list[float]:
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return [0.0 for _ in vals]
    return [(v - lo) / (hi - lo) for v in vals]


def _coverage(query: str, text: str) -> float:
    qt = set(tokenize(query))
    if not qt:
        return 0.0
    tt = set(tokenize(text))
    if not tt:
        return 0.0
    return len(qt & tt) / len(qt)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


class ContextAwareReranker:
    def __init__(self, strategy: str = "heuristic"):
        self.strategy = strategy
        self._ce = None  # lazy cross-encoder

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        top_n: Optional[int] = None,
        config: Optional[RAGConfig] = None,
    ) -> list[RetrievedChunk]:
        top_n = top_n or (config.rerank_top_n if config else 5)
        if not candidates:
            return []
        if self.strategy == "none":
            for c in candidates:
                c.rerank_score = None
            return candidates[:top_n]

        if self.strategy == "llm":
            try:
                return self._rerank_llm(query, candidates, top_n)
            except Exception as e:
                logger.warning("[rerank] llm 실패 → heuristic 폴백: %s", e)
                return self._rerank_heuristic(query, candidates, top_n, config)

        if self.strategy == "cross_encoder":
            try:
                return self._rerank_cross(query, candidates, top_n)
            except Exception as e:
                logger.warning("[rerank] cross_encoder 실패 → heuristic 폴백: %s", e)
                return self._rerank_heuristic(query, candidates, top_n, config)

        return self._rerank_heuristic(query, candidates, top_n, config)

    # ── heuristic ──
    def _rerank_heuristic(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int,
        config: Optional[RAGConfig],
    ) -> list[RetrievedChunk]:
        lambda_weight = config.mmr_lambda if config else 0.7
        norm_dense = _minmax([c.dense_score for c in candidates])
        norm_sparse = _minmax([c.sparse_score for c in candidates])
        coverage_scores = [_coverage(query, c.text) for c in candidates]
        base = [0.5 * norm_dense[i] + 0.3 * norm_sparse[i] + 0.2 * coverage_scores[i] for i in range(len(candidates))]

        toks = [set(tokenize(c.text)) for c in candidates]
        selected: list[int] = []
        remaining = list(range(len(candidates)))
        while remaining and len(selected) < top_n:
            best_idx, best_val = -1, -math.inf
            for idx in remaining:
                sim = max((_jaccard(toks[idx], toks[s]) for s in selected), default=0.0)
                val = lambda_weight * base[idx] + (1 - lambda_weight) * sim
                if val > best_val:
                    best_val, best_idx = val, idx
            selected.append(best_idx)
            remaining.remove(best_idx)

        out: list[RetrievedChunk] = []
        for rank, idx in enumerate(selected):
            c = candidates[idx]
            c.rerank_score = float(base[idx])
            c.score = float(base[idx])
            c.rank = rank
            out.append(c)
        return out

    # ── LLM-as-judge ──
    def _rerank_llm(
        self, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        items = "\n".join(
            f"[{i}] {c.text[:400]}" for i, c in enumerate(candidates)
        )
        system = (
            "You are a strict relevance judge for retrieval reranking. "
            "Given a query and candidate passages, score each passage's relevance to the query on a 0.0-1.0 scale. "
            "Respond ONLY with a JSON array: [{\"index\": <int>, \"score\": <float 0-1>}, ...]. "
            "No prose, no markdown."
        )
        user = f"QUERY: {query}\n\nPASSAGES:\n{items}"
        resp, _, _ = chat_with_fallback(
            [Message(role="user", content=user)],
            temperature=0.0,
            max_tokens=800,
            system=system,
        )
        scores = self._parse_llm_scores(resp.text, len(candidates))
        for i, c in enumerate(candidates):
            c.rerank_score = float(scores.get(i, 0.0))
        candidates.sort(key=lambda c: c.rerank_score, reverse=True)  # type: ignore[arg-type]
        for rank, c in enumerate(candidates[:top_n]):
            c.score = c.rerank_score or 0.0
            c.rank = rank
        return candidates[:top_n]

    @staticmethod
    def _parse_llm_scores(text: str, n: int) -> dict[int, float]:
        try:
            arr = json.loads(text.strip())
            out: dict[int, float] = {}
            for item in arr:
                idx = int(item.get("index", -1))
                if 0 <= idx < n:
                    out[idx] = float(item.get("score", 0.0))
            return out
        except Exception:
            return {}

    # ── cross-encoder (BGE) ──
    def _rerank_cross(
        self, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if self._ce is None:
            from ..reranker import BgeReranker

            self._ce = BgeReranker()
        scores = self._ce.rerank(query, [c.text for c in candidates])
        norm = _minmax(scores)
        for i, c in enumerate(candidates):
            c.rerank_score = float(norm[i])
        candidates.sort(key=lambda c: c.rerank_score, reverse=True)  # type: ignore[arg-type]
        for rank, c in enumerate(candidates[:top_n]):
            c.score = c.rerank_score or 0.0
            c.rank = rank
        return candidates[:top_n]
