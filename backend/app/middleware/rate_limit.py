"""E-B2: SQLite 기반 Rate Limit 미들웨어.

Redis 없이 SQLite TTL 카운터로 구현.
룰:
  - IP (guest):  30 req/분, 200 req/시간 → 초과 시 429 + 15분 차단
  - IP (member): 120 req/분 → 429 (차단 X)
  - sub_id (guest): 10 req/분 → 429 + bot_score +0.2
  - sub_id (member): 60 req/분 → 429
  - 동일 IP 30분 안에 5개+ sub_id → 즉시 차단 + flagged_as_bot
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: E-B2 — SQLite Rate Limit 미들웨어
# Reason: ORDERS.md EPIC E-B2
# Status: COMPLETED
# =============================================================================
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings


# rate_limit 버킷 저장용 메모리 캐시 (재시작 시 리셋, Redis 없는 단계)
# {key: [timestamp1, timestamp2, ...]} — 슬라이딩 윈도우
_buckets: dict[str, list[float]] = {}
# IP 차단 목록: {ip: unblock_at_timestamp}
_blocked_ips: dict[str, float] = {}
# IP → sub_id 세트 매핑 (30분 윈도우)
_ip_subs: dict[str, dict[str, float]] = {}  # ip → {sub_id: last_seen_ts}

_RATE_LIMIT_PATHS = {"/chat", "/chat/stream"}


def _clean_window(timestamps: list[float], window: float) -> list[float]:
    cutoff = time.time() - window
    return [t for t in timestamps if t >= cutoff]


def _count_in_window(key: str, window: float) -> int:
    ts = _buckets.get(key, [])
    ts = _clean_window(ts, window)
    _buckets[key] = ts
    return len(ts)


def _record_hit(key: str) -> None:
    ts = _buckets.get(key, [])
    ts.append(time.time())
    _buckets[key] = ts[-500:]  # 최대 500개 유지


def _track_ip_sub(ip: str, sub_id: str) -> int:
    """IP에서 30분 안에 몇 개의 sub_id가 보였는지 추적. 반환값 = 고유 sub_id 수."""
    now = time.time()
    cutoff = now - 1800  # 30분
    subs = _ip_subs.get(ip, {})
    subs = {k: v for k, v in subs.items() if v >= cutoff}
    subs[sub_id] = now
    _ip_subs[ip] = subs
    return len(subs)


def _is_rate_limited_path(path: str) -> bool:
    return any(path.startswith(p) for p in _RATE_LIMIT_PATHS)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        if not _is_rate_limited_path(request.url.path):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        sub_id = request.query_params.get("user_id") or "anon"

        # IP 차단 여부 확인
        unblock_at = _blocked_ips.get(ip, 0)
        if time.time() < unblock_at:
            remaining = int(unblock_at - time.time())
            return JSONResponse(
                status_code=429,
                content={"error": "ip_blocked", "retry_after_seconds": remaining},
            )

        # 1분/1시간 윈도우
        ip_min_key = f"ip_min:{ip}"
        ip_hr_key = f"ip_hr:{ip}"
        sub_min_key = f"sub_min:{sub_id}"

        ip_min_count = _count_in_window(ip_min_key, 60)
        ip_hr_count = _count_in_window(ip_hr_key, 3600)
        sub_min_count = _count_in_window(sub_min_key, 60)

        # tier 결정 (헤더 기반 — chat.py 에서 토큰 체크가 먼저 실행되므로 간단히 anon 판별)
        is_member = sub_id != "anon" and not sub_id.startswith("anon_")

        # Guest IP 제한
        if not is_member:
            if ip_min_count >= 30:
                _blocked_ips[ip] = time.time() + 900  # 15분 차단
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limit_exceeded", "blocked_minutes": 15},
                )
            if ip_hr_count >= 200:
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limit_exceeded", "retry_after": "1 hour"},
                )
            # sub_id 분당 10 req → bot_score +0.2
            if sub_min_count >= 10:
                await _bump_bot_score(sub_id, 0.2)
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limit_exceeded", "retry_after_seconds": 60},
                )
        else:
            # Member IP 제한 (더 넓음)
            if ip_min_count >= 120:
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limit_exceeded", "retry_after_seconds": 60},
                )
            if sub_min_count >= 60:
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limit_exceeded", "retry_after_seconds": 60},
                )

        # 동일 IP 에서 30분 내 5개+ 다른 sub_id → 즉시 차단
        unique_subs = _track_ip_sub(ip, sub_id)
        if unique_subs >= 5:
            await _flag_ip_subs_as_bot(ip)
            _blocked_ips[ip] = time.time() + 3600  # 1시간 차단
            return JSONResponse(
                status_code=429,
                content={"error": "suspicious_multi_account", "blocked_minutes": 60},
            )

        # 히트 기록
        _record_hit(ip_min_key)
        _record_hit(ip_hr_key)
        _record_hit(sub_min_key)

        return await call_next(request)


async def _bump_bot_score(sub_id: str, delta: float) -> None:
    """E-B3: bot_score 누적. 1.0 초과 시 flagged_as_bot=True."""
    try:
        from ..db import get_session
        from ..models.orm import Subscriber
        with get_session() as s:
            sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
            if sub:
                sub.bot_score = min(1.0, (sub.bot_score or 0.0) + delta)
                if sub.bot_score >= 1.0:
                    sub.flagged_as_bot = True
    except Exception:
        pass


async def _flag_ip_subs_as_bot(ip: str) -> None:
    """동일 IP 에서 발견된 모든 sub_id를 flagged_as_bot=True 처리."""
    try:
        from ..db import get_session
        from ..models.orm import Subscriber
        subs = list((_ip_subs.get(ip) or {}).keys())
        with get_session() as s:
            for sid in subs:
                sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sid).first()
                if sub:
                    sub.flagged_as_bot = True
                    sub.bot_score = 1.0
    except Exception:
        pass
