"""E-A: 토큰 쿼터 서비스 — 3 bucket (bonus > monthly > daily) 소진 로직.

사용법:
    quote = await check_and_consume(sub_id, estimated_tokens=2000)
    if not quote.allowed:
        raise 429 with quota info

    # ... 응답 생성 ...

    await finalize_consumption(sub_id, actual_tokens, estimated=2000)
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: E-A — token_service.py 신규 파일
#       3 bucket 쿼터 (bonus > monthly > daily) + finalize + signup bonus
# Reason: ORDERS.md EPIC E-A2
# Status: COMPLETED
# =============================================================================
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import settings
from ..db import get_session
from ..models.orm import Subscriber


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class TokenQuoteResult:
    allowed: bool
    remaining_daily: int
    remaining_monthly: int
    remaining_bonus: int
    bucket_used: str        # "bonus" | "monthly" | "daily" | "none"
    reset_in_hours: Optional[int]
    sub_id: str


def _tier_monthly_limit(tier: str) -> int:
    mapping = {
        "member": settings.tokens_monthly_member,
        "supporter": settings.tokens_monthly_supporter,
        "darakbang": settings.tokens_monthly_darakbang,
    }
    return mapping.get(tier, 0)


def _reset_daily_if_needed(sub: Subscriber) -> bool:
    """일일 풀 리셋 필요 여부 확인 + 리셋. True = 리셋했음."""
    now = _utcnow()
    if sub.tokens_daily_reset_at is None or sub.tokens_daily_reset_at.date() < now.date():
        sub.tokens_daily = settings.tokens_daily_guest
        sub.tokens_daily_reset_at = datetime(now.year, now.month, now.day, 0, 0, 0)
        return True
    return False


def _reset_monthly_if_needed(sub: Subscriber) -> bool:
    """월간 풀 리셋 필요 여부 확인 + 리셋. True = 리셋했음."""
    now = _utcnow()
    monthly_limit = _tier_monthly_limit(sub.subscription_tier)
    if monthly_limit == 0:
        return False
    if sub.tokens_monthly_reset_at is None or (
        sub.tokens_monthly_reset_at.year < now.year or
        sub.tokens_monthly_reset_at.month < now.month
    ):
        sub.tokens_monthly = monthly_limit
        sub.tokens_monthly_reset_at = datetime(now.year, now.month, 1, 0, 0, 0)
        return True
    return False


def check_and_consume_sync(sub_id: str, estimated_tokens: int) -> TokenQuoteResult:
    """DB session 안에서 동기 실행. check_and_consume 의 실제 구현."""
    if not settings.token_quota_enabled:
        return TokenQuoteResult(
            allowed=True, remaining_daily=999999, remaining_monthly=999999,
            remaining_bonus=999999, bucket_used="none", reset_in_hours=None, sub_id=sub_id,
        )

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub is None:
            return TokenQuoteResult(
                allowed=True, remaining_daily=settings.tokens_daily_guest,
                remaining_monthly=0, remaining_bonus=0,
                bucket_used="none", reset_in_hours=None, sub_id=sub_id,
            )

        _reset_daily_if_needed(sub)
        _reset_monthly_if_needed(sub)

        now = _utcnow()
        next_reset = datetime(now.year, now.month, now.day, 0, 0, 0) + timedelta(days=1)
        reset_in_hours = int((next_reset - now).total_seconds() / 3600)

        # 총 가용 토큰 먼저 확인 — 부족하면 bucket 건드리지 않고 즉시 거절
        total_available = (sub.tokens_bonus or 0) + (sub.tokens_monthly or 0) + (sub.tokens_daily or 0)
        if total_available < estimated_tokens:
            return TokenQuoteResult(
                allowed=False,
                remaining_daily=sub.tokens_daily or 0,
                remaining_monthly=sub.tokens_monthly or 0,
                remaining_bonus=sub.tokens_bonus or 0,
                bucket_used="none",
                reset_in_hours=reset_in_hours,
                sub_id=sub_id,
            )

        # 소진 순서: bonus → monthly → daily
        remaining = estimated_tokens
        bucket = "none"

        if sub.tokens_bonus >= remaining:
            sub.tokens_bonus -= remaining
            bucket = "bonus"
            remaining = 0
        elif sub.tokens_bonus > 0:
            remaining -= sub.tokens_bonus
            sub.tokens_bonus = 0

        if remaining > 0 and sub.tokens_monthly >= remaining:
            sub.tokens_monthly -= remaining
            bucket = "monthly" if bucket == "none" else bucket
            remaining = 0
        elif remaining > 0 and sub.tokens_monthly > 0:
            remaining -= sub.tokens_monthly
            sub.tokens_monthly = 0

        if remaining > 0 and sub.tokens_daily >= remaining:
            sub.tokens_daily -= remaining
            bucket = "daily" if bucket == "none" else bucket
            remaining = 0

        allowed = remaining == 0

        if allowed:
            sub.tokens_lifetime_used = (sub.tokens_lifetime_used or 0) + estimated_tokens

        return TokenQuoteResult(
            allowed=allowed,
            remaining_daily=sub.tokens_daily,
            remaining_monthly=sub.tokens_monthly,
            remaining_bonus=sub.tokens_bonus,
            bucket_used=bucket,
            reset_in_hours=reset_in_hours if not allowed else None,
            sub_id=sub_id,
        )


async def check_and_consume(sub_id: str, estimated_tokens: int) -> TokenQuoteResult:
    """답변 전 호출 — 견적 토큰만큼 사전 차감. 실제 정산은 finalize_consumption."""
    return check_and_consume_sync(sub_id, estimated_tokens)


def finalize_consumption_sync(sub_id: str, actual_tokens: int, estimated: int) -> None:
    """실제 사용량과 견적 차이를 조정 — 과다 차감 시 환불, 부족 차감 시 추가."""
    if not settings.token_quota_enabled:
        return

    diff = actual_tokens - estimated  # 양수 = 추가 차감 필요, 음수 = 환불

    if diff == 0:
        return

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub is None:
            return

        if diff < 0:
            # 환불 — bonus 에 우선 적립
            refund_amount = abs(diff)
            sub.tokens_bonus += refund_amount
            sub.tokens_lifetime_used = max(0, (sub.tokens_lifetime_used or 0) - refund_amount)
        else:
            # 추가 차감
            remaining = diff
            if sub.tokens_bonus >= remaining:
                sub.tokens_bonus -= remaining
            else:
                remaining -= sub.tokens_bonus
                sub.tokens_bonus = 0
                if sub.tokens_monthly >= remaining:
                    sub.tokens_monthly -= remaining
                else:
                    remaining -= sub.tokens_monthly
                    sub.tokens_monthly = 0
                    sub.tokens_daily = max(0, sub.tokens_daily - remaining)
            sub.tokens_lifetime_used = (sub.tokens_lifetime_used or 0) + diff


async def finalize_consumption(sub_id: str, actual_tokens: int, estimated: int) -> None:
    """비동기 래퍼."""
    finalize_consumption_sync(sub_id, actual_tokens, estimated)


def grant_signup_bonus_sync(sub_id: str, amount: int | None = None) -> bool:
    """가입 보너스 지급. 이미 받았으면 skip (멱등성). True = 지급, False = 이미 지급됨."""
    if not settings.token_quota_enabled:
        return False

    bonus = amount if amount is not None else settings.tokens_bonus_on_signup

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub is None:
            return False
        # 멱등성 보장: 이미 보너스가 있으면 (가입 보너스 받은 상태) skip
        # lifetime_used > 0 이거나 subscription_tier != guest 이면 이미 가입 처리됨
        if sub.subscription_tier != "guest":
            return False
        sub.subscription_tier = "member"
        sub.subscribed_at = _utcnow()
        sub.tokens_bonus += bonus
        sub.tokens_monthly = settings.tokens_monthly_member
        sub.tokens_monthly_reset_at = _utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return True


async def grant_signup_bonus(sub_id: str, amount: int | None = None) -> bool:
    return grant_signup_bonus_sync(sub_id, amount)


def get_quota_status(sub_id: str) -> dict:
    """현재 남은 쿼터 조회 (차감 없음). User UI 표시용."""
    if not settings.token_quota_enabled:
        return {"unlimited": True, "tokens_daily": 999999, "tokens_monthly": 999999, "tokens_bonus": 999999}

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub is None:
            return {
                "subscription_tier": "guest",
                "tokens_daily": settings.tokens_daily_guest,
                "tokens_monthly": 0,
                "tokens_bonus": 0,
                "tokens_lifetime_used": 0,
                "reset_in_hours": 24,
            }
        _reset_daily_if_needed(sub)
        _reset_monthly_if_needed(sub)
        now = _utcnow()
        next_reset = datetime(now.year, now.month, now.day, 0, 0, 0) + timedelta(days=1)
        return {
            "subscription_tier": sub.subscription_tier,
            "tokens_daily": sub.tokens_daily,
            "tokens_monthly": sub.tokens_monthly,
            "tokens_bonus": sub.tokens_bonus,
            "tokens_lifetime_used": sub.tokens_lifetime_used or 0,
            "reset_in_hours": int((next_reset - now).total_seconds() / 3600),
        }
