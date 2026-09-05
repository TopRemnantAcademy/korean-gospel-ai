"""CCP 원가 단가(rate card) 관리 API.

GET  /admin/ccp/rates        현재 유효한 단가 목록 조회
POST /admin/ccp/rates        신규 단가 추가 (SCD Type 2 — 기존 구간 종료 + 신규 구간 개시)

설계 근거
-------
- 원가 단가는 세무·보조금 증빙의 근거가 되므로 **불변(immutable)** 이어야 한다.
  따라서 UPDATE 가 아닌 "기존 유효 구간의 effective_to 를 닫고, effective_from 가
  다른 새 행을 INSERT" 하는 방식(SCD Type 2)으로 이력을 보존한다.
- 입력값은 모두 Decimal/Numeric(18,6) 으로 처리해 부동소수 오차를 배제한다.
- source_note 는 "공급자 가격표 URL·환율 기준일" 등 출처 소명 근거이므로 필수로 받는다.
- 관리자 전용: check_admin(Bearer 또는 X-API-Key) 적용.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..db import get_session
from ..models.ccp import CCPRateCard
from .auth import check_admin as _check_admin

router = APIRouter(prefix="/admin/ccp", tags=["ccp"])

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 요청/응답 스키마
# --------------------------------------------------------------------------- #
class CreateRateReq(BaseModel):
    """신규 단가 추가 요청.

    provider/model 는 ``LLMResponse.provider/model`` 과 동일하게 입력한다.
    effective_from 는 비우면 서버 현재 시각(UTC)으로 개시된다.
    source_note 는 반드시 채운다(증빙 근거).
    """

    provider: str = Field(..., min_length=1, max_length=40)
    model: str = Field(..., min_length=1, max_length=120)
    input_price_per_1k: Decimal = Field(..., ge=0)
    output_price_per_1k: Decimal = Field(..., ge=0)
    currency: str = Field("KRW", max_length=8)
    effective_from: Optional[datetime] = None
    source_note: str = Field(..., min_length=1, max_length=400)


class RateOut(BaseModel):
    rate_card_id: str
    provider: str
    model: str
    input_price_per_1k: str
    output_price_per_1k: str
    currency: str
    effective_from: datetime
    effective_to: Optional[datetime]
    source_note: Optional[str]


# --------------------------------------------------------------------------- #
# 헬퍼
# --------------------------------------------------------------------------- #
def _to_out(row: CCPRateCard) -> RateOut:
    return RateOut(
        rate_card_id=row.rate_card_id,
        provider=row.provider,
        model=row.model,
        input_price_per_1k=str(row.input_price_per_1k),
        output_price_per_1k=str(row.output_price_per_1k),
        currency=row.currency,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        source_note=row.source_note,
    )


def _close_overlapping_active(
    s, provider: str, model: str, effective_from: datetime
) -> None:
    """동일 (provider, model) 의 현재 유효 구간(effective_to IS NULL) 중
    새 구간 시작 시각보다 앞서 시작된 행의 effective_to 를 닫는다.

    SCD Type 2 의 표준 패턴: 신규 단가는 과거 구간을 소급 변경하지 않고,
    effective_from 시점부터 유효한 새 행으로插入되며, 그 시점 이전까지 유효했던
    행은 effective_to 로 종료 처리된다.
    """
    existing = (
        s.query(CCPRateCard)
        .filter(
            CCPRateCard.provider == provider,
            CCPRateCard.model == model,
            CCPRateCard.effective_to.is_(None),
        )
        .all()
    )
    for row in existing:
        # 비교 기준(effective_from)을 naive 로 정규화해 DB 값(naive)과 동일 차원 비교
        cmp_from = effective_from
        if cmp_from.tzinfo is not None:
            cmp_from = cmp_from.replace(tzinfo=None)
        row_from = row.effective_from
        if row_from.tzinfo is not None:
            row_from = row_from.replace(tzinfo=None)
        if row_from <= cmp_from:
            row.effective_to = cmp_from


# --------------------------------------------------------------------------- #
# 엔드포인트
# --------------------------------------------------------------------------- #
@router.get("/rates", response_model=list[RateOut])
def list_rates(authorization: Optional[str] = Header(default=None)):
    """현재 유효한(종료 시각이 NULL 인) 단가 목록을 반환한다.

    과거 이력은 포함하지 않는다 — 전체 이력을 보려면 후속 단계(M4 보고서)에서
    /admin/ccp/rates?history=true 형태로 확장 예정.
    """
    _check_admin(authorization)
    with get_session() as s:
        rows = (
            s.query(CCPRateCard)
            .filter(CCPRateCard.effective_to.is_(None))
            .order_by(CCPRateCard.provider, CCPRateCard.model)
            .all()
        )
        return [_to_out(r) for r in rows]


@router.post("/rates", response_model=RateOut, status_code=201)
def create_rate(
    req: CreateRateReq,
    authorization: Optional[str] = Header(default=None),
):
    """신규 단가를 추가한다 (SCD Type 2).

    동일 (provider, model) 의 현재 유효 구간이 있으면 effective_to 로 종료 처리 후
    새 구간을 개시한다. effective_from 위반(미래 시점이 기존 시작보다 앞서는 등)
    시나리오는 DB UniqueConstraint(uq_ccp_rate_card_scope_from) 가 방어한다.
    """
    _check_admin(authorization)
    # Decimal 타입 보강: pydantic 가 문자열/실수를 Decimal 로 직렬화했을 수 있으므로
    # 다시 Decimal 로 정규화해 Numeric 컬럼에 안전하게 바인딩한다.
    try:
        in_price = Decimal(str(req.input_price_per_1k))
        out_price = Decimal(str(req.output_price_per_1k))
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"단가 형식 오류: {e}")

    effective_from = req.effective_from or datetime.now(timezone.utc)
    if effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=timezone.utc)
    # SQLite 저장 일관성을 위해 naive UTC 로 정규화 (조회 시 tzinfo=None 로 반환됨)
    effective_from_naive = effective_from.replace(tzinfo=None)

    with get_session() as s:
        _close_overlapping_active(s, req.provider, req.model, effective_from_naive)
        row = CCPRateCard(
            provider=req.provider,
            model=req.model,
            input_price_per_1k=in_price,
            output_price_per_1k=out_price,
            currency=req.currency or "KRW",
            effective_from=effective_from_naive,
            effective_to=None,
            source_note=req.source_note,
        )
        s.add(row)
        try:
            s.commit()
            s.refresh(row)
            result = _to_out(row)
        except Exception as e:  # UniqueConstraint 등 무결성 위반
            s.rollback()
            _logger.warning("[ccp] 단가 추가 실패: %s", e)
            raise HTTPException(
                status_code=409,
                detail="동일 (provider, model, effective_from) 조합의 단가가 이미 존재합니다.",
            )
    return result
