"""Hybrid Retriever.

- server 모드 : dense + sparse(BM42) → RRF 융합 → reranker → top-N
- embedded/memory 모드 : dense only → reranker → top-N (sparse 자동 우회)
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: D-C16 — Salvation-Aware Retriever (C6 대체·강화)
#       SALVATION_BOOST_MATRIX + DARAKBANG_BOOST_MATRIX 추가
#       assume_saved 플래그 영향 반영
# Reason: ORDERS.md EPIC D-C16
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from ..config import settings
from .embedding.factory import get_embedder
from .vector_store import QdrantStore, RetrievedPoint
from .reranker import get_reranker, BaseReranker


# D-C16: (사용자 salvation_status, 자료 target_salvation_stage) → boost
SALVATION_BOOST_MATRIX: dict[tuple[str, str], float] = {
    ("unknown",   "seeker"):       +0.40,
    ("unknown",   "uncertain"):    +0.20,
    ("unknown",   "gospel_core"):  +0.30,
    ("seeker",    "seeker"):       +0.35,
    ("seeker",    "gospel_core"):  +0.50,
    ("uncertain", "assurance"):    +0.45,
    ("uncertain", "uncertain"):    +0.25,
    ("uncertain", "gospel_core"):  +0.35,
    ("assured",   "discipleship"): +0.25,
    ("assured",   "assured"):      +0.10,
    ("mature",    "discipleship"): +0.30,
    ("mature",    "leadership"):   +0.20,
    ("mature",    "pastoral"):     +0.15,
}

# D-C16: (darakbang_role, 자료 darakbang_tier) → boost
DARAKBANG_BOOST_MATRIX: dict[tuple[str, str], float] = {
    ("member",  "darakbang_general"): +0.20,
    ("member",  "darakbang_deep"):    +0.15,
    ("leader",  "darakbang_general"): +0.10,
    ("leader",  "darakbang_deep"):    +0.30,
    ("leader",  "darakbang_leader"):  +0.40,
    ("pastor",  "darakbang_deep"):    +0.25,
    ("pastor",  "darakbang_leader"):  +0.35,
    ("pastor",  "pastoral"):          +0.40,
}


@dataclass
class RetrievedItem:
    id: str
    text: str
    score: float
    rrf_score: float
    dense_rank: int | None
    sparse_rank: int | None
    metadata: dict


# 임베더 이름별 retriever 캐시 — 매 요청마다 embedder/store/reranker 재생성 방지
_retriever_cache: dict[str, "HybridRetriever"] = {}


def get_retriever(embedder_name: str | None = None) -> "HybridRetriever":
    """모듈-레벨 캐시에서 retriever 반환. 없으면 생성 후 캐시."""
    key = embedder_name or settings.embedder
    if key not in _retriever_cache:
        _retriever_cache[key] = HybridRetriever(embedder_name=embedder_name)
    return _retriever_cache[key]


class HybridRetriever:
    def __init__(self, embedder_name: str | None = None, reranker: BaseReranker | None = None):
        self.embedder_name = embedder_name or settings.embedder
        self.embedder = get_embedder(self.embedder_name)
        self.store = QdrantStore(self.embedder_name, dim=self.embedder.dim)
        self.reranker = reranker or get_reranker(
            settings.reranker, cohere_api_key=settings.cohere_api_key
        )

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        rerank_top_n: int | None = None,
        dense_weight: float | None = None,
        sparse_weight: float | None = None,
        profile: Any = None,
        dense_query: str | None = None,   # V3: HyDE 확장 dense 질의 (None=원질의)
        sparse_query: str | None = None,  # V3: 키워드 추출 sparse 질의 (None=원질의)
    ) -> list[RetrievedItem]:  # noqa: E501
        import asyncio as _asyncio

        top_k = top_k or settings.retrieval_top_k
        rerank_top_n = rerank_top_n or settings.rerank_top_n
        dw = dense_weight if dense_weight is not None else settings.dense_weight
        sw = sparse_weight if sparse_weight is not None else settings.sparse_weight

        # ⚡ 1-3) 동기 CPU/IO 작업을 스레드 풀에서 실행 (이벤트 루프 블로킹 방지)
        #        → asyncio.gather(classify_input, retrieve)가 진정한 병렬로 동작
        _embedder = self.embedder
        _store = self.store

        _collection = _store.collection

        def _sync_search():
            # 임베딩 대상: HyDE 등으로 확장된 dense 질의가 있으면 사용, 없으면 원질의
            _dense_q = dense_query or query
            qv = _embedder.embed_query(_dense_q).tolist()   # KURE CPU embedding
            dense = _store.search_dense(qv, top_k=top_k)     # Qdrant dense

            # Sparse: Qdrant 서버 BM42 우선, embedded 면 자체 Kiwi+BM25 인덱스 사용 (V2)
            sparse = _store.search_sparse(query, top_k=top_k)
            if not sparse:
                sparse = _bm25_sparse(_collection, sparse_query or query, top_k)

            rankings = [dense] + ([sparse] if sparse else [])
            weights = ([dw, sw] if sparse else [1.0])
            return _rrf_fusion(rankings, weights=weights, k=60)

        fused = await _asyncio.to_thread(_sync_search)
        if not fused:
            return []

        # 4) Rerank (RERANKER=none이면 즉시 반환, bge_m3이면 스레드에서 실행)
        topN = fused[: max(rerank_top_n * 2, rerank_top_n)]
        _docs = [it["point"].text for it in topN]
        rerank_scores = await _asyncio.to_thread(self.reranker.rerank, query, _docs)
        for it, s in zip(topN, rerank_scores):
            it["rerank_score"] = s
        topN.sort(key=lambda it: it["rerank_score"], reverse=True)
        topN = topN[:rerank_top_n]

        results = [
            RetrievedItem(
                id=p.id,
                text=p.text,
                score=it["rerank_score"],
                rrf_score=it["rrf"],
                dense_rank=it.get("dense_rank"),
                sparse_rank=it.get("sparse_rank"),
                metadata=p.metadata,
            )
            for it in topN
            for p in [it["point"]]
        ]
        
        # C6: 사용자 프로필 기반 매칭 가중치 (Boost)
        # ✏️ AI-CHANGE 2026-05-19 [Antigravity]: profile.xxx → profile.get("xxx") dict 접근 (B5/A2 fix)
        # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C16 — SALVATION_BOOST_MATRIX + DARAKBANG_BOOST_MATRIX 추가
        # ✏️ AI-CHANGE 2026-05-27 [Claude]: settings.retriever_boost_enabled 플래그로 boost on/off 가능
        if profile and settings.retriever_boost_enabled:
            salvation_status = profile.get("salvation_status", "unknown")
            darakbang_role = profile.get("darakbang_role") if profile.get("is_darakbang_member") else None
            darakbang_verified = profile.get("darakbang_verified", False)
            assume_saved = profile.get("assume_saved", False)

            for item in results:
                boost = 0.0
                _faith = profile.get("faith_stage")
                _journey = profile.get("journey_stage")
                _tone = profile.get("preferred_tone")

                # C6: 기존 프로필 기반 boost
                if _faith and _faith in (item.metadata.get("target_audience") or []):
                    boost += 0.15
                if _journey and _journey in (item.metadata.get("target_stage") or []):
                    boost += 0.20
                if _tone == "gentle" and item.metadata.get("emotion_tone") == "comforting":
                    boost += 0.08
                if _faith in ("seeker", "new_believer") and item.metadata.get("difficulty", 3) <= 2:
                    boost += 0.10

                # D-C16: salvation boost matrix
                doc_salvation_stages = item.metadata.get("target_salvation_stage") or []
                if isinstance(doc_salvation_stages, str):
                    doc_salvation_stages = [doc_salvation_stages]
                for stage in doc_salvation_stages:
                    b = SALVATION_BOOST_MATRIX.get((salvation_status, stage), 0.0)
                    if b:
                        boost += b
                        break  # 한 문서에 여러 stage 태그 있어도 첫 매칭만

                # gospel_core_tag 자료 — seeker/uncertain 에게 최우선
                if item.metadata.get("gospel_core_tag") and salvation_status in ("unknown", "seeker", "uncertain"):
                    boost += 0.30

                # D-C16: assume_saved 플래그 영향
                if assume_saved:
                    # "구원받았다 치고" 모드 — discipleship/sanctification 자료 활성화
                    if "discipleship" in doc_salvation_stages or "assured" in doc_salvation_stages:
                        boost += 0.25
                else:
                    # 기본 모드 — gospel_core/seeker 자료 강화 (98% 가정)
                    if "seeker" in doc_salvation_stages or "gospel_core" in doc_salvation_stages:
                        boost += 0.15

                # D-C16: darakbang boost matrix (verified 멤버만 적용)
                if darakbang_role and darakbang_verified:
                    doc_darakbang_tier = item.metadata.get("darakbang_tier")
                    if doc_darakbang_tier:
                        b = DARAKBANG_BOOST_MATRIX.get((darakbang_role, doc_darakbang_tier), 0.0)
                        boost += b

                item.score += boost

            results.sort(key=lambda x: x.score, reverse=True)

        # D-C24: gospel_core fallback — 결과 없고 사용자가 seeker/uncertain 이면 gospel_core 자료 보충
        if not results and profile and profile.get("salvation_status") in ("unknown", "seeker", "uncertain"):
            from ..config import settings as _s
            if _s.gospel_core_fallback_enabled:
                results = await self._gospel_core_fallback(query, top_n=3)

        return results

    async def _gospel_core_fallback(self, query: str, top_n: int = 3) -> list[RetrievedItem]:
        """D-C24: gospel_core_tag=True 자료 중 query 와 가장 유사한 것을 fallback으로 반환."""
        try:
            from qdrant_client.http import models as qm
            gospel_filter = qm.Filter(must=[
                qm.FieldCondition(key="gospel_core_tag", match=qm.MatchValue(value=True))
            ])
            qv = self.embedder.embed_query(query).tolist()
            hits = self.store.search_dense(qv, top_k=top_n, flt=gospel_filter)
            return [
                RetrievedItem(
                    id=p.id, text=p.text, score=p.score,
                    rrf_score=p.score, dense_rank=i + 1, sparse_rank=None,
                    metadata=p.metadata,
                )
                for i, p in enumerate(hits)
            ]
        except Exception:
            return []





def _bm25_sparse(collection: str, query: str, top_k: int) -> list:
    """자체 Kiwi+BM25 인덱스로 sparse 검색 → RetrievedPoint 리스트 (V2).

    embedded Qdrant 가 BM42 를 못 쓸 때 정확어·성경장절 검색을 부활시킨다.
    인덱스가 비어있으면 [] 반환 (dense-only 로 graceful fallback).
    """
    try:
        from .sparse_index import get_index
        idx = get_index(collection)
        if idx.size() == 0:
            return []
        hits = idx.search(query, top_k=top_k)
        out = []
        for chunk_id, score, payload in hits:
            payload = dict(payload)
            text = payload.pop("text", "")
            out.append(RetrievedPoint(id=str(chunk_id), score=score, text=text, metadata=payload))
        return out
    except Exception:
        return []


def _rrf_fusion(rankings, *, weights=None, k=60):
    weights = weights or [1.0] * len(rankings)
    s = sum(weights) or 1.0
    weights = [w / s for w in weights]
    accum: dict[str, dict] = {}
    rank_keys = ["dense_rank", "sparse_rank"]
    for src_idx, hits in enumerate(rankings):
        for rank, pt in enumerate(hits, start=1):
            key = pt.id
            entry = accum.get(key)
            if entry is None:
                entry = {"point": pt, "rrf": 0.0, "dense_rank": None, "sparse_rank": None}
                accum[key] = entry
            entry["rrf"] += weights[src_idx] * (1.0 / (k + rank))
            entry[rank_keys[src_idx] if src_idx < len(rank_keys) else "dense_rank"] = rank
    return sorted(accum.values(), key=lambda e: e["rrf"], reverse=True)
