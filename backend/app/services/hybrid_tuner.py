"""Hybrid RRF 가중치 그리드 탐색 — validation 질문셋 MRR 최대화."""
from __future__ import annotations

import itertools
from typing import Iterable

from ..config import settings
from .eval_service import load_eval_questions
from .retriever import HybridRetriever


async def _keyword_mrr(
    retriever: HybridRetriever,
    questions: list[dict],
    *,
    top_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> float:
    if not questions:
        return 0.0
    rr_sum = 0.0
    counted = 0
    for q in questions:
        keywords = q.get("expected_keywords") or []
        if not keywords:
            continue
        items = await retriever.retrieve(
            q["query"],
            rerank_top_n=top_k,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
        )
        rank = None
        for i, it in enumerate(items, start=1):
            blob = it.text + " " + str(it.metadata.get("title", ""))
            if any(k in blob for k in keywords):
                rank = i
                break
        if rank is not None:
            rr_sum += 1.0 / rank
        counted += 1
    return rr_sum / counted if counted else 0.0


async def tune_hybrid_weights(
    *,
    embedder: str | None = None,
    top_k: int = 5,
    dense_grid: Iterable[float] | None = None,
    sparse_grid: Iterable[float] | None = None,
) -> dict:
    questions = load_eval_questions()
    if not questions:
        return {"ok": False, "reason": "data/eval/questions.json 없음"}

    dense_grid = list(dense_grid or [0.5, 0.6, 0.7, 0.8, 0.9])
    sparse_grid = list(sparse_grid or [0.1, 0.2, 0.3, 0.4, 0.5])

    retriever = HybridRetriever(embedder_name=embedder)
    best_mrr = -1.0
    best_pair = (settings.dense_weight, settings.sparse_weight)
    trials: list[dict] = []

    for dw, sw in itertools.product(dense_grid, sparse_grid):
        if dw + sw <= 0:
            continue
        mrr = await _keyword_mrr(
            retriever, questions, top_k=top_k, dense_weight=dw, sparse_weight=sw,
        )
        trials.append({"dense_weight": dw, "sparse_weight": sw, "mrr": round(mrr, 4)})
        if mrr > best_mrr:
            best_mrr = mrr
            best_pair = (dw, sw)

    trials.sort(key=lambda t: t["mrr"], reverse=True)
    return {
        "ok": True,
        "embedder": retriever.embedder_name,
        "questions": len(questions),
        "top_k": top_k,
        "best": {
            "dense_weight": best_pair[0],
            "sparse_weight": best_pair[1],
            "mrr": round(best_mrr, 4),
        },
        "current": {
            "dense_weight": settings.dense_weight,
            "sparse_weight": settings.sparse_weight,
        },
        "trials": trials[:15],
    }
