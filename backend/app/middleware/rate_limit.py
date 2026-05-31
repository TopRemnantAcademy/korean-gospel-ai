"""E-B2 + 무료체험 Rate Limit 미들웨어.

무료 티어 정책 (guest):
  - 신규 사용자 → 3일 무료 체험 자동 부여 (trial_expires_at = first_seen_at + 3d)
  - 체험 중 : 3시간당 FREE_TRIAL_3H_LIMIT 회 쿼리 (기본 10회)
  - 체험 만료: 429 + trial_expired 코드 → 프론트엔드에서 결제 페이지 안내

유료 회원 정책 (member | supporter):
  - 3시간 할당량 없음
  - 분당 MAX_MEMBER_RPM 회 (기본 60)

봇 차단:
  - flagged_as_bot=True → 즉시 403
  - 동일 IP 30분 내 5개+ 다른 sub_id → IP 1시간 차단
  - IP 분당 30 req 초과 → 15분 차단

Rate limit 대상 경로: /chat, /chat/stream
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings

# ─── 설정값 ────────────────────────────────────────────────────────────────────
FREE_TRIAL_DAYS = 3          # 무료체험 일수
FREE_TRIAL_3H_LIMIT = 10     # 3시간당 최대 쿼리 수 (무료)
FREE_TRIAL_WINDOW_SEC = 10_800  # 3시간 = 10800초

MAX_GUEST_IP_RPM = 30        # IP 분당 최대 (비회원)
MAX_GUEST_IP_RPH = 200       # IP 시간당 최대 (비회원)
MAX_MEMBER_RPM = 60          # 유료 회원 분당 최대

IP_BLOCK_MINUTES = 15        # IP 초과 시 차단 시간
MULTI_SUB_BLOCK_HOURS = 1    # 다계정 의심 IP 차단 시간
MULTI_SUB_THRESHOLD = 5      # 동일 IP 30분 내 이 수 이상 sub_id → 차단

# ─── 인메모리 버킷 ─────────────────────────────────────────────────────────────
_buckets: dict[str, list[float]] = {}      # {key: [timestamps]}
_blocked_ips: dict[str, float] = {}        # {ip: unblock_at}
_ip_subs: dict[str, dict[str, float]] = {} # {ip: {sub_id: last_seen_ts}}
_3h_buckets: dict[str, list[float]] = {}   # {sub_id: [timestamps]} — 3h 윈도우

# 구독 정보 캐시 (5분 TTL): {sub_id: (tier, trial_expires_at, flagged, cached_at)}
_sub_cache: dict[str, tuple] = {}
_SUB_CACHE_TTL = 300


# ─── 헬퍼 ──────────────────────────────────────────────────────────────────────
def _clean(ts_list: list[float], window: float) -> list[float]:
    cutoff = time.time() - window
    return [t for t in ts_list if t >= cutoff]


def _count(key: str, window: float, store: dict) -> int:
    ts = _clean(store.get(key, []), window)
    store[key] = ts
    return len(ts)


def _hit(key: str, store: dict, max_keep: int = 500) -> None:
    ts = store.get(key, [])
    ts.append(time.time())
    store[key] = ts[-max_keep:]


def _is_rate_path(path: str) -> bool:
    return path.startswith("/chat")


def _track_ip_sub(ip: str, sub_id: str) -> int:
    now = time.time()
    cutoff = now - 1800  # 30분
    subs = {k: v for k, v in (_ip_subs.get(ip) or {}).items() if v >= cutoff}
    subs[sub_id] = now
    _ip_subs[ip] = subs
    return len(subs)


# ─── DB 조회 (캐시 포함) ────────────────────────────────────────────────────────
def _get_sub_info(sub_id: str) -> tuple[str, Optional[datetime], bool]:
    """(subscription_tier, trial_expires_at, flagged_as_bot). 5분 캐시."""
    if sub_id == "anon":
        return "guest", None, False

    now = time.time()
    cached = _sub_cache.get(sub_id)
    if cached and now - cached[3] < _SUB_CACHE_TTL:
        return cached[0], cached[1], cached[2]

    try:
        from ..db import get_session
        from ..models.orm import Subscriber
        with get_session() as s:
            row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
            if row:
                tier = row.subscription_tier or "guest"
                trial_exp = row.trial_expires_at
                flagged = bool(row.flagged_as_bot)
                _sub_cache[sub_id] = (tier, trial_exp, flagged, now)
                return tier, trial_exp, flagged
    except Exception:
        pass

    return "guest", None, False


# ─── 3시간 윈도우 쿼리 카운터 ──────────────────────────────────────────────────
def _count_3h(sub_id: str) -> int:
    ts = _clean(_3h_buckets.get(sub_id, []), FREE_TRIAL_WINDOW_SEC)
    _3h_buckets[sub_id] = ts
    return len(ts)


def _hit_3h(sub_id: str) -> None:
    ts = _3h_buckets.get(sub_id, [])
    ts.append(time.time())
    _3h_buckets[sub_id] = ts[-200:]


def _next_3h_reset(sub_id: str) -> int:
    """현재 윈도우가 리셋되기까지 남은 초."""
    ts = _clean(_3h_buckets.get(sub_id, []), FREE_TRIAL_WINDOW_SEC)
    if not ts:
        return 0
    oldest = min(ts)
    return max(0, int(oldest + FREE_TRIAL_WINDOW_SEC - time.time()))


# ─── 미들웨어 ──────────────────────────────────────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)
        if not _is_rate_path(request.url.path):
            return await call_next(request)

        ip = (request.client.host if request.client else "unknown") or "unknown"
        sub_id = request.query_params.get("user_id") or "anon"

        # ── 1) IP 차단 확인 ───────────────────────────────────────────────────
        unblock_at = _blocked_ips.get(ip, 0)
        if time.time() < unblock_at:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "ip_blocked",
                    "retry_after_seconds": int(unblock_at - time.time()),
                    "message": "너무 많은 요청이 감지되었습니다. 잠시 후 다시 시도해주세요.",
                },
            )

        # ── 2) 구독 정보 조회 (캐시) ──────────────────────────────────────────
        tier, trial_exp, flagged = _get_sub_info(sub_id)

        # ── 3) 봇 플래그 → 즉시 차단 ─────────────────────────────────────────
        if flagged:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "account_suspended",
                    "message": "계정이 정지되었습니다. 문의: support@gospel-ai.kr",
                },
            )

        is_paid = tier in ("member", "supporter")

        # ── 4) 무료체험 만료 확인 (guest만) ──────────────────────────────────
        if not is_paid and sub_id != "anon" and trial_exp is not None:
            if datetime.utcnow() > trial_exp:
                return JSONResponse(
                    status_code=402,
                    content={
                        "error": "trial_expired",
                        "message": (
                            "3일 무료 체험이 종료되었습니다. "
                            "회원제를 구매하면 계속 이용하실 수 있어요."
                        ),
                        "expired_at": trial_exp.isoformat(),
                    },
                )

        # ── 5) IP 분당/시간당 제한 (비회원) ──────────────────────────────────
        ip_min_key = f"ip_min:{ip}"
        ip_hr_key = f"ip_hr:{ip}"

        if not is_paid:
            ip_min = _count(ip_min_key, 60, _buckets)
            ip_hr = _count(ip_hr_key, 3600, _buckets)

            if ip_min >= MAX_GUEST_IP_RPM:
                _blocked_ips[ip] = time.time() + IP_BLOCK_MINUTES * 60
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "blocked_minutes": IP_BLOCK_MINUTES,
                        "message": f"{IP_BLOCK_MINUTES}분 후 다시 시도해주세요.",
                    },
                )
            if ip_hr >= MAX_GUEST_IP_RPH:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "1시간 후 다시 시도해주세요.",
                    },
                )

        # ── 6) 유료 회원 분당 제한 ───────────────────────────────────────────
        if is_paid:
            sub_min = _count(f"sub_min:{sub_id}", 60, _buckets)
            if sub_min >= MAX_MEMBER_RPM:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "잠시 후 다시 시도해주세요. (분당 요청 한도)",
                    },
                )

        # ── 7) 무료체험 3시간 쿼리 할당량 ────────────────────────────────────
        if not is_paid and sub_id != "anon":
            q_3h = _count_3h(sub_id)
            if q_3h >= FREE_TRIAL_3H_LIMIT:
                reset_secs = _next_3h_reset(sub_id)
                reset_min = max(1, reset_secs // 60)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "trial_quota_exceeded",
                        "message": (
                            f"무료 체험 할당량({FREE_TRIAL_3H_LIMIT}회/3시간)을 초과했습니다. "
                            f"약 {reset_min}분 후 다시 이용 가능합니다."
                        ),
                        "retry_after_seconds": reset_secs,
                        "quota": FREE_TRIAL_3H_LIMIT,
                        "window_hours": 3,
                    },
                )

        # ── 8) 다계정 의심 (동일 IP 30분 내 여러 sub_id) ─────────────────────
        unique_subs = _track_ip_sub(ip, sub_id)
        if unique_subs >= MULTI_SUB_THRESHOLD:
            _blocked_ips[ip] = time.time() + MULTI_SUB_BLOCK_HOURS * 3600
            await _flag_ip_subs_as_bot(ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "suspicious_activity",
                    "blocked_hours": MULTI_SUB_BLOCK_HOURS,
                    "message": "비정상 접속 패턴이 감지되었습니다.",
                },
            )

        # ── 9) 히트 기록 ─────────────────────────────────────────────────────
        _hit(ip_min_key, _buckets)
        _hit(ip_hr_key, _buckets)
        if not is_paid and sub_id != "anon":
            _hit_3h(sub_id)

        return await call_next(request)


# ─── 봇 플래그 처리 ────────────────────────────────────────────────────────────
async def _flag_ip_subs_as_bot(ip: str) -> None:
    """동일 IP에서 발견된 모든 sub_id를 자동 차단."""
    try:
        from ..db import get_session
        from ..models.orm import Subscriber
        subs = list((_ip_subs.get(ip) or {}).keys())
        with get_session() as s:
            for sid in subs:
                row = s.query(Subscriber).filter(Subscriber.subscriber_id == sid).first()
                if row:
                    row.flagged_as_bot = True
                    row.bot_score = 1.0
                # 캐시 무효화
                _sub_cache.pop(sid, None)
    except Exception:
        pass


# ─── 구독 업그레이드 헬퍼 (관리자 API에서 호출) ────────────────────────────────
def invalidate_sub_cache(sub_id: str) -> None:
    """구독 정보 변경 시 캐시 강제 갱신."""
    _sub_cache.pop(sub_id, None)
