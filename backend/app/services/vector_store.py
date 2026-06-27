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
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Optional, Sequence
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ..config import settings


@dataclass
class RetrievedPoint:
    id: str
    score: float
    text: str
    metadata: dict


_BM42_MODEL = "Qdrant/bm42-all-minilm-l6-v2-attentions"


_client_cache: dict[str, tuple[QdrantClient, bool]] = {}
_client_lock = Lock()


def _build_client(url: str) -> tuple[QdrantClient, bool]:
    """returns (client, is_server_mode). server mode일 때만 sparse 지원."""
    if url.startswith("local:"):
        path = url.split(":", 1)[1] or "./.qdrant_local"
        return QdrantClient(path=path), False
    if url in {"memory:", ":memory:", "memory"}:
        return QdrantClient(location=":memory:"), False
    # server mode
    return QdrantClient(url=url, api_key=settings.qdrant_api_key or None, prefer_grpc=False), True


def _make_client() -> tuple[QdrantClient, bool]:
    """프로세스당 URL별로 단일 QdrantClient 재사용.

    embedded(local) 모드는 스토리지 폴더에 파일 락을 잡기 때문에 같은 경로로
    두 번째 클라이언트를 열면 "already accessed by another instance" 오류가 난다.
    memory 모드도 인스턴스마다 별도 DB라 캐시가 정확성에 필요하다.
    """
    url = (settings.qdrant_url or "").strip()
    cached = _client_cache.get(url)
    if cached is not None:
        return cached
    with _client_lock:
        cached = _client_cache.get(url)
        if cached is not None:
            return cached
        client = _build_client(url)
        _client_cache[url] = client
        return client


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
