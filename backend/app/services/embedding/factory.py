"""Embedder Factory.

주요 기능:
- TTL LRU 캐시
- 임베더 인스턴스 캐시
- 캐시 통계 추적

엔드포인트:
- get_embedder(name): 이름으로 임베더 반환
- cache_stats(): 전역 캐시 통계
- clear_all_caches(): 모든 캐시 비우기
"""
from __future__ import annotations
import time
import threading
from collections import OrderedDict
from typing import Hashable, Sequence

import numpy as np

from .base import BaseEmbedder
from ..cache_monitor import cache_monitor


class _TTLLRUCache:
    """TTL이 있는 LRU 캐시."""

    def __init__(self, max_items: int = 8192, ttl_sec: int = 3600):
        self._max = max_items
        self._ttl = ttl_sec
        self._cache: OrderedDict[Hashable, tuple[float, np.ndarray]] = OrderedDict()
        self._lock = threading.RLock()

        # 카운터 분리: stats() 호출시 락을 짧게 유지
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> np.ndarray | None:
        """캐시 조회."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            ts, val = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None

            self._cache.move_to_end(key)
            self._hits += 1
            return val

    def put(self, key: str, value: np.ndarray) -> None:
        """단일 항목 추가."""
        with self._lock:
            now = time.time()
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = (now, value)

            # LRU eviction
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)

    def put_batch(self, keys: Sequence[str], values: Sequence[np.ndarray]) -> None:
        """배치로 캐시 채우기."""
        with self._lock:
            now = time.time()
            for k, v in zip(keys, values):
                if k in self._cache:
                    del self._cache[k]
                self._cache[k] = (now, v)

            # LRU eviction
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)

    def stats(self) -> dict:
        """통계 반환 - 락을 짧게 유지하기 위해 원자적 연산만."""
        with self._lock:
            total = self._hits + self._misses
            ratio = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": round(ratio, 4),
                "ttl_sec": self._ttl,
            }

    def clear(self) -> None:
        """모든 캐시 비우기."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# ── 전역 캐시: 쿼리 임베딩 (가장 자주 호출되므로 가장 큼) ──
_QUERY_CACHE = _TTLLRUCache(max_items=8192, ttl_sec=3600)


class CachedEmbedder:
    """원본 embedder를 감싸서 캐시와 통계를 추가."""

    __slots__ = ("_inner", "name", "model_id", "_dim")  # 메모리 절약

    def __init__(self, inner: BaseEmbedder):
        self._inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self._dim = inner.dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_query(self, text: str) -> np.ndarray:
        """단일 쿼리 임베딩 - 캐시 우선."""
        cache_key = (self.name, self._dim, text)
        cached = _QUERY_CACHE.get(cache_key)
        if cached is not None:
            cache_monitor.track_embedding(hit=True, latency_ms=0.01)
            return cached

        # 캐시 미스 - 실제 계산 필요
        start = time.perf_counter()

        # [PERF] 추론을 락 밖에서 실행해 동시 요청의 임베딩을 병렬화한다.
        # _QUERY_CACHE.get/put 은 자체 RLock 으로 스레드 안전하므로, 이전의
        # self._lock(DCL) 은 캐시 보호에 불필요했고 추론 직렬화만 유발했다.
        # (동일 텍스트 동시 미스 시 중복 계산 1회는 허용 — 쿼리는 대개 유일.)
        vec = self._inner.embed_query(text)
        _QUERY_CACHE.put(cache_key, vec)

        latency = (time.perf_counter() - start) * 1000
        cache_monitor.track_embedding(hit=False, latency_ms=latency)
        return vec

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """배치 임베딩.

        처리 과정:
        1. 모든 텍스트에 대해 캐시 조회
        2. 미스된 텍스트만 배치로 계산
        3. 결과를 캐시에 백필
        4. 원래 순서대로 조립
        """
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)

        n = len(texts)
        result = np.empty((n, self._dim), dtype=np.float32)
        missed_indices = []
        missed_texts = []

        start = time.perf_counter()

        # 1) 캐시 히트된 것 먼저 결과에 채우기
        for i, t in enumerate(texts):
            cache_key = (self.name, self._dim, t)
            v = _QUERY_CACHE.get(cache_key)
            if v is not None:
                result[i] = v
            else:
                missed_indices.append(i)
                missed_texts.append(t)

        # 2) 모두 캐시 히트면 바로 반환
        hit_count = n - len(missed_indices)
        if not missed_indices:
            latency = (time.perf_counter() - start) * 1000
            for _ in range(hit_count):
                cache_monitor.track_embedding(hit=True, latency_ms=latency / hit_count)
            return result

        # 3) 미스된 것만 배치 임베딩 — 락 밖에서 실행해 병렬화 (캐시는 자체 RLock 으로 스레드 안전)
        if missed_texts:
            miss_vecs = self._inner.embed_documents(missed_texts)

            # 4) 새로 계산된 것을 캐시에 백필
            miss_keys = [(self.name, self._dim, txt) for txt in missed_texts]
            _QUERY_CACHE.put_batch(miss_keys, miss_vecs)

            # 5) 결과에 채우기
            for dest_i, vec in zip(missed_indices, miss_vecs):
                result[dest_i] = vec

        # 통계 기록
        latency = (time.perf_counter() - start) * 1000
        total_miss = len(missed_indices)
        total_hit = n - total_miss

        if total_hit > 0:
            hit_latency = latency * 0.1 / total_hit  # 캐시 조회 시간 추정
            for _ in range(total_hit):
                cache_monitor.track_embedding(hit=True, latency_ms=hit_latency)

        if total_miss > 0:
            miss_latency = latency * 0.9 / total_miss  # 계산 시간 추정
            for _ in range(total_miss):
                cache_monitor.track_embedding(hit=False, latency_ms=miss_latency)

        return result

    @property
    def inner(self) -> BaseEmbedder:
        """원본 임베더 직접 접근이 필요할 때."""
        return self._inner

    @staticmethod
    def cache_stats() -> dict:
        """글로벌 쿼리 캐시 통계."""
        return _QUERY_CACHE.stats()

    @staticmethod
    def clear_cache() -> None:
        """글로벌 캐시 완전 비우기."""
        _QUERY_CACHE.clear()


# ── 임베더 인스턴스 캐시 (모델 로딩 비싸므로) ──
_embedder_lock = threading.RLock()
_embedder_cache: dict[str, CachedEmbedder] = {}


def get_embedder(name: str) -> CachedEmbedder:
    """이름으로 임베더 반환."""
    n = name.lower().strip()
    if n in _embedder_cache:
        return _embedder_cache[n]

    with _embedder_lock:
        if n in _embedder_cache:
            return _embedder_cache[n]

        if n in {"kure", "kure_v1", "kurev1"}:
            from .kure import KureEmbedder
            emb = KureEmbedder()
        elif n in {"bge_m3", "bge-m3", "bge"}:
            from .bge import BgeM3Embedder
            emb = BgeM3Embedder()
        elif n in {"e5", "e5_large", "multilingual_e5"}:
            from .e5 import E5Embedder
            emb = E5Embedder()
        elif n in {"hf_inference", "hf-inference", "hf"}:
            from .hf_inference import HfInferenceEmbedder
            emb = HfInferenceEmbedder()
        elif n in {"voyage", "voyage_3", "voyage-3"}:
            from .voyage import VoyageEmbedder
            emb = VoyageEmbedder()
        elif n in {"hash", "local_hash", "test"}:
            from .hash_embedder import HashEmbedder
            emb = HashEmbedder()
        else:
            raise ValueError(f"Unknown embedder: {name}")

        wrapped = CachedEmbedder(emb)
        _embedder_cache[n] = wrapped
        return wrapped


def list_supported() -> list[str]:
    """지원하는 임베더 목록."""
    return ["kure", "bge_m3", "e5", "hf_inference", "voyage", "hash"]


def cache_stats() -> dict:
    """전역 캐시 통계."""
    return CachedEmbedder.cache_stats()


def clear_all_caches() -> None:
    """모든 캐시 비우기 (테스트/벤치마크용)."""
    CachedEmbedder.clear_cache()
    with _embedder_lock:
        _embedder_cache.clear()
