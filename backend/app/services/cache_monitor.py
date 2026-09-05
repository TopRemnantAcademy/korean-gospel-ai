"""캐시 적중률 모니터링 시스템.

임베딩 캐시와 검색 캐시의 효과를 측정하고 추적합니다:
- 시간별 히트율 추적
- 레이턴시 개선 효과 측정 (히트 vs 미스)
- 캐시 크기와 효율성 모니터링
- 주기적 통계 출력

사용법:
    monitor = CacheMonitor()
    monitor.track_embedding(hit=True, latency_ms=1.2)
    monitor.track_retrieval(hit=True, latency_ms=45.0)
    stats = monitor.get_stats()
    monitor.print_dashboard()
"""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional


@dataclass
class CacheEvent:
    """단일 캐시 이벤트"""
    timestamp: float
    hit: bool
    latency_ms: float
    cache_type: str  # "embedding" or "retrieval"


@dataclass
class TimeWindowStats:
    """시간 윈도우별 통계"""
    window_minutes: int
    embedding_hits: int = 0
    embedding_misses: int = 0
    embedding_hit_latency_avg: float = 0.0
    embedding_miss_latency_avg: float = 0.0
    retrieval_hits: int = 0
    retrieval_misses: int = 0
    retrieval_hit_latency_avg: float = 0.0
    retrieval_miss_latency_avg: float = 0.0


class CacheMonitor:
    """캐시 성능 모니터"""

    _instance: Optional["CacheMonitor"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_events: int = 10000):
        if self._initialized:
            return
        self._initialized = True

        self.max_events = max_events
        self.events: Deque[CacheEvent] = deque(maxlen=max_events)

        # 임베딩 캐시 카운터
        self.embedding_hits = 0
        self.embedding_misses = 0
        self.embedding_hit_latency_total = 0.0
        self.embedding_miss_latency_total = 0.0

        # 검색 캐시 카운터
        self.retrieval_hits = 0
        self.retrieval_misses = 0
        self.retrieval_hit_latency_total = 0.0
        self.retrieval_miss_latency_total = 0.0

        # 시작 시간
        self.start_time = time.time()

    def track_embedding(self, hit: bool, latency_ms: float) -> None:
        """임베딩 캐시 이벤트 추적"""
        self.events.append(CacheEvent(
            timestamp=time.time(),
            hit=hit,
            latency_ms=latency_ms,
            cache_type="embedding",
        ))
        if hit:
            self.embedding_hits += 1
            self.embedding_hit_latency_total += latency_ms
        else:
            self.embedding_misses += 1
            self.embedding_miss_latency_total += latency_ms

    def track_retrieval(self, hit: bool, latency_ms: float) -> None:
        """검색 캐시 이벤트 추적"""
        self.events.append(CacheEvent(
            timestamp=time.time(),
            hit=hit,
            latency_ms=latency_ms,
            cache_type="retrieval",
        ))
        if hit:
            self.retrieval_hits += 1
            self.retrieval_hit_latency_total += latency_ms
        else:
            self.retrieval_misses += 1
            self.retrieval_miss_latency_total += latency_ms

    def get_stats(self) -> Dict[str, Any]:
        """전체 통계 반환"""
        uptime_sec = time.time() - self.start_time

        # 임베딩
        emb_total = self.embedding_hits + self.embedding_misses
        emb_hit_rate = self.embedding_hits / emb_total if emb_total > 0 else 0.0
        emb_hit_avg = (
            self.embedding_hit_latency_total / self.embedding_hits
            if self.embedding_hits > 0 else 0.0
        )
        emb_miss_avg = (
            self.embedding_miss_latency_total / self.embedding_misses
            if self.embedding_misses > 0 else 0.0
        )
        emb_speedup = emb_miss_avg / emb_hit_avg if emb_hit_avg > 0 else 1.0

        # 검색
        ret_total = self.retrieval_hits + self.retrieval_misses
        ret_hit_rate = self.retrieval_hits / ret_total if ret_total > 0 else 0.0
        ret_hit_avg = (
            self.retrieval_hit_latency_total / self.retrieval_hits
            if self.retrieval_hits > 0 else 0.0
        )
        ret_miss_avg = (
            self.retrieval_miss_latency_total / self.retrieval_misses
            if self.retrieval_misses > 0 else 0.0
        )
        ret_speedup = ret_miss_avg / ret_hit_avg if ret_hit_avg > 0 else 1.0

        return {
            "uptime_sec": round(uptime_sec, 1),
            "uptime_hours": round(uptime_sec / 3600, 2),
            "embedding": {
                "hits": self.embedding_hits,
                "misses": self.embedding_misses,
                "total": emb_total,
                "hit_rate": round(emb_hit_rate, 4),
                "hit_latency_avg_ms": round(emb_hit_avg, 3),
                "miss_latency_avg_ms": round(emb_miss_avg, 3),
                "speedup_factor": round(emb_speedup, 1),
            },
            "retrieval": {
                "hits": self.retrieval_hits,
                "misses": self.retrieval_misses,
                "total": ret_total,
                "hit_rate": round(ret_hit_rate, 4),
                "hit_latency_avg_ms": round(ret_hit_avg, 3),
                "miss_latency_avg_ms": round(ret_miss_avg, 3),
                "speedup_factor": round(ret_speedup, 1),
            },
            "buffer_size": len(self.events),
            "buffer_max": self.max_events,
        }

    def get_time_window_stats(self, minutes: int = 5) -> Dict[str, Any]:
        """최근 N분 동안의 통계 반환"""
        now = time.time()
        cutoff = now - (minutes * 60)

        emb_hits = emb_misses = 0
        emb_hit_lat = emb_miss_lat = 0.0
        ret_hits = ret_misses = 0
        ret_hit_lat = ret_miss_lat = 0.0

        for ev in reversed(self.events):
            if ev.timestamp < cutoff:
                break
            if ev.cache_type == "embedding":
                if ev.hit:
                    emb_hits += 1
                    emb_hit_lat += ev.latency_ms
                else:
                    emb_misses += 1
                    emb_miss_lat += ev.latency_ms
            else:  # retrieval
                if ev.hit:
                    ret_hits += 1
                    ret_hit_lat += ev.latency_ms
                else:
                    ret_misses += 1
                    ret_miss_lat += ev.latency_ms

        emb_total = emb_hits + emb_misses
        ret_total = ret_hits + ret_misses

        return {
            "window_minutes": minutes,
            "embedding": {
                "hits": emb_hits,
                "misses": emb_misses,
                "hit_rate": emb_hits / emb_total if emb_total else 0.0,
                "hit_latency_avg_ms": emb_hit_lat / emb_hits if emb_hits else 0.0,
                "miss_latency_avg_ms": emb_miss_lat / emb_misses if emb_misses else 0.0,
            },
            "retrieval": {
                "hits": ret_hits,
                "misses": ret_misses,
                "hit_rate": ret_hits / ret_total if ret_total else 0.0,
                "hit_latency_avg_ms": ret_hit_lat / ret_hits if ret_hits else 0.0,
                "miss_latency_avg_ms": ret_miss_lat / ret_misses if ret_misses else 0.0,
            },
        }

    def print_dashboard(self, live: bool = False) -> None:
        """모니터링 대시보드 출력"""
        stats = self.get_stats()
        recent = self.get_time_window_stats(5)  # 최근 5분

        # 클리어 (라이브 모드일때)
        if live:
            print("\033[H\033[J", end="")

        print("\n" + "=" * 72)
        print("📊 캐시 모니터링 대시보드")
        print("=" * 72)
        print(f" 가동 시간: {stats['uptime_hours']:.1f}시간")
        print(f" 이벤트 버퍼: {stats['buffer_size']:,}/{stats['buffer_max']:,}")

        # === 임베딩 캐시 ===
        print("\n" + "─" * 72)
        print("🔤 임베딩 캐시")
        print("─" * 72)
        emb = stats["embedding"]
        emb_recent = recent["embedding"]

        # 히트율 바
        hr = emb["hit_rate"] * 100
        bar = "█" * int(hr // 5) + "░" * (20 - int(hr // 5))
        hr_recent = emb_recent["hit_rate"] * 100
        bar_recent = "█" * int(hr_recent // 5) + "░" * (20 - int(hr_recent // 5))

        print(f"  {'총계':<12} {emb['hits']:>8,} hits / {emb['misses']:>8,} misses")
        print(f"  {'누적 적중률':<12} [{bar}] {hr:.1f}%")
        print(f"  {'최근 5분':<12} [{bar_recent}] {hr_recent:.1f}%")
        print(f"\n  {'레이턴시':<12} 히트: {emb['hit_latency_avg_ms']:>8.2f}ms "
              f"| 미스: {emb['miss_latency_avg_ms']:>8.2f}ms")
        print(f"  {'측정 비율':<12} {emb['speedup_factor']:>8.1f}x")

        # === 검색 캐시 ===
        print("\n" + "─" * 72)
        print("🔍 검색 캐시")
        print("─" * 72)
        ret = stats["retrieval"]
        ret_recent = recent["retrieval"]

        hr = ret["hit_rate"] * 100
        bar = "█" * int(hr // 5) + "░" * (20 - int(hr // 5))
        hr_recent = ret_recent["hit_rate"] * 100
        bar_recent = "█" * int(hr_recent // 5) + "░" * (20 - int(hr_recent // 5))

        print(f"  {'총계':<12} {ret['hits']:>8,} hits / {ret['misses']:>8,} misses")
        print(f"  {'누적 적중률':<12} [{bar}] {hr:.1f}%")
        print(f"  {'최근 5분':<12} [{bar_recent}] {hr_recent:.1f}%")
        print(f"\n  {'레이턴시':<12} 히트: {ret['hit_latency_avg_ms']:>8.2f}ms "
              f"| 미스: {ret['miss_latency_avg_ms']:>8.2f}ms")
        print(f"  {'측정 비율':<12} {ret['speedup_factor']:>8.1f}x")

        # === 요약 ===
        print("\n" + "─" * 72)
        total_saved_ms = (
            (emb["miss_latency_avg_ms"] - emb["hit_latency_avg_ms"]) * emb["hits"] +
            (ret["miss_latency_avg_ms"] - ret["hit_latency_avg_ms"]) * ret["hits"]
        )
        print(f"💡 총 절약 시간: {total_saved_ms / 1000:.1f}초 "
              f"({total_saved_ms / 3600000:.2f}시간)")
        print("=" * 72 + "\n")

    def reset(self) -> None:
        """모든 통계 초기화"""
        self._initialized = False
        self.__init__(max_events=self.max_events)


# 전역 싱글톤 인스턴스
cache_monitor = CacheMonitor()
