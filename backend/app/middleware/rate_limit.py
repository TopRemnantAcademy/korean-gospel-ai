from __future__ import annotations

import random
import time
from typing import Callable, Optional

import asyncio

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings

# 환경변수(RATE_LIMIT_ENABLED / RATE_LIMIT_PER_MINUTE)로 제어. 미설정 시 기본 60 RPM.
MAX_IP_RPM = settings.rate_limit_per_minute
MAX_IP_RPH = settings.rate_limit_per_minute * 10
IP_BLOCK_MINUTES = 15

# 속도 제한 적용 경로 (LLM 비용/남용 표면): 채팅 + 인증 + ingest + admin + documents (P4 #3)
_RATE_PREFIXES = ("/chat", "/auth", "/rag", "/admin", "/documents", "/support")

_buckets: dict[str, list[float]] = {}
_blocked_ips: dict[str, float] = {}
# [PERF] 버킷 키 상한 — 초과 시 만료/비활성 키 정리로 메모리 무한성장 방지
_BUCKETS_MAX = 10000

# Redis 공유 버킷 (다중 worker 일관성). 미설정 시 프로세스 내 버킷 사용.
_rl_redis: Optional[object] = None
_rl_redis_tried = False

# 백그라운드 태스크 참조 보관 — GC 방지
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg_task(coro) -> None:
    """asyncio.create_task 참조를 보관하여 예기치 않은 GC 를 방지."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _get_redis():
    """Redis 클라이언트를 한 번만 생성해 캐시(연결 풀 재사용). 실패 시 None."""
    global _rl_redis, _rl_redis_tried
    if _rl_redis_tried:
        return _rl_redis
    _rl_redis_tried = True
    url = getattr(settings, "redis_url", None)
    if not url:
        return None
    try:
        import redis

        _rl_redis = redis.Redis.from_url(url, socket_timeout=1)
        return _rl_redis
    except Exception:
        return None


def _real_client_ip(request: Request) -> str:
    """실제 클라이언트 IP (P4 #3).

    신뢰 프록시 뒤에서는 X-Forwarded-For 의 **가장 오른쪽 hop** 을 사용한다.
    XFF 형식은 `client, proxy1, proxy2` 이며, 신뢰 프록시가 수신한 요청 IP 를
    끝에 append 하므로 맨 **왼쪽** hop 은 공격자가 임의로 조작할 수 있어 신뢰하면 안 된다
    (매번 다른 XFF 를 보내면 익명 할당량/rate limit 이 무제한 우회됨).
    단일 신뢰 프록시(nginx 등) 환경이 아니면 rate_limit_trust_proxy=False 권장.
    """
    if getattr(settings, "rate_limit_trust_proxy", True):
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            if hops:
                return hops[-1]
        xri = request.headers.get("X-Real-IP")
        if xri:
            return xri.strip()
    return (request.client.host if request.client else "unknown") or "unknown"


def _clean(ts_list: list[float], window: float) -> list[float]:
    cutoff = time.time() - window
    return [t for t in ts_list if t >= cutoff]


def _redis_count(key: str, window: float) -> int:
    r = _get_redis()
    if r is None:
        return 0
    now = time.time()
    r.zremrangebyscore(key, 0, now - window)  # 만료 항목 정리
    return r.zcard(key)


def _redis_hit(key: str, window: float) -> None:
    r = _get_redis()
    if r is None:
        return
    now = time.time()
    r.zremrangebyscore(key, 0, now - window)
    r.zadd(key, {f"{now}:{random.random()}": now})
    r.expire(key, int(window) + 5)


def _count(key: str, window: float) -> int:
    r = _get_redis()
    if r is not None:
        try:
            return _redis_count(key, window)
        except Exception:
            pass
    ts = _clean(_buckets.get(key, []), window)
    _buckets[key] = ts
    return len(ts)


def _hit(key: str, window: float, max_keep: int = 1000) -> None:
    r = _get_redis()
    if r is not None:
        try:
            _redis_hit(key, window)
            return
        except Exception:
            pass
    ts = _buckets.get(key, [])
    is_new = not ts
    ts.append(time.time())
    _buckets[key] = ts[-max_keep:]
    # [PERF] 새 키 추가로 상한 초과 시에만 정리(정리 후에도 초과하면 오래된 키 제거)
    if is_new and len(_buckets) > _BUCKETS_MAX:
        _global_cleanup()
        while len(_buckets) > _BUCKETS_MAX:
            _buckets.pop(next(iter(_buckets)))


def _global_cleanup() -> None:
    """모든 속도 제한 딕셔너리에서 만료된 항목 정리.

    ⚠️ 순회 중 딕셔너리 크기를 변경하면 RuntimeError 가 발생하므로,
    삭제 대상 key 를 먼저 복사(list)한 뒤 순회한다.
    """
    now = time.time()
    expired_ips = [ip for ip, unblock_at in _blocked_ips.items() if now >= unblock_at]
    for ip in expired_ips:
        _blocked_ips.pop(ip, None)
    # [PERF] 빈 키 + 1시간(hour 윈도우) 이상 활동 없는 키 제거 → 메모리 무한성장 방지
    stale_keys = [k for k, v in _buckets.items() if not v or v[-1] < now - 3600]
    for k in stale_keys:
        _buckets.pop(k, None)


def _is_rate_path(path: str) -> bool:
    return any(path.startswith(p) for p in _RATE_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _is_rate_path(request.url.path):
            return await call_next(request)

        # RATE_LIMIT_ENABLED=false 면 속도 제한 비활성화 (env로 토글)
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # 확률적 전역 정리 (1% 확률)
        if random.random() < 0.01:
            _global_cleanup()

        ip = _real_client_ip(request)
        unblock_at = _blocked_ips.get(ip, 0)
        now = time.time()
        if now < unblock_at:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(int(unblock_at - now))},
                content={
                    "error": "ip_blocked",
                    "retry_after_seconds": int(unblock_at - now),
                    "message": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
                },
            )

        min_key = f"ip_min:{ip}"
        hr_key = f"ip_hr:{ip}"
        if _count(min_key, 60) >= MAX_IP_RPM:
            _blocked_ips[ip] = now + IP_BLOCK_MINUTES * 60
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(IP_BLOCK_MINUTES * 60)},
                content={
                    "error": "rate_limit_exceeded",
                    "blocked_minutes": IP_BLOCK_MINUTES,
                    "message": f"{IP_BLOCK_MINUTES}분 후 다시 시도해주세요.",
                },
            )
        if _count(hr_key, 3600) >= MAX_IP_RPH:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(3600)},
                content={
                    "error": "rate_limit_exceeded",
                    "message": "1시간 후 다시 시도해주세요.",
                },
            )

        _hit(min_key, 60)
        _hit(hr_key, 3600)
        response = await call_next(request)
        # 클라이언트가 자율 제어할 수 있도록 표준 Rate-Limit 헤더 부여
        response.headers["X-RateLimit-Limit"] = str(MAX_IP_RPM)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, MAX_IP_RPM - _count(min_key, 60))
        )
        return response
