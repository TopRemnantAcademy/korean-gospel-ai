"""요율 해석 및 LLM 호출 원가 계산 서비스.

책임(단일 책임 원칙)
--------------------
이 모듈은 **오직** "토큰 사용량 → 원화 원가" 변환만 담당한다.
DB 커밋, 인터랙션 저장, HTTP 응답 등은 호출자(token_service / API 계층)의
책임이며 여기서는 수행하지 않는다.

핵심 규칙
---------
1. **시점 기준 조회**: 원가는 "호출이 발생한 시각"의 요율로 계산한다.
   요율 구간은 ``[effective_from, effective_to)`` 반개구간이다.
2. **소급 변경 금지**: 요율표에 새 행이 추가되어도 이미 확정된
   ``Interaction.cost_krw`` 는 변하지 않는다(호출자가 재계산하지 않는 한).
3. **정확한 십진 연산**: 통화 계산에 float 를 쓰지 않는다. 모든 연산은
   ``decimal.Decimal`` 로 하고, 최종 결과만 6자리로 반올림한다.
4. **실패는 조용히**: 요율이 없으면 예외 대신 ``None`` 을 반환한다.
   원가를 모른다는 이유로 사용자 채팅이 실패해서는 안 된다(가용성 우선).
   대신 경고 로그를 남겨 운영자가 요율 누락을 인지하도록 한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models.ccp import CCPRateCard

logger = logging.getLogger(__name__)

# 단가의 기준 단위: 1,000 토큰당 가격
TOKENS_PER_PRICE_UNIT = Decimal(1000)

# 원가 저장 정밀도 — DB 컬럼 Numeric(18, 6) 과 일치시킨다.
COST_QUANTIZE = Decimal("0.000001")


class RateNotFoundError(LookupError):
    """지정한 시점에 유효한 요율 카드가 없을 때 발생.

    ``calculate_cost`` 는 이 예외를 잡아 ``None`` 을 반환하지만,
    배치 재계산 스크립트처럼 "누락을 반드시 알아야 하는" 호출자는
    ``resolve_rate_card`` 를 직접 호출해 예외를 받을 수 있다.
    """


@dataclass(frozen=True)
class CostBreakdown:
    """원가 계산 결과(불변 값 객체).

    속성
    ----
    cost_krw:
        총 원가(KRW). 입력 원가 + 출력 원가.
    input_cost_krw:
        prompt 토큰에 대한 원가(KRW).
    output_cost_krw:
        completion 토큰에 대한 원가(KRW).
    rate_card_id:
        계산에 사용된 요율 카드 PK — 감사 추적용.
    """

    cost_krw: Decimal
    input_cost_krw: Decimal
    output_cost_krw: Decimal
    rate_card_id: str


def _normalize_naive_utc(moment: datetime) -> datetime:
    """tz-aware datetime 을 UTC 기준 naive 로 변환한다.

    프로젝트의 ``DateTime`` 컬럼은 timezone 정보를 저장하지 않는 naive 이며
    ``_now()`` 가 UTC 로 값을 넣는다. 비교 대상이 tz-aware 일 경우
    "can't compare offset-naive and offset-aware datetimes" 오류가 나므로
    UTC 로 환산 후 tzinfo 를 제거해 저장 규약과 일치시킨다.

    매개변수
    --------
    moment: 변환할 시각.

    반환
    ----
    UTC 기준 naive datetime.
    """
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def resolve_rate_card(
    session: Session,
    provider: str,
    model: str,
    at: Optional[datetime] = None,
) -> CCPRateCard:
    """주어진 시점에 유효한 요율 카드를 조회한다.

    구간 판정은 ``effective_from <= at < effective_to`` 이며,
    ``effective_to`` 가 NULL 이면 종료되지 않은(현재 유효한) 요율로 본다.
    데이터 오류로 구간이 겹칠 경우 ``effective_from`` 이 가장 최근인 행을
    선택하여 결정론적으로 동작하게 한다.

    매개변수
    --------
    session: 활성 SQLAlchemy 세션.
    provider: LLM 공급자 식별자(예: ``nvidia``). 대소문자·공백은 정규화된다.
    model: 모델 식별자. 대소문자·공백은 정규화된다.
    at: 기준 시각. 생략 시 현재(UTC).

    반환
    ----
    조건을 만족하는 :class:`CCPRateCard`.

    예외
    ----
    ValueError: provider 또는 model 이 비어 있는 경우.
    RateNotFoundError: 해당 시점에 유효한 요율이 없는 경우.
    """
    # 외부 입력 검증 — 빈 문자열/None 은 조용히 넘기지 않고 즉시 거부한다.
    if not provider or not provider.strip():
        raise ValueError("provider 는 비어 있을 수 없습니다")
    if not model or not model.strip():
        raise ValueError("model 은 비어 있을 수 없습니다")

    normalized_provider = provider.strip().lower()
    normalized_model = model.strip()
    moment = _normalize_naive_utc(at or datetime.now(timezone.utc))

    # 파라미터 바인딩(SQLAlchemy Core) — 문자열 연결이 없으므로 SQL 인젝션 불가.
    stmt = (
        select(CCPRateCard)
        .where(
            CCPRateCard.provider == normalized_provider,
            CCPRateCard.model == normalized_model,
            CCPRateCard.effective_from <= moment,
            or_(
                CCPRateCard.effective_to.is_(None),
                CCPRateCard.effective_to > moment,
            ),
        )
        .order_by(CCPRateCard.effective_from.desc())
        .limit(1)
    )

    card = session.execute(stmt).scalars().first()
    if card is None:
        raise RateNotFoundError(
            f"유효한 요율 카드 없음: provider={normalized_provider} "
            f"model={normalized_model} at={moment.isoformat()}"
        )
    return card


def _validate_token_count(value: int, field_name: str) -> int:
    """토큰 수 입력을 검증한다.

    bool 은 int 의 서브클래스라 계산에 섞이면 조용한 버그가 되므로 거부한다.

    매개변수
    --------
    value: 검증할 토큰 수.
    field_name: 오류 메시지에 표시할 필드명.

    반환
    ----
    검증을 통과한 토큰 수.

    예외
    ----
    TypeError: 정수가 아닌 경우.
    ValueError: 음수인 경우.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} 는 정수여야 합니다 (받은 타입: {type(value).__name__})")
    if value < 0:
        raise ValueError(f"{field_name} 는 0 이상이어야 합니다 (받은 값: {value})")
    return value


def compute_cost_from_card(
    card: CCPRateCard,
    prompt_tokens: int,
    completion_tokens: int,
) -> CostBreakdown:
    """요율 카드와 토큰 수로 원가를 계산한다(순수 함수, DB 접근 없음).

    계산식::

        원가 = (prompt_tokens / 1000) * input_price_per_1k
             + (completion_tokens / 1000) * output_price_per_1k

    매개변수
    --------
    card: 적용할 요율 카드.
    prompt_tokens: 입력 토큰 수(0 이상).
    completion_tokens: 출력 토큰 수(0 이상).

    반환
    ----
    :class:`CostBreakdown` — 총액/입력/출력 원가와 요율 카드 ID.

    예외
    ----
    TypeError: 토큰 수가 정수가 아닌 경우.
    ValueError: 토큰 수가 음수인 경우.
    """
    _validate_token_count(prompt_tokens, "prompt_tokens")
    _validate_token_count(completion_tokens, "completion_tokens")

    # DB 에서 온 Numeric 은 드라이버에 따라 float 로 올 수 있으므로
    # 반드시 str 을 경유해 Decimal 로 변환한다(이진 부동소수 오차 차단).
    input_price = Decimal(str(card.input_price_per_1k))
    output_price = Decimal(str(card.output_price_per_1k))

    input_cost = (Decimal(prompt_tokens) / TOKENS_PER_PRICE_UNIT) * input_price
    output_cost = (Decimal(completion_tokens) / TOKENS_PER_PRICE_UNIT) * output_price

    return CostBreakdown(
        cost_krw=(input_cost + output_cost).quantize(
            COST_QUANTIZE, rounding=ROUND_HALF_UP
        ),
        input_cost_krw=input_cost.quantize(COST_QUANTIZE, rounding=ROUND_HALF_UP),
        output_cost_krw=output_cost.quantize(COST_QUANTIZE, rounding=ROUND_HALF_UP),
        rate_card_id=card.rate_card_id,
    )


def calculate_cost(
    session: Session,
    provider: Optional[str],
    model: Optional[str],
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    at: Optional[datetime] = None,
) -> Optional[CostBreakdown]:
    """LLM 호출 1건의 원가를 계산한다(가용성 우선, 실패 시 None).

    채팅 응답 경로에서 호출되므로 **어떤 경우에도 예외를 전파하지 않는다**.
    원가 산정 실패가 사용자 응답 실패로 이어져서는 안 되기 때문이다.
    산정 불가 사유는 경고 로그로 남긴다.

    다음 경우 ``None`` 을 반환한다.

    - provider/model 이 없는 턴(fast-path, crisis_bypass 등 LLM 미호출)
    - 토큰 사용량 정보가 없는 경우
    - 해당 시점 요율 카드가 등록되지 않은 경우
    - 그 외 예기치 못한 오류

    매개변수
    --------
    session: 활성 SQLAlchemy 세션.
    provider: LLM 공급자 식별자. None 허용.
    model: 모델 식별자. None 허용.
    prompt_tokens: 입력 토큰 수. None 허용.
    completion_tokens: 출력 토큰 수. None 허용.
    at: 원가 기준 시각. 생략 시 현재(UTC).

    반환
    ----
    :class:`CostBreakdown` 또는 산정 불가 시 ``None``.
    """
    if not provider or not model:
        # LLM 을 호출하지 않은 정상 턴이므로 경고 없이 조용히 종료.
        return None

    if prompt_tokens is None or completion_tokens is None:
        logger.warning(
            "CCP 원가 산정 생략: 토큰 사용량 누락 (provider=%s model=%s)",
            provider,
            model,
        )
        return None

    try:
        card = resolve_rate_card(session, provider, model, at=at)
        return compute_cost_from_card(card, prompt_tokens, completion_tokens)
    except RateNotFoundError as exc:
        # 신규 모델 도입 시 흔히 발생 — 운영자가 요율을 등록하면 해소된다.
        logger.warning("CCP 원가 산정 실패(요율 미등록): %s", exc)
        return None
    except (TypeError, ValueError) as exc:
        logger.warning("CCP 원가 산정 실패(입력 오류): %s", exc)
        return None
    except Exception:  # noqa: BLE001 - 채팅 경로 보호를 위한 최종 방어선
        logger.exception("CCP 원가 산정 중 예기치 못한 오류")
        return None
