"""일일 질문 수 할당량 (IP 익명 티어 + 로그인 티어, 2026-07-23).

정책:
- 익명(IP): 하루 1회. IP + 브라우저 UUID 이중바인딩(둘 중 먼저 찬 게 기준)으로 우회 방지.
- 로그인: 구독 티어별 한도 (free/standard/premium). 평생 회원(lifetime)은 무한.
- KST 자정 리셋. question_quota 테이블에 일별 카운트 보관(다중 worker/재기동 안전).
"""
from __future__ import annotations

import datetime
import time
import logging
from typing import Optional

_log = logging.getLogger(__name__)

from ..db import get_session
from ..models.orm import QuestionQuota, Subscriber
from ..config import settings
from . import settings_service

KST = datetime.timezone(datetime.timedelta(hours=9))

_TIER_KEYS = {
    "anonymous": "quota_anonymous_daily",
    "free": "quota_free_daily",
    "standard": "quota_standard_daily",
    "premium": "quota_premium_daily",
    "lifetime": "quota_lifetime_daily",
}


def _kst_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone(KST)


def _today_str() -> str:
    return _kst_now().strftime("%Y-%m-%d")


def _reset_in_hours() -> float:
    n = _kst_now()
    midnight = n.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    return max(0.0, (midnight - n).total_seconds() / 3600.0)


def tier_limit(tier: str) -> int:
    key = _TIER_KEYS.get(tier, "quota_free_daily")
    default = getattr(settings, key, 10)
    return settings_service.get_int(key, default)


def is_enabled() -> bool:
    return settings_service.get_bool("question_quota_enabled", settings.question_quota_enabled)


def _check_key(key: str, tier: str, limit: int, increment: bool) -> dict:
    """단일 키 카운트. increment=False 면 잔여만 조회(소비 안 함).

    SQLite 단일 라이터 경합(database is locked) 시 재시도. 모든 재시도가 실패하면
    fail-open(허용) 처리해 500 서비스 거부를 막는다. (소비 차감이 한 번 누락되는 것은
    허용 — 할당량 초과 사용자에게 500 을 띄우는 것보다 낫다.)
    """
    from sqlalchemy.exc import OperationalError
    today = _today_str()
    last_exc = None
    for _attempt in range(6):
        try:
            with get_session() as s:
                row = s.query(QuestionQuota).filter(QuestionQuota.key == key).first()
                if not row or row.date_str != today:
                    count = 0
                else:
                    count = row.count
                allowed = count < limit
                if increment and allowed:
                    count += 1
                    if not row:
                        row = QuestionQuota(key=key, date_str=today, count=count, tier=tier)
                        s.add(row)
                    else:
                        row.date_str = today
                        row.count = count
                        row.tier = tier
                    s.flush()
                remaining = max(0, limit - count)
                return {
                    "allowed": allowed,
                    "remaining": remaining,
                    "daily_limit": limit,
                    "tier": tier,
                    "reset_in_hours": round(_reset_in_hours(), 1),
                }
        except OperationalError as _e:
            last_exc = _e
            time.sleep(0.05)
    _log.warning("[QUOTA] DB lock (%s) — fail-open 처리: %s", key, last_exc)
    return {
        "allowed": True,
        "remaining": limit,
        "daily_limit": limit,
        "tier": tier,
        "reset_in_hours": round(_reset_in_hours(), 1),
    }


def _anon_result(ip: str, uuid: str) -> dict:
    """IP + UUID 이중바인딩: 둘 중 먼저 찬 게 기준(더 엄격한 쪽 적용)."""
    limit = tier_limit("anonymous")
    r_ip = _check_key("ip:" + ip, "anonymous", limit, increment=True)
    r_uuid = _check_key("sub:" + uuid, "anonymous", limit, increment=True) if uuid else None
    if r_uuid is None:
        return r_ip
    # 둘 다 허용돼야 허용. 잔여는 둘 중 작은 값.
    allowed = r_ip["allowed"] and r_uuid["allowed"]
    remaining = min(r_ip["remaining"], r_uuid["remaining"])
    return {
        "allowed": allowed,
        "remaining": remaining,
        "daily_limit": limit,
        "tier": "anonymous",
        "reset_in_hours": r_ip["reset_in_hours"],
    }


def _loggedin_result(sub: Subscriber) -> dict:
    tier = "lifetime" if sub.is_lifetime_member else (sub.subscription_tier or "free")
    limit = tier_limit(tier)
    return _check_key("sub:" + sub.subscriber_id, tier, limit, increment=True)


def check_quota(*, sub: Optional[Subscriber] = None, ip: str = "", uuid: str = "") -> dict:
    """질문 1회 소비. 반환값으로 허용 여부/잔여 판단."""
    if not is_enabled():
        # 할당량 비활성화 → 무한 허용 (잔여는 free 한도로 표시)
        return {
            "allowed": True,
            "remaining": tier_limit("lifetime" if (sub and sub.is_lifetime_member)
                                    else (sub.subscription_tier if sub else "free")),
            "daily_limit": tier_limit("lifetime" if (sub and sub.is_lifetime_member)
                                      else (sub.subscription_tier if sub else "free")),
            "tier": "lifetime" if (sub and sub.is_lifetime_member)
            else (sub.subscription_tier if sub else "anonymous"),
            "reset_in_hours": round(_reset_in_hours(), 1),
            "disabled": True,
        }
    if sub is not None:
        return _loggedin_result(sub)
    return _anon_result(ip, uuid)


def quota_status(*, sub: Optional[Subscriber] = None, ip: str = "", uuid: str = "") -> dict:
    """소비 없이 잔여만 조회 (프론트 표시/429 재발송 UI)."""
    if sub is not None:
        tier = "lifetime" if sub.is_lifetime_member else (sub.subscription_tier or "free")
        limit = tier_limit(tier)
        # 소비 없이 잔여 계산
        today = _today_str()
        with get_session() as s:
            row = s.query(QuestionQuota).filter(
                QuestionQuota.key == "sub:" + sub.subscriber_id
            ).first()
            count = 0 if (not row or row.date_str != today) else row.count
        return {
            "tier": tier,
            "remaining": max(0, limit - count),
            "daily_limit": limit,
            "reset_in_hours": round(_reset_in_hours(), 1),
            "enabled": is_enabled(),
        }
    limit = tier_limit("anonymous")
    today = _today_str()
    with get_session() as s:
        rip = s.query(QuestionQuota).filter(QuestionQuota.key == "ip:" + ip).first()
        cnt_ip = 0 if (not rip or rip.date_str != today) else rip.count
    return {
        "tier": "anonymous",
        "remaining": max(0, limit - cnt_ip),
        "daily_limit": limit,
        "reset_in_hours": round(_reset_in_hours(), 1),
        "enabled": is_enabled(),
    }
