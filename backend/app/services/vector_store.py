"""Qdrant 어댑터.

3가지 모드 지원:
1. **embedded (local path)** - 기본. Docker/서버 불필요.
     QDRANT_URL=local:./.qdrant_local
2. **server** - Docker 또는 Qdrant Cloud
     QDRANT_URL=http://localhost:6333  또는  https://xxx.qdrant.tech (+ QDRANT_API_KEY)
3. **memory** - 테스트용. 종료시 데이터 사라짐.
     QDRANT_URL=memory:

Hybrid(dense + sparse BM42)는 server 모드에서만 지원.
embedded/memory 모드는 자동으로 dense-only fallback.
"""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Sequence
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ..config import settings

logger = logging.getLogger(__name__)

@dataclass
class RetrievedPoint:
    id: str
    score: float
    text: str
    metadata: dict


_BM42_MODEL = "Qdrant/bm42-all-minilm-l6-v2-attentions"

# ─── Qdrant 클라이언트 수동 캐시 ──────────────────────────────────────────────
# lru_cache 대신 수동 캐시 사용 이유:
#   - lru_cache는 성공/실패 모두 캐시하거나(return 기반) 예외를 캐시하지 않음
#   - embedded 모드에서 프로세스 잠금 충돌 시 초기화 실패 가능 → 재시도 필요
#   - 성공 시에만 캐시, 실패 시 (None, False) 반환 후 다음 요청에서 재시도
_client_instance: tuple | None = None  # (QdrantClient, is_server_bool) | None
_client_lock = threading.Lock()


def _build_qdrant_client() -> tuple[QdrantClient, bool]:
    """실제 QdrantClient 생성. 실패 시 예외 발생."""
    url = (settings.qdrant_url or "").strip()
    if url.startswith("local:"):
        raw_path = url.split(":", 1)[1] or "./.qdrant_local"
        from pathlib import Path as _Path
        path = str((_Path(settings.root_dir) / raw_path).resolve())
        logger.info("[vector_store] Qdrant embedded 모드: %s", path)
        return QdrantClient(path=path), False
    if url in {"memory:", ":memory:", "memory"}:
        logger.info("[vector_store] Qdrant memory 모드")
        return QdrantClient(location=":memory:"), False
    logger.info("[vector_store] Qdrant server 모드: %s", url)
    return QdrantClient(
        url=url,
        api_key=settings.qdrant_api_key or None,
        prefer_grpc=False,
    ), True


def _make_client() -> tuple[QdrantClient | None, bool]:
    """(QdrantClient | None, is_server: bool) 반환.

    ※ 성공 시에만 모듈 수준 캐시에 저장. 실패 시 (None, False) 반환 후 재시도 가능.
      embedded 모드: 다른 프로세스가 잠금을 쥔 경우 초기화 실패 → 잠금 해제 후 재시도.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance
    with _client_lock:
        if _client_instance is not None:  # double-check
            return _client_instance
        try:
            result = _build_qdrant_client()
            _client_instance = result
            return result
        except Exception as exc:
            logger.warning(
                "[vector_store] Qdrant 초기화 실패 (재시도 가능): %s", exc
            )
            return (None, False)  # 캐시 안 함 → 다음 호출 시 재시도


@lru_cache(maxsize=1)
def _sparse_encoder():
    from fastembed import SparseTextEmbedding
    return SparseTextEmbedding(model_name=_BM42_MODEL)


def _to_sparse(text: str) -> qm.SparseVector:
    enc = _sparse_encoder()
    out = next(enc.embed([text]))
    return qm.SparseVector(indices=out.indices.tolist(), values=out.values.tolist())


def _to_sparse_batch(texts: Sequence[str]) -> list[qm.SparseVector]:
    enc = _sparse_encoder()
    return [
        qm.SparseVector(indices=o.indices.tolist(), values=o.values.tolist())
        for o in enc.embed(list(texts))
    ]


class QdrantStore:
    def __init__(self, embedder_name: str, dim: int, collection: str | None = None):
        self.embedder_name = embedder_name
        self.dim = dim
        self.collection = collection or settings.collection_name(embedder_name)
        self.client, self.is_server = _make_client()
        if self.client is None:
            raise RuntimeError(
                "Qdrant 클라이언트를 초기화할 수 없어요. "
                "QDRANT_URL 설정을 확인하거나 잠시 후 다시 시도해 주세요."
            )
        # embedded/memory 모드는 sparse 비지원 (qdrant-client local engine 제한).
        # 또한 qdrant_sparse_enabled가 꺼져 있으면 메모리(fastembed 로딩) 절약을 위해 비활성화.
        self.use_sparse = self.is_server and settings.qdrant_sparse_enabled
        self._ensure_collection()

    # ---------- collection ----------
    def _ensure_collection(self):
        try:
            existing = {c.name for c in self.client.get_collections().collections}
        except Exception:
            existing = set()
        if self.collection in existing:
            return

        vectors_config = {"dense": qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE)}
        sparse_config = (
            {"sparse": qm.SparseVectorParams(modifier=qm.Modifier.IDF)}
            if self.use_sparse else None
        )
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_config,
        )

    def reset(self):
        try:
            self.client.delete_collection(self.collection)
        except Exception:
            pass
        self._ensure_collection()

    def delete_where(self, flt: qm.Filter) -> None:
        """필터 조건에 맞는 포인트 삭제. N15: 옛 published 청크 정리."""
        try:
            self.client.delete(
                collection_name=self.collection,
                points_selector=qm.FilterSelector(filter=flt),
                wait=True,
            )
        except Exception:
            pass

    # ---------- upsert ----------
    def upsert(
        self,
        *,
        ids: Sequence[str] | None,
        texts: Sequence[str],
        dense_vectors: Sequence[Sequence[float]],
        metadatas: Sequence[dict],
    ):
        assert len(texts) == len(dense_vectors) == len(metadatas)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        sparses = _to_sparse_batch(texts) if self.use_sparse else [None] * len(texts)

        points = []
        for pid, text, dv, sp, meta in zip(ids, texts, dense_vectors, sparses, metadatas):
            payload = dict(meta)
            payload["text"] = text
            vector = {"dense": list(dv)}
            if sp is not None:
                vector["sparse"] = sp
            points.append(qm.PointStruct(id=pid, vector=vector, payload=payload))
        self.client.upsert(collection_name=self.collection, points=points, wait=True)

    # ---------- search ----------
    def search_dense(
        self,
        query_vec: Sequence[float],
        *,
        top_k: int = 20,
        flt: Optional[qm.Filter] = None,
    ) -> list[RetrievedPoint]:
        res = self.client.query_points(
            collection_name=self.collection,
            query=list(query_vec),
            using="dense",
            limit=top_k,
            with_payload=True,
            query_filter=flt,
        ).points
        return [_to_retrieved(p) for p in res]

    def search_sparse(
        self,
        query_text: str,
        *,
        top_k: int = 20,
        flt: Optional[qm.Filter] = None,
    ) -> list[RetrievedPoint]:
        if not self.use_sparse:
            return []  # dense-only fallback
        try:
            sp = _to_sparse(query_text)
            res = self.client.query_points(
                collection_name=self.collection,
                query=sp, using="sparse", limit=top_k,
                with_payload=True, query_filter=flt,
            ).points
            return [_to_retrieved(p) for p in res]
        except Exception:
            return []


def _to_retrieved(p) -> RetrievedPoint:
    payload = p.payload or {}
    text = payload.pop("text", "")
    return RetrievedPoint(
        id=str(p.id),
        score=float(p.score),
        text=text,
        metadata=payload,
    )
