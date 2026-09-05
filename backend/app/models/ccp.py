"""CCP (Cost & Compliance Platform) — 비용 귀속 기반 테이블.

P1 범위: LLM 호출 1건당 실제 원가(KRW)를 불변 스냅샷으로 확정하기 위한
요율 카드(rate card) 테이블만 정의한다. 프로젝트/증빙/인건비 테이블은
후속 단계(M1·M4·M5)에서 동일 ``ccp_`` 네임스페이스로 추가한다.

설계 원칙
---------
1. **요율 불변(immutable rate)**: 요율이 바뀌면 기존 행을 UPDATE 하지 않고
   ``effective_from`` 이 다른 새 행을 INSERT 한다. 과거 계산 결과가 소급
   변경되면 세무·보조금 증빙의 신뢰성이 무너지기 때문이다.
2. **시점 스냅샷 조회**: 원가는 호출 시각(``Interaction.created_at``)이
   속한 구간의 요율로 계산한다. 요율 구간은 ``[effective_from, effective_to)``
   반개구간이며 ``effective_to`` 가 NULL 이면 현재 유효한 행이다.
3. **단가 단위**: 1,000 토큰당 원화(KRW). 부동소수 오차를 배제하기 위해
   ``Numeric(18, 6)`` 으로 저장하고 계산은 ``Decimal`` 로 수행한다.

주의: 본 모듈은 ``backend.app.models.orm`` 과 동일한 ``Base`` 를 공유하므로
Alembic autogenerate 대상에 포함되려면 ``orm.py`` 에서 import 되어야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    """기본키용 UUID4 문자열을 생성한다."""
    return str(uuid.uuid4())


def _now() -> datetime:
    """UTC 기준 현재 시각을 반환한다(orm.py 와 동일 규약)."""
    return datetime.now(timezone.utc)


class CCPRateCard(Base):
    """LLM provider·model 별 토큰 단가의 버전 관리 테이블.

    한 행은 "특정 provider/model 이 특정 기간 동안 가졌던 단가"를 의미하는
    불변 레코드다. 요율 변경 시 기존 행의 ``effective_to`` 를 닫고 새 행을
    INSERT 하는 방식(SCD Type 2)으로 이력을 보존한다.

    컬럼
    ----
    rate_card_id:
        기본키(UUID4 문자열).
    provider:
        LLM 공급자 식별자. ``BaseLLM.provider_name`` 과 동일한 값
        (예: ``nvidia``, ``tencent``, ``gemini``).
    model:
        모델 식별자. ``LLMResponse.model`` 과 동일한 값.
    input_price_per_1k:
        입력(prompt) 1,000 토큰당 단가(KRW). 0 이상.
    output_price_per_1k:
        출력(completion) 1,000 토큰당 단가(KRW). 0 이상.
    currency:
        단가 통화. 본 시스템은 원화 정산이 기준이므로 기본값 ``KRW``.
    effective_from:
        요율 적용 시작 시각(포함, UTC).
    effective_to:
        요율 적용 종료 시각(미포함, UTC). NULL 이면 현재 유효한 요율.
    source_note:
        단가 출처(공급자 가격표 URL·환율 기준일 등). 세무 증빙 시
        "왜 이 단가인가"를 소명하는 근거가 되므로 반드시 기록한다.
    created_at:
        행 생성 시각(감사 추적용).

    제약
    ----
    - ``uq_ccp_rate_card_scope_from``: 동일 (provider, model, effective_from)
      조합은 1건만 허용하여 같은 시점에 두 요율이 공존하는 것을 방지한다.
    """

    __tablename__ = "ccp_rate_card"

    rate_card_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)

    input_price_per_1k: Mapped[Numeric] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    output_price_per_1k: Mapped[Numeric] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="KRW"
    )

    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    source_note: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            "effective_from",
            name="uq_ccp_rate_card_scope_from",
        ),
        # 시점 조회(provider+model+기간) 가 가장 빈번한 접근 패턴이므로 복합 인덱스.
        Index(
            "ix_ccp_rate_card_lookup",
            "provider",
            "model",
            "effective_from",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의용
        return (
            f"<CCPRateCard {self.provider}/{self.model} "
            f"in={self.input_price_per_1k} out={self.output_price_per_1k} "
            f"from={self.effective_from} to={self.effective_to}>"
        )
