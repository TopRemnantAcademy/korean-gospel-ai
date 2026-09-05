"""비동기 안전 LRU 캐시 — 메모리 누수 방지 + Race condition 방지.

기존 dict 기반 캐시의 문제점:
1. 동시 요청시 race condition 발생 가능
2. 크기 제한이 없어 메모리 누수 위험
3. clear() 방식은 순간적으로 성능 저하

개선점:
- asyncio.Lock 으로 동시 접근 동기화
- OrderedDict 기반 LRU eviction
- 크기 제한으로 메모리 누수 방지
- TTL 지원
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Optional


class AsyncLRUCache:
    """비동기 안전 LRU 캐시.

    Args:
        max_size: 최대 캐시 항목 수 (기본 1000)
        ttl_seconds: 항목별 TTL (초). None 이면 무제한.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: Optional[float] = None):
        self._cache: OrderedDict[Any, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: Any) -> Optional[Any]:
        """캐시에서 값 가져오기.

        Returns:
            값. 없거나 만료됐으면 None.
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expire_at = self._cache[key]

            if self._ttl is not None and time.time() > expire_at:
                del self._cache[key]
                self._misses += 1
                return None

            self._cache.move_to_end(key)
            self._hits += 1
            return value

    async def set(self, key: Any, value: Any) -> None:
        """캐시에 값 저장.

        가득 찼으면 가장 오래된 항목부터 제거 (LRU).
        """
        async with self._lock:
            expire_at = time.time() + self._ttl if self._ttl else float('inf')

            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (value, expire_at)
                return

            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = (value, expire_at)

    async def has(self, key: Any) -> bool:
        """키 존재 여부 확인 (만료 체크 포함)."""
        return await self.get(key) is not None

    async def clear(self) -> None:
        """캐시 전체 비우기."""
        async with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        """캐시 통계 반환."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
        }

    def __len__(self) -> int:
        return len(self._cache)
