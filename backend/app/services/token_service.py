from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.exc import OperationalError

from ..config import settings
from ..db import get_session_immediate
from ..models.orm import Subscriber

_logger = logging.getLogger(__name__)


# ── Token Quota 헬퍼 ──────────────────────────────────────────────────────────
def _today_str() -> str:
    from datetime import date

    return date.today().isoformat()


def _hours_until_midnight() -> int:
    from datetime import datetime

    return max(1, 24 - datetime.now().hour)


def _maybe_reset_periods(sub: "Subscriber") -> None:
    """일/월간 토큰 카운터 주기 리셋 (기준일 변경 시)."""
    today = _today_str()
    if sub.tokens_daily_reset != today:
        sub.tokens_daily = 0
        sub.tokens_daily_reset = today
    month = today[:7]
    if sub.tokens_monthly_reset != month:
        sub.tokens_monthly = 0
        sub.tokens_monthly_reset = month


def _quote_exhausted(sub_id: str, rd: int, rm: int, bonus) -> "TokenQuoteResult":
    return TokenQuoteResult(
        allowed=False,
        remaining_daily=rd,
        remaining_monthly=rm,
        remaining_bonus=max(0, bonus or 0),
        bucket_used="daily",
        reset_in_hours=_hours_until_midnight(),
        sub_id=sub_id,
    )


def _with_retry(fn, *args, max_retries=3, backoff=0.1, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                _logger.warning(
                    "[token_service] DB locked, retry %d/%d", attempt + 1, max_retries
                )
                time.sleep(backoff * (attempt + 1))
            else:
                raise


@dataclass
class TokenQuoteResult:
    allowed: bool
    remaining_daily: int
    remaining_monthly: int
    remaining_bonus: int
    bucket_used: str
    reset_in_hours: Optional[int]
    sub_id: str


def _unlimited_quote(sub_id: str) -> TokenQuoteResult:
    return TokenQuoteResult(
        allowed=True,
        remaining_daily=0,
        remaining_monthly=0,
        remaining_bonus=0,
        bucket_used="none",
        reset_in_hours=None,
        sub_id=sub_id,
    )


def check_and_consume_sync(sub_id: str, estimated_tokens: int) -> TokenQuoteResult:
    """사전 점검(예약). token_quota_enabled=False → 무제한 스텁."""
    if not settings.token_quota_enabled:
        return _unlimited_quote(sub_id)
    with get_session_immediate() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            sub = Subscriber(subscriber_id=sub_id)
            s.add(sub)
        _maybe_reset_periods(sub)
        rd = max(0, settings.token_quota_default - sub.tokens_daily)
        rm = max(0, settings.token_quota_monthly - sub.tokens_monthly)
        if estimated_tokens > rd or estimated_tokens > rm:
            return _quote_exhausted(sub_id, rd, rm, sub.tokens_bonus)
        sub.tokens_daily += estimated_tokens
        sub.tokens_monthly += estimated_tokens
        sub.tokens_lifetime_used += estimated_tokens
        return TokenQuoteResult(
            allowed=True,
            remaining_daily=rd - estimated_tokens,
            remaining_monthly=rm - estimated_tokens,
            remaining_bonus=max(0, sub.tokens_bonus),
            bucket_used="daily",
            reset_in_hours=_hours_until_midnight(),
            sub_id=sub_id,
        )


async def check_and_consume(sub_id: str, estimated_tokens: int) -> TokenQuoteResult:
    return await asyncio.to_thread(check_and_consume_sync, sub_id, estimated_tokens)


def finalize_consumption_sync(
    sub_id: str, actual_tokens: int, estimated: int, extra_llm_calls: int = 0
) -> bool:
    """토큰 사용량 최종 정산 — 예약량(estimated)과 실제 사용량(actual)의 차이를 보정.

    save_interaction_and_finalize_tokens_sync() 가 상호작용 저장과 함께 이 로직을
    포함하므로 대부분의 경우 해당 함수를 사용하면 됩니다. 본 함수는 상호작용을 저장
    하지 않고 순수하게 토큰 잔액만 정산해야 할 때 사용합니다.
    """
    if not settings.token_quota_enabled:
        return False
    delta = (actual_tokens or estimated) - estimated
    if delta == 0:
        return False
    with get_session_immediate() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub:
            sub.tokens_daily = max(0, sub.tokens_daily + delta)
            sub.tokens_monthly = max(0, sub.tokens_monthly + delta)
            sub.tokens_lifetime_used = max(0, sub.tokens_lifetime_used + delta)
            return True
    return False


async def finalize_consumption(
    sub_id: str, actual_tokens: int, estimated: int, extra_llm_calls: int = 0
) -> None:
    await asyncio.to_thread(
        finalize_consumption_sync, sub_id, actual_tokens, estimated, extra_llm_calls
    )


def grant_signup_bonus_sync(sub_id: str, amount: int | None = None) -> bool:
    """신규 가입자에게 토큰 보너스를 지급한다.

    settings.signup_bonus_tokens 가 설정된 경우에만 동작.
    """
    if not settings.token_quota_enabled:
        return False
    bonus = amount if amount is not None else getattr(settings, 'signup_bonus_tokens', 0)
    if not bonus or bonus <= 0:
        return False
    try:
        with get_session_immediate() as s:
            sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
            if sub:
                # 보너스는 일일/월간 한도를 늘리는 것이 아니라
                # 사용량을 감소시켜 여유분을 생성
                sub.tokens_daily = max(0, sub.tokens_daily - bonus)
                sub.tokens_monthly = max(0, sub.tokens_monthly - bonus)
                # 노출용 보너스 잔액도 갱신 (get_quota_status 'bonus' 가 항상 0인 버그 수정)
                sub.tokens_bonus = max(0, (sub.tokens_bonus or 0) + bonus)
                s.commit()
                _logger.info("[token] signup bonus granted: sub=%s, amount=%d", sub_id, bonus)
                return True
    except Exception:
        _logger.warning("[token] signup bonus 지급 실패: sub=%s", sub_id, exc_info=True)
    return False


async def grant_signup_bonus(sub_id: str, amount: int | None = None) -> bool:
    return await asyncio.to_thread(grant_signup_bonus_sync, sub_id, amount)


def get_quota_status(sub_id: str) -> dict:
    if not settings.token_quota_enabled:
        return {"unlimited": True}
    try:
        with get_session_immediate() as s:
            sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
            if not sub:
                return {
                    "unlimited": False,
                    "daily_used": 0,
                    "daily_quota": settings.token_quota_default,
                    "monthly_used": 0,
                    "monthly_quota": settings.token_quota_monthly,
                }
            _maybe_reset_periods(sub)
            return {
                "unlimited": False,
                "daily_used": sub.tokens_daily,
                "daily_quota": settings.token_quota_default,
                "monthly_used": sub.tokens_monthly,
                "monthly_quota": settings.token_quota_monthly,
                "bonus": max(0, sub.tokens_bonus),
            }
    except Exception:
        return {"unlimited": False}


def check_consume_and_prepare_profile_sync(
    sub_id: str, estimated_tokens: int
) -> tuple[TokenQuoteResult, dict]:
    from .subscriber_service import _row_to_dict

    def _inner():
        with get_session_immediate() as s:
            row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
            if not row:
                row = Subscriber(subscriber_id=sub_id)
                s.add(row)
                s.flush()
            row.total_questions = (row.total_questions or 0) + 1
            profile_dict = _row_to_dict(row)

            # ── Token Quota (활성 시에만 강제) ──
            if settings.token_quota_enabled:
                _maybe_reset_periods(row)
                rd = max(0, settings.token_quota_default - row.tokens_daily)
                rm = max(0, settings.token_quota_monthly - row.tokens_monthly)
                if estimated_tokens > rd or estimated_tokens > rm:
                    return _quote_exhausted(sub_id, rd, rm, row.tokens_bonus), profile_dict
                row.tokens_daily += estimated_tokens
                row.tokens_monthly += estimated_tokens
                row.tokens_lifetime_used += estimated_tokens
                return (
                    TokenQuoteResult(
                        allowed=True,
                        remaining_daily=rd - estimated_tokens,
                        remaining_monthly=rm - estimated_tokens,
                        remaining_bonus=max(0, row.tokens_bonus),
                        bucket_used="daily",
                        reset_in_hours=_hours_until_midnight(),
                        sub_id=sub_id,
                    ),
                    profile_dict,
                )

            return _unlimited_quote(sub_id), profile_dict

    return _with_retry(_inner)


async def check_consume_and_prepare_profile(
    sub_id: str, estimated_tokens: int
) -> tuple[TokenQuoteResult, dict]:
    return await asyncio.to_thread(
        check_consume_and_prepare_profile_sync, sub_id, estimated_tokens
    )


def save_interaction_and_finalize_tokens_sync(
    sub_id: str,
    question: str,
    answer: str,
    cited_versions: list,
    trace_id: str | None,
    elapsed_ms: int,
    actual_tokens: int,
    estimated: int,
    extra_llm_calls: int = 0,
    crisis_bypass: bool = False,
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> str:
    """상호작용을 저장하고 토큰 잔액을 정산한다(CCP 원가 스냅샷 포함).

    CCP 관련 인자는 모두 키워드 전용·선택 인자이므로, 기존 호출부는
    수정 없이 그대로 동작한다(개방-폐쇄 원칙).

    매개변수 (CCP 확장분)
    ---------------------
    llm_provider: 실제 응답한 LLM 공급자. 미호출 턴이면 None.
    llm_model: 실제 응답한 모델명. 미호출 턴이면 None.
    prompt_tokens: 입력 토큰 수. 알 수 없으면 None.
    completion_tokens: 출력 토큰 수. 알 수 없으면 None.

    반환
    ----
    생성된 interaction_id.

    비고
    ----
    원가 산정에 실패해도(요율 미등록 등) 상호작용 저장은 정상 수행된다.
    """
    from ..models.orm import Interaction
    from .ccp.rate_service import calculate_cost

    def _inner():
        with get_session_immediate() as s:
            # 익명/신규 sub_id("self" 등)는 subscriber 행이 없을 수 있다.
            # interaction.subscriber_id 는 FK(nullable) 이므로, 참조 대상이 없으면
            # INSERT 시 "FOREIGN KEY constraint failed" 로 상호작용 저장이 유실된다.
            # get_or_create 패턴으로 참조 행을 먼저 보장한다(기존 행이면 no-op).
            if sub_id:
                _sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
                if _sub is None:
                    s.add(Subscriber(subscriber_id=sub_id))
                    s.flush()

            interaction_obj = Interaction(
                subscriber_id=sub_id,
                question=question,
                answer=answer,
                cited_versions=cited_versions,
                trace_id=trace_id,
                elapsed_ms=elapsed_ms,
                crisis_bypass=crisis_bypass,
                # V-4: cited 문서가 없으면 질문에 대한 검색 커버리지 부족으로 표시
                low_coverage=not bool(cited_versions),
                llm_provider=llm_provider,
                llm_model=llm_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

            # ── CCP: 호출 시점 요율로 원가를 확정해 함께 저장 ──
            # calculate_cost 는 내부에서 모든 예외를 흡수하고 None 을 반환하므로
            # 채팅 저장 경로가 원가 산정 때문에 실패하지 않는다.
            breakdown = calculate_cost(
                s,
                llm_provider,
                llm_model,
                prompt_tokens,
                completion_tokens,
            )
            if breakdown is not None:
                interaction_obj.cost_krw = breakdown.cost_krw
                interaction_obj.rate_card_id = breakdown.rate_card_id

            s.add(interaction_obj)
            s.flush()
            interaction_id = interaction_obj.interaction_id

            # ── Token Quota 실제 사용량 반영 (예약→실제 차이 보정) ──
            if settings.token_quota_enabled:
                sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
                if sub:
                    delta = (actual_tokens or estimated) - estimated
                    sub.tokens_daily = max(0, sub.tokens_daily + delta)
                    sub.tokens_monthly = max(0, sub.tokens_monthly + delta)
                    sub.tokens_lifetime_used = max(0, sub.tokens_lifetime_used + delta)

            return interaction_id

    return _with_retry(_inner)


async def save_interaction_and_finalize_tokens(
    sub_id: str,
    question: str,
    answer: str,
    cited_versions: list,
    trace_id: str | None,
    elapsed_ms: int,
    actual_tokens: int,
    estimated: int,
    extra_llm_calls: int = 0,
    crisis_bypass: bool = False,
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> str:
    """``save_interaction_and_finalize_tokens_sync`` 의 비동기 래퍼.

    CCP 인자를 워커 스레드로 그대로 전달한다(functools.partial 로 키워드 전용
    인자를 보존).
    """
    from functools import partial

    return await asyncio.to_thread(
        partial(
            save_interaction_and_finalize_tokens_sync,
            sub_id,
            question,
            answer,
            cited_versions,
            trace_id,
            elapsed_ms,
            actual_tokens,
            estimated,
            extra_llm_calls,
            crisis_bypass,
            llm_provider=llm_provider,
            llm_model=llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    )
