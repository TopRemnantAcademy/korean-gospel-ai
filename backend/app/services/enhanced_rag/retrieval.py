"""Enhanced RAG — 하이브리드 검색 (dense + keyword, RRF 융합).

파이프라인:
1. 쿼리 임베딩 → dense 검색 (Qdrant cosine)
2. 쿼리 토큰화   → keyword 검색 (BM25)
3. Reciprocal Rank Fusion(RRF) 로 두 랭킹 결합 → 후보 집합
4. (선택) metadata 필터: doc_id / source 로 후보 제한

필터링은 매니페스트 청크_ids 집합으로 수행 (대규모에서도 안전).
"""
from __future__ import annotations

import asyncio
import logging
import numpy as np
from typing import Optional

from .bm25 import tokenize
from .config import RAGConfig
from .embeddings import RAGEmbedder
from .types import RetrievedChunk
from .vector_store import RAGVectorStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self, config: RAGConfig, embedder: RAGEmbedder, store: RAGVectorStore):
        self.config = config
        self.embedder = embedder
        self.store = store

    def _allowed_ids(self, filters: Optional[dict]) -> Optional[set]:
        """필터 대상 청크 id 집합 반환.

        - 필터 미지정 → None (필터링 안 함)
        - 필터 지정되었으나 매칭 없음 → 빈 집합 set() (아무것도 안 돌려줌)
          (이전 코드는 `allowed or None` 로 빈 집합을 None 으로 바꿔
           전체 코퍼스를 반환하는 버그가 있었음)
        """
        if not filters:
            return None
        doc_id = filters.get("doc_id")
        source = filters.get("source")
        if not doc_id and not source:
            return None
        manifest = self.store._manifest

        doc_ids: set = set()
        if doc_id:
            m = manifest.get(doc_id)
            if m:
                doc_ids = set(m.get("chunk_ids", []))

        src_ids: set = set()
        if source:
            for d, m in manifest.items():
                if m.get("source") == source:
                    src_ids.update(m.get("chunk_ids", []))

        if doc_id and source:
            # doc 가 존재하고 그 source 가 일치할 때만 해당 doc 의 청크
            if manifest.get(doc_id, {}).get("source") == source:
                return doc_ids
            return set()  # doc 존재하나 source 불일치 → 매칭 없음
        if doc_id:
            return doc_ids  # doc 없으면 빈 집합 → 매칭 없음
        return src_ids  # source 전용

    async def retrieve(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        dense_weight: Optional[float] = None,
        sparse_weight: Optional[float] = None,
        rrf_k: Optional[int] = None,
        recall_k: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> list[RetrievedChunk]:
        cfg = self.config
        top_k = top_k or cfg.top_k
        dw = dense_weight if dense_weight is not None else cfg.dense_weight
        sw = sparse_weight if sparse_weight is not None else cfg.sparse_weight
        k = rrf_k or cfg.rrf_k
        rk = recall_k or cfg.recall_k
        allowed = self._allowed_ids(filters)

        vec = await asyncio.to_thread(self.embedder.embed_query, query)
        vec = np.asarray(vec, dtype=float).ravel().tolist()  # numpy→native float list (타입 안정성)
        qtokens = tokenize(query)

        # 주 벡터(중국어 우선) 검색
        dense_primary = await asyncio.to_thread(
            self.store.search_primary, vec, top_k=rk, allowed_ids=allowed
        )
        # 원문 언어 벡터(한국어) 검색 — 이중 저장 시에만
        dense_source: list[dict] = []
        if self.store.has_source_vector and self.store.source_embedder is not None:
            vec_src = await asyncio.to_thread(
                self.store.source_embedder.embed_query, query
            )
            vec_src = np.asarray(vec_src, dtype=float).ravel().tolist()
            dense_source = await asyncio.to_thread(
                self.store.search_source, vec_src, top_k=rk, allowed_ids=allowed
            )

        # 키워드(BM25) 검색
        kw_res = await asyncio.to_thread(
            self.store.search_keyword, qtokens, top_k=rk, allowed_ids=allowed
        )

        # RRF 융합: 세 스트림을 각각 독립 랭킹으로 취급.
        # dense_source 를 dense_primary 뒤에 이어 붙여 하나의 랭킹으로 다루면
        # 한국어 쿼리 매치가 rank≈rk 로 밀려 bilingual 검색이 무력화됨
        # (cross-stream rank inflation). 주/원문 dense + keyword 를 3개
        # 독립 스트림으로 융합한다.
        streams = [
            (dense_primary, dw, "dense"),
            (dense_source, dw, "dense"),   # 동일 dense 가중치 (양 언어 모두 dense)
            (kw_res, sw, "sparse"),
        ]
        fused = self._rrf_fusion_streams(streams, k)
        # 후보 수는 rerank 가 잘라내므로 넉넉히 보관
        cap = max(rk, top_k * 3)
        fused = fused[:cap]

        out: list[RetrievedChunk] = []
        for rank, item in enumerate(fused):
            meta = item["meta"]
            out.append(
                RetrievedChunk(
                    chunk_id=item["chunk_id"],
                    doc_id=item["doc_id"],
                    text=item["text"],
                    dense_score=item["dense_score"],
                    sparse_score=item["sparse_score"],
                    rrf_score=item["rrf"],
                    rank=rank,
                    section=meta.get("section", ""),
                    source=meta.get("source", ""),
                    title=meta.get("title", ""),
                    metadata=meta,
                )
            )
        return out

    @staticmethod
    def _rrf_fusion_streams(
        streams: list[tuple[list[dict], float, str]],
        k: int,
    ) -> list[dict]:
        """여러 독립 랭킹(스트림)을 RRF 로 융합.

        각 스트림 = (ranked_results, weight, kind) 튜플. kind 는
        "dense" | "sparse" 로 원점수 저장 위치를 결정.
        각 스트림은 rank 0 부터 독립적으로 취급되므로, 한 스트림의 결과가
        다른 스트림 뒤에 붙어 rank 가 밀리는 현상(cross-stream rank
        inflation)이 방지된다. 이중 저장(한국어 원문 벡터) 검색이 주(중국어)
        검색에 비해 부당하게 페널티 받는 문제를 해결.
        """
        rrf: dict[str, float] = {}
        points: dict[str, dict] = {}
        dense_map: dict[str, float] = {}
        sparse_map: dict[str, float] = {}

        for results, weight, kind in streams:
            if not results or abs(weight) < 1e-9:
                continue
            is_sparse = kind == "sparse"
            for rank, item in enumerate(results):
                pid = item["chunk_id"]
                points[pid] = item
                rrf[pid] = rrf.get(pid, 0.0) + weight / (k + rank + 1)
                sc = float(item.get("score", 0.0))
                if is_sparse:
                    # sparse(키워드) 점수 보관, dense 는 0.0 기본
                    if sparse_map.get(pid) is None:
                        sparse_map[pid] = sc
                    dense_map.setdefault(pid, 0.0)
                else:
                    if dense_map.get(pid) is None:
                        dense_map[pid] = sc
                    sparse_map.setdefault(pid, 0.0)

        if not rrf:
            return []

        merged = sorted(rrf.keys(), key=lambda x: -rrf[x])
        return [
            {
                "chunk_id": pid,
                "doc_id": points[pid]["doc_id"],
                "text": points[pid]["text"],
                "dense_score": dense_map.get(pid, 0.0),
                "sparse_score": sparse_map.get(pid, 0.0),
                "rrf": rrf[pid],
                "meta": points[pid].get("meta", {}),
            }
            for pid in merged
        ]
