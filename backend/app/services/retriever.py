"""Hybrid Retriever.

주요 기능:
- Query Optimizer 기반 쿼리 타입 분석과 동적 가중치 적용
- dense/sparse 검색 결과 RRF 결합
- reranker 적용 및 프로필 기반 soft boost
- retriever 인스턴스 캐시
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-29
# Task: Database Grade Upgrade v3
# =============================================================================
from __future__ import annotations
import logging
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from ..config import settings
from .embedding.factory import get_embedder
from .vector_store import QdrantStore, RetrievedPoint
from .reranker import get_reranker, NoOpReranker
from .search_optimizer import analyze_query, analyze_query_async
from .cache_monitor import cache_monitor
# 프로필 부스트 매트릭스/로직은 enhanced_rag.profile_boost 에서 단일 소스로 관리 (Wave C/E 단일화)
from .enhanced_rag.profile_boost import compute_profile_boost


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedItem:
    id: str
    text: str
    score: float
    rrf_score: float
    dense_rank: int | None
    sparse_rank: int | None
    metadata: dict


# ── retriever 캐시 (매 요청마다 재생성 방지) ──
_retriever_cache: dict[tuple[str, str], "HybridRetriever"] = {}
_retriever_lock = threading.RLock()


def get_retriever(embedder_name: str | None = None, collection: str | None = None) -> "HybridRetriever":
    """모듈-레벨 캐시에서 retriever 반환."""
    key = (embedder_name or settings.embedder, collection or "")

    # 캐시된 retriever가 있으면 바로 반환
    if key in _retriever_cache:
        return _retriever_cache[key]

    with _retriever_lock:
        # Double-check: 락 대기 중 다른 쓰레드가 초기화했을 수 있음
        if key in _retriever_cache:
            return _retriever_cache[key]

        _retriever_cache[key] = HybridRetriever(embedder_name=embedder_name, collection=collection)
        return _retriever_cache[key]


def _rrf_fusion(
    rankings: list[list[dict]],
    weights: list[float],
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion: 여러 랭킹 리스트를 하나로 합침."""
    scores: dict[str, float] = {}
    points: dict[str, Any] = {}
    dense_ranks: dict[str, int] = {}
    sparse_ranks: dict[str, int] = {}

    for list_idx, (rank_list, weight) in enumerate(zip(rankings, weights)):
        if abs(weight) < 1e-9:
            continue
        for rank, item in enumerate(rank_list):
            # Defensive: dense/sparse(Qdrant) pass RetrievedPoint objects,
            # BM25 fallback passes {"point": RetrievedPoint} dicts.
            point = item["point"] if isinstance(item, dict) else item
            if point is None:
                continue
            pid = point.id
            points[pid] = item["point"]
            scores[pid] = scores.get(pid, 0.0) + weight / (k + rank + 1)
            if list_idx == 0:
                dense_ranks[pid] = rank
            else:
                sparse_ranks[pid] = rank

    if not scores:
        return []

    # RRF 점수 기준 정렬
    sorted_pids = sorted(scores.keys(), key=lambda x: -scores[x])
    return [
        {
            "id": pid,
            "rrf": scores[pid],
            "point": points[pid],
            "dense_rank": dense_ranks.get(pid),
            "sparse_rank": sparse_ranks.get(pid),
        }
        for pid in sorted_pids
    ]


def _merge_duplicate_candidates_fast(items: list[dict]) -> list[dict]:
    """중복 후보 병합."""
    if not items:
        return []

    scores: dict[str, float] = {}
    point_map: dict[str, Any] = {}

    for item in items:
        pid = item["id"]
        point = item["point"]
        point_map[pid] = point
        scores[pid] = scores.get(pid, 0.0) + item["rrf"]

    sorted_pids = sorted(scores.keys(), key=lambda x: -scores[x])
    return [
        {"id": pid, "rrf": scores[pid], "point": point_map[pid]}
        for pid in sorted_pids
    ]


def _bm25_sparse(collection: str, query: str, top_k: int) -> list[dict]:
    """메모리 BM25 인덱스로 sparse 검색."""
    from .sparse_index import get_index
    idx = get_index(collection)
    results = idx.search(query, top_k=top_k)
    return [
        {
            "point": RetrievedPoint(
                id=chunk_id,
                score=score,
                text=payload.get("text", ""),
                metadata=payload,
            )
        }
        for chunk_id, score, payload in results
    ]


class HybridRetriever:
    _CACHE_TTL_SEC = 1800  # 30분 - 검색 쿼리는 반복성이 매우 높음

    def __init__(
        self, embedder_name: str | None = None, reranker=None, collection: str | None = None
    ):
        self.embedder_name = embedder_name or settings.embedder
        self.embedder = get_embedder(self.embedder_name)
        self.store = QdrantStore(self.embedder_name, dim=self.embedder.dim, collection=collection)
        # Reranker: get_reranker 내부에서 이미 fail-open(NoOp) 을 보장하지만,
        # 혹시 모를 예외로부터 채팅 경로를 이중 보호한다.
        try:
            self.reranker = reranker or get_reranker(
                settings.reranker, cohere_api_key=settings.cohere_api_key
            )
        except Exception as _rexc:
            logger.warning(
                "[retriever] reranker 초기화 예외(%s: %s) → NoOp 폴백",
                type(_rexc).__name__, _rexc,
            )
            self.reranker = NoOpReranker()
        self._cache: "OrderedDict[tuple, tuple[list[RetrievedItem], float]]" = OrderedDict()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        rerank_top_n: int | None = None,
        dense_weight: float | None = None,
        sparse_weight: float | None = None,
        profile: Any = None,
        dense_query: str | None = None,
        sparse_query: str | None = None,
    ) -> list[RetrievedItem]:
        import asyncio as _asyncio

        # ══════════════════════════════════════════════════════════════
        # Stage 0: 쿼리 분석 — Query Optimizer
        # ══════════════════════════════════════════════════════════════
        qa = await analyze_query_async(query)

        # 명시적 파라미터 > 옵티마이저 추론 > 기본값
        top_k = top_k or settings.retrieval_top_k
        rerank_top_n = rerank_top_n or settings.rerank_top_n
        dw = dense_weight if dense_weight is not None else qa.dense_weight
        sw = sparse_weight if sparse_weight is not None else qa.sparse_weight

        # 캐시 조회: 프로필은 영향있는 필드만 hash 키로 사용
        cache_profile = None
        if profile:
            # NOTE: faith_stage 는 compute_profile_boost 가 사용하지 않으므로 캐시키에서 제외
            # (영향 없는 필드로 인한 불필요한 캐시 미스 방지).
            cache_profile = (
                profile.get("salvation_status", "unknown"),
                profile.get("darakbang_role"),
                bool(profile.get("is_darakbang_member")),
                bool(profile.get("darakbang_verified")),
                bool(profile.get("assume_saved")),
            )
        cache_key = (
            query,
            top_k,
            rerank_top_n,
            dw,
            sw,
            cache_profile,
            dense_query,
            sparse_query,
        )
        if cache_key in self._cache:
            cached_results, cached_at = self._cache[cache_key]
            if time.time() - cached_at < self._CACHE_TTL_SEC:
                # LRU: hit 시 최근 사용으로 갱신
                self._cache.move_to_end(cache_key)
                start = time.perf_counter()
                # 호출자가 수정할 수도 있으므로 list만 새로 만듦 (얕은 복사)
                result = list(cached_results)
                latency = (time.perf_counter() - start) * 1000
                cache_monitor.track_retrieval(hit=True, latency_ms=latency)
                return result

        # 캐시 미스 타이머 시작
        _retrieval_start = time.perf_counter()

        # ══════════════════════════════════════════════════════════════
        # Stage 1: Coarse Recall — 최대한 많은 후보 모으기
        # ══════════════════════════════════════════════════════════════
        # 최적화: recall_k 를 고정 200 에서 top_k 비례 + 하한으로 축소.
        # 대규모 데이터에서 Qdrant 탐색량을 크게 줄여 응답 지연을 낮춘다.
        recall_k = max(top_k * settings.recall_k_per_topk, settings.recall_k_floor)
        _store = self.store
        _collection = _store.collection

        # 다중 쿼리 병렬 검색: 모든 확장 쿼리에 대해 dense + sparse 동시 실행
        # 최적화: 2번째 확장 쿼리부터 recall_k 를 감쇠시켜 전체 호출량 감축.
        # (원본 쿼리가 가장 중요 → 100%, 이후 쿼리는 보조적 탐색으로 축소)
        all_candidates = []
        tasks = []

        for qi, eq in enumerate(qa.expanded_queries):
            # 첫 번째(원본) 쿼리는 full recall, 이후는 decay 적용
            q_recall_k = recall_k if qi == 0 else max(
                settings.recall_k_floor // 2,
                int(recall_k * (settings.multi_query_recall_decay ** qi)),
            )

            async def _search_one(q: str, rk: int = q_recall_k):
                async def _dense_one():
                    qv = await _asyncio.to_thread(self.embedder.embed_query, q)
                    return await _asyncio.to_thread(
                        _store.search_dense, qv.tolist(), top_k=rk
                    )

                async def _sparse_one():
                    sres = await _asyncio.to_thread(
                        _store.search_sparse, q, top_k=rk
                    )
                    if not sres:
                        sres = await _asyncio.to_thread(
                            _bm25_sparse, _collection, q, rk
                        )
                    return sres

                d_res, s_res = await _asyncio.gather(_dense_one(), _sparse_one())

                # search_dense / search_sparse return list[RetrievedPoint];
                # _bm25_sparse (fallback) returns list[{"point": RetrievedPoint}].
                # Normalize every item to the dict shape _rrf_fusion expects,
                # but KEEP the list-of-rank-lists structure (one per sub-search)
                # so it aligns with `weights` via zip().
                def _normalize(results):
                    return [
                        {"point": r} if not isinstance(r, dict) else r
                        for r in results
                    ]

                rankings = [_normalize(d_res)]
                if s_res:
                    rankings.append(_normalize(s_res))
                weights = [dw, sw] if s_res else [1.0]
                return _rrf_fusion(rankings, weights=weights, k=settings.rrf_k)

            tasks.append(_search_one(eq))

        # 모든 쿼리의 검색 결과 동시 수집
        fused_results = await _asyncio.gather(*tasks)
        for fr in fused_results:
            all_candidates.extend(fr)

        # ══════════════════════════════════════════════════════════════
        # Stage 2: 중복 병합 - 여러 쿼리에서 나온 같은 문서 점수 합산
        # ══════════════════════════════════════════════════════════════
        if len(qa.expanded_queries) > 1 and all_candidates:
            merged = _merge_duplicate_candidates_fast(all_candidates)
            merged.sort(key=lambda x: -x["rrf"])
            final_for_rerank = merged[:max(rerank_top_n * 4, 30)]  # 최적화: 100→30]
        else:
            pid_set = set()
            unique = []
            for c in sorted(all_candidates, key=lambda x: -x["rrf"]):
                if c["id"] not in pid_set:
                    pid_set.add(c["id"])
                    unique.append(c)
            final_for_rerank = unique[:max(rerank_top_n * 4, 30)]  # 최적화: 100→30]

        # ══════════════════════════════════════════════════════════════
        # Stage 3: Fine Rank — rerank로 최종 순위 정밀화
        # ══════════════════════════════════════════════════════════════
        if not final_for_rerank:
            return []

        _docs = [it["point"].text for it in final_for_rerank]
        try:
            rerank_scores = await _asyncio.to_thread(self.reranker.rerank, query, _docs)
        except Exception:
            logger.exception("[retriever] reranker.rerank 실패")
            rerank_scores = None

        # V2: RRF(0.3) + rerank(0.7) 결합 점수 먼저 계산
        if rerank_scores is None or getattr(self.reranker, "name", "") == "none":
            for it in final_for_rerank:
                it["final_score"] = it["rrf"]
        else:
            for it, rr_score in zip(final_for_rerank, rerank_scores):
                it["final_score"] = it["rrf"] * 0.3 + float(rr_score) * 0.7

        # ✅ 부스트는 단일 곱셈자(additive 결합)로 적용해 enhanced_rag/pipeline._apply_profile_boost
        # 와 공식 일치 (base*(1+tb+pb)). 기존 곱셈형 base*(1+tb)*(1+pb) 는 같은 부스트 합에 대해
        # pipeline 결과와 수치가 달라, eval A/B 비교(승격) 전제를 깨뜨림 (MEMORY 단일 소스 불변식).
        if qa.preferred_filters or (profile and settings.retriever_boost_enabled):
            for item in final_for_rerank:
                boost = 0.0
                if qa.preferred_filters:
                    meta = item["point"].metadata
                    if qa.preferred_filters.get("gospel_core_tag") and meta.get("gospel_core_tag"):
                        boost += 0.20
                if profile and settings.retriever_boost_enabled:
                    boost += compute_profile_boost(item["point"].metadata or {}, profile)
                if boost:
                    item["final_score"] *= 1.0 + boost

        final_for_rerank.sort(key=lambda it: it["final_score"], reverse=True)
        final_for_rerank = final_for_rerank[:rerank_top_n]

        results = [
            RetrievedItem(
                id=it["point"].id,
                text=it["point"].text,
                score=it["final_score"],
                rrf_score=it["rrf"],
                dense_rank=it.get("dense_rank"),
                sparse_rank=it.get("sparse_rank"),
                metadata=it["point"].metadata,
            )
            for it in final_for_rerank
        ]

        _retrieval_latency = (time.perf_counter() - _retrieval_start) * 1000
        cache_monitor.track_retrieval(hit=False, latency_ms=_retrieval_latency)

        # 캐시 저장 + 크기 제한 (OrderedDict LRU — O(1) eviction)
        self._cache[cache_key] = (results, time.time())
        while len(self._cache) > 1500:
            self._cache.popitem(last=False)  # 가장 오래된 항목 제거

        return list(results)
