"""CCP 원가 산정 서비스 단위 테스트.

정상 흐름 / 경계 조건 / 예외 상황을 모두 다룬다.
DB 는 인메모리 SQLite 를 사용하므로 운영 DB(.gospel.db)에 영향이 없고
외부 의존(LLM/네트워크)도 없다.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.ccp import CCPRateCard  # noqa: E402
from backend.app.services.ccp.rate_service import (  # noqa: E402
    CostBreakdown,
    RateNotFoundError,
    calculate_cost,
    compute_cost_from_card,
    resolve_rate_card,
)

# 테스트 기준 시각(고정) — 시간에 의존하는 플래키 테스트를 방지한다.
T0 = datetime(2026, 8, 1, 0, 0, 0)


@pytest.fixture()
def session():
    """CCPRateCard 테이블만 가진 인메모리 세션을 제공한다.

    orm.py 전체가 아닌 CCPRateCard 테이블만 생성해 테스트를 가볍게 유지한다.
    """
    engine = create_engine("sqlite://")
    CCPRateCard.__table__.create(engine)
    maker = sessionmaker(bind=engine)
    db = maker()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _add_card(
    session,
    *,
    provider: str = "nvidia",
    model: str = "test-model",
    input_price: str = "1.0",
    output_price: str = "2.0",
    effective_from: datetime = T0,
    effective_to: datetime | None = None,
) -> CCPRateCard:
    """테스트용 요율 카드를 생성해 커밋한다."""
    card = CCPRateCard(
        provider=provider,
        model=model,
        input_price_per_1k=Decimal(input_price),
        output_price_per_1k=Decimal(output_price),
        effective_from=effective_from,
        effective_to=effective_to,
    )
    session.add(card)
    session.commit()
    return card


# ---------------------------------------------------------------- 정상 흐름
def test_compute_cost_basic(session):
    """1,000 토큰 단가가 그대로 반영되는 기본 계산."""
    card = _add_card(session, input_price="1.0", output_price="2.0")
    result = compute_cost_from_card(card, prompt_tokens=1000, completion_tokens=1000)

    assert result.input_cost_krw == Decimal("1.000000")
    assert result.output_cost_krw == Decimal("2.000000")
    assert result.cost_krw == Decimal("3.000000")
    assert result.rate_card_id == card.rate_card_id


def test_compute_cost_is_decimal_exact(session):
    """부동소수 오차 없이 십진 정확도가 보장되어야 한다.

    0.1 을 float 로 3번 더하면 0.30000000000000004 가 되지만
    Decimal 은 정확히 0.3 이어야 한다.
    """
    card = _add_card(session, input_price="0.1", output_price="0")
    result = compute_cost_from_card(card, prompt_tokens=3000, completion_tokens=0)
    assert result.cost_krw == Decimal("0.300000")


def test_calculate_cost_returns_breakdown(session):
    """calculate_cost 정상 경로는 CostBreakdown 을 반환한다."""
    _add_card(session, input_price="3.0", output_price="6.0")
    result = calculate_cost(session, "nvidia", "test-model", 500, 250, at=T0)

    assert isinstance(result, CostBreakdown)
    # 500/1000*3 = 1.5, 250/1000*6 = 1.5
    assert result.cost_krw == Decimal("3.000000")


def test_provider_is_case_insensitive(session):
    """provider 는 대소문자·공백에 관계없이 매칭되어야 한다."""
    _add_card(session, provider="nvidia")
    card = resolve_rate_card(session, "  NVIDIA  ", "test-model", at=T0)
    assert card.provider == "nvidia"


# ------------------------------------------------------------- 시점 스냅샷
def test_resolve_picks_rate_valid_at_that_time(session):
    """과거 호출에는 과거 요율이 적용되어야 한다(소급 변경 금지)."""
    t1 = T0 + timedelta(days=10)
    # 구 요율: T0 ~ t1
    _add_card(session, input_price="1.0", output_price="1.0",
              effective_from=T0, effective_to=t1)
    # 신 요율: t1 ~ 무기한
    _add_card(session, input_price="5.0", output_price="5.0",
              effective_from=t1, effective_to=None)

    old = resolve_rate_card(session, "nvidia", "test-model",
                            at=T0 + timedelta(days=1))
    new = resolve_rate_card(session, "nvidia", "test-model",
                            at=t1 + timedelta(days=1))

    assert old.input_price_per_1k == Decimal("1.000000")
    assert new.input_price_per_1k == Decimal("5.000000")


def test_effective_from_is_inclusive(session):
    """구간 시작 시각은 포함된다(경계 조건)."""
    _add_card(session, effective_from=T0)
    card = resolve_rate_card(session, "nvidia", "test-model", at=T0)
    assert card is not None


def test_effective_to_is_exclusive(session):
    """구간 종료 시각은 제외된다(경계 조건).

    effective_to == at 인 순간은 해당 요율이 이미 만료된 것으로 본다.
    """
    t1 = T0 + timedelta(days=10)
    _add_card(session, effective_from=T0, effective_to=t1)
    with pytest.raises(RateNotFoundError):
        resolve_rate_card(session, "nvidia", "test-model", at=t1)


def test_before_effective_from_raises(session):
    """요율 시작 이전 시점은 조회되지 않는다."""
    _add_card(session, effective_from=T0)
    with pytest.raises(RateNotFoundError):
        resolve_rate_card(
            session, "nvidia", "test-model", at=T0 - timedelta(seconds=1)
        )


def test_timezone_aware_input_is_normalized(session):
    """tz-aware 시각을 넘겨도 naive 저장값과 정상 비교되어야 한다."""
    _add_card(session, effective_from=T0)
    aware = (T0 + timedelta(hours=1)).replace(tzinfo=timezone.utc)
    card = resolve_rate_card(session, "nvidia", "test-model", at=aware)
    assert card is not None


# ------------------------------------------------------------- 경계 조건
def test_zero_tokens_yields_zero_cost(session):
    """토큰 0 이면 원가도 0 이다(None 이 아니라 0)."""
    card = _add_card(session)
    result = compute_cost_from_card(card, prompt_tokens=0, completion_tokens=0)
    assert result.cost_krw == Decimal("0.000000")


def test_free_tier_zero_price(session):
    """단가 0(무료 티어)도 유효한 값이며 0원으로 산정된다."""
    card = _add_card(session, input_price="0", output_price="0")
    result = compute_cost_from_card(card, prompt_tokens=10**6, completion_tokens=10**6)
    assert result.cost_krw == Decimal("0.000000")


def test_sub_won_precision_preserved(session):
    """1원 미만의 미세 단가도 반올림으로 소실되지 않아야 한다."""
    card = _add_card(session, input_price="0.001", output_price="0")
    # 1 토큰 → 0.001/1000 = 0.000001 (저장 정밀도 하한)
    result = compute_cost_from_card(card, prompt_tokens=1, completion_tokens=0)
    assert result.cost_krw == Decimal("0.000001")


def test_overlapping_ranges_prefers_latest_effective_from(session):
    """구간이 겹칠 경우 가장 최근 시작 요율을 결정론적으로 선택한다."""
    _add_card(session, input_price="1.0", effective_from=T0)
    _add_card(session, input_price="9.0", effective_from=T0 + timedelta(days=1))
    card = resolve_rate_card(
        session, "nvidia", "test-model", at=T0 + timedelta(days=2)
    )
    assert card.input_price_per_1k == Decimal("9.000000")


# ------------------------------------------------------------- 예외 상황
@pytest.mark.parametrize("bad_provider", ["", "   ", None])
def test_blank_provider_raises_value_error(session, bad_provider):
    """provider 가 비어 있으면 ValueError."""
    with pytest.raises(ValueError):
        resolve_rate_card(session, bad_provider, "test-model", at=T0)


@pytest.mark.parametrize("bad_model", ["", "   ", None])
def test_blank_model_raises_value_error(session, bad_model):
    """model 이 비어 있으면 ValueError."""
    with pytest.raises(ValueError):
        resolve_rate_card(session, "nvidia", bad_model, at=T0)


def test_negative_tokens_raise_value_error(session):
    """음수 토큰은 거부한다."""
    card = _add_card(session)
    with pytest.raises(ValueError):
        compute_cost_from_card(card, prompt_tokens=-1, completion_tokens=0)


def test_non_integer_tokens_raise_type_error(session):
    """정수가 아닌 토큰 수는 거부한다."""
    card = _add_card(session)
    with pytest.raises(TypeError):
        compute_cost_from_card(card, prompt_tokens="100", completion_tokens=0)


def test_bool_tokens_rejected(session):
    """bool 은 int 서브클래스지만 조용한 버그를 막기 위해 거부한다."""
    card = _add_card(session)
    with pytest.raises(TypeError):
        compute_cost_from_card(card, prompt_tokens=True, completion_tokens=0)


def test_unknown_provider_raises_rate_not_found(session):
    """등록되지 않은 provider 는 RateNotFoundError."""
    _add_card(session, provider="nvidia")
    with pytest.raises(RateNotFoundError):
        resolve_rate_card(session, "openai", "test-model", at=T0)


# ------------------------- calculate_cost 의 가용성 우선(None 반환) 정책
def test_calculate_cost_none_when_no_provider(session):
    """LLM 미호출 턴(provider 없음)은 조용히 None."""
    assert calculate_cost(session, None, None, 10, 10, at=T0) is None


def test_calculate_cost_none_when_tokens_missing(session):
    """토큰 정보가 없으면 None."""
    _add_card(session)
    assert calculate_cost(session, "nvidia", "test-model", None, 10, at=T0) is None


def test_calculate_cost_none_when_rate_missing(session):
    """요율 미등록 시 예외를 던지지 않고 None 을 반환해야 한다.

    원가 산정 실패가 사용자 채팅 실패로 이어지면 안 된다(가용성 우선).
    """
    assert calculate_cost(session, "unknown", "unknown-model", 10, 10, at=T0) is None


def test_calculate_cost_none_on_invalid_tokens(session):
    """잘못된 토큰 입력도 예외 대신 None."""
    _add_card(session)
    assert calculate_cost(session, "nvidia", "test-model", -5, 10, at=T0) is None


def test_calculate_cost_never_raises_on_broken_session():
    """세션이 손상되어도 예외를 전파하지 않는다(최종 방어선)."""

    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("DB 연결 끊김")

    assert calculate_cost(BrokenSession(), "nvidia", "m", 10, 10, at=T0) is None


# ------------------------------------------------------------- 불변성 계약
def test_cost_breakdown_is_immutable(session):
    """CostBreakdown 은 frozen dataclass 여야 한다."""
    card = _add_card(session)
    result = compute_cost_from_card(card, 100, 100)
    with pytest.raises(Exception):
        result.cost_krw = Decimal("999")
