"""CCP 요율 카드 등록/변경 CLI.

요율은 사업적 판단이 개입되는 데이터이므로 마이그레이션이 아닌 별도
스크립트로 관리한다(스키마 변경과 데이터 입력의 분리).

핵심 동작 — **UPDATE 하지 않는다**
-----------------------------------
동일 provider/model 의 요율을 새로 등록하면:

1. 기존에 열려 있던(effective_to IS NULL) 행의 ``effective_to`` 를
   새 요율의 ``effective_from`` 으로 닫고,
2. 새 요율 행을 INSERT 한다.

과거 단가를 덮어쓰지 않으므로 이미 확정된 원가의 소명 근거가 보존된다.

사용 예::

    # 현재 시각부터 적용
    python scripts/seed_ccp_rates.py --provider nvidia \\
        --model meta/llama-3.1-8b-instruct \\
        --input-price 0.0 --output-price 0.0 \\
        --note "NVIDIA NIM 무료 티어 (2026-08 기준)"

    # 적용 시각 지정 + 변경 미리보기
    python scripts/seed_ccp_rates.py --provider gemini --model gemini-2.0-flash \\
        --input-price 0.14 --output-price 0.55 \\
        --effective-from 2026-08-01T00:00:00 --note "환율 1,380 KRW/USD" --dry-run

    # 등록된 요율 조회
    python scripts/seed_ccp_rates.py --list
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import select  # noqa: E402

from backend.app.db import get_session_immediate  # noqa: E402
from backend.app.models.ccp import CCPRateCard  # noqa: E402


def _parse_datetime(raw: str) -> datetime:
    """ISO 8601 문자열을 UTC naive datetime 으로 변환한다.

    매개변수
    --------
    raw: ``2026-08-01T00:00:00`` 형식의 문자열.

    반환
    ----
    UTC 기준 naive datetime(DB 저장 규약과 일치).

    예외
    ----
    argparse.ArgumentTypeError: 형식이 올바르지 않은 경우.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"ISO 8601 형식이 아닙니다: {raw!r} (예: 2026-08-01T00:00:00)"
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_price(raw: str) -> Decimal:
    """단가 문자열을 Decimal 로 변환하고 음수를 거부한다.

    매개변수
    --------
    raw: 1,000 토큰당 원화 단가 문자열.

    반환
    ----
    검증된 Decimal 단가.

    예외
    ----
    argparse.ArgumentTypeError: 숫자가 아니거나 음수인 경우.
    """
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"숫자가 아닙니다: {raw!r}") from exc
    if value < 0:
        raise argparse.ArgumentTypeError(f"단가는 0 이상이어야 합니다: {raw!r}")
    return value


def list_rates() -> int:
    """등록된 모든 요율 카드를 출력한다.

    반환
    ----
    프로세스 종료 코드(항상 0).
    """
    with get_session_immediate() as session:
        rows = (
            session.execute(
                select(CCPRateCard).order_by(
                    CCPRateCard.provider,
                    CCPRateCard.model,
                    CCPRateCard.effective_from.desc(),
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            print("[ccp] 등록된 요율 카드가 없습니다.")
            return 0
        print(f"[ccp] 요율 카드 {len(rows)}건")
        for row in rows:
            period_end = (
                row.effective_to.isoformat() if row.effective_to else "현재 유효"
            )
            print(
                f"  - {row.provider}/{row.model} "
                f"in={row.input_price_per_1k} out={row.output_price_per_1k} "
                f"{row.currency} | {row.effective_from.isoformat()} ~ {period_end}"
            )
    return 0


def upsert_rate(
    provider: str,
    model: str,
    input_price: Decimal,
    output_price: Decimal,
    effective_from: datetime,
    note: str | None,
    dry_run: bool,
) -> int:
    """기존 요율 구간을 닫고 새 요율을 등록한다(SCD Type 2).

    매개변수
    --------
    provider: LLM 공급자 식별자(소문자로 정규화됨).
    model: 모델 식별자.
    input_price: 입력 1,000 토큰당 단가(KRW).
    output_price: 출력 1,000 토큰당 단가(KRW).
    effective_from: 새 요율 적용 시작 시각(UTC naive).
    note: 단가 출처 메모(세무 소명 근거).
    dry_run: True 이면 DB 를 변경하지 않고 계획만 출력한다.

    반환
    ----
    프로세스 종료 코드. 0=성공, 1=검증 실패.
    """
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip()

    with get_session_immediate() as session:
        # 동일 시작 시각의 중복 등록 방지(UNIQUE 제약 위반을 사전 차단해
        # 친절한 메시지를 제공).
        duplicate = (
            session.execute(
                select(CCPRateCard).where(
                    CCPRateCard.provider == normalized_provider,
                    CCPRateCard.model == normalized_model,
                    CCPRateCard.effective_from == effective_from,
                )
            )
            .scalars()
            .first()
        )
        if duplicate is not None:
            print(
                f"[ccp] 오류: 동일 시작 시각의 요율이 이미 존재합니다 "
                f"({normalized_provider}/{normalized_model} "
                f"@ {effective_from.isoformat()})"
            )
            return 1

        # 현재 열려 있는 요율 구간을 찾아 닫는다.
        open_card = (
            session.execute(
                select(CCPRateCard)
                .where(
                    CCPRateCard.provider == normalized_provider,
                    CCPRateCard.model == normalized_model,
                    CCPRateCard.effective_to.is_(None),
                )
                .order_by(CCPRateCard.effective_from.desc())
            )
            .scalars()
            .first()
        )

        if open_card is not None:
            if open_card.effective_from >= effective_from:
                print(
                    f"[ccp] 오류: 새 적용 시각({effective_from.isoformat()})이 "
                    f"기존 요율 시작({open_card.effective_from.isoformat()})보다 "
                    f"이르거나 같습니다. 과거로 소급 등록할 수 없습니다."
                )
                return 1
            print(
                f"[ccp] 기존 요율 구간 종료 예정: "
                f"{open_card.effective_from.isoformat()} → {effective_from.isoformat()}"
            )

        print(
            f"[ccp] 신규 요율: {normalized_provider}/{normalized_model} "
            f"in={input_price} out={output_price} KRW/1k "
            f"from={effective_from.isoformat()}"
        )

        if dry_run:
            print("[ccp] --dry-run 이므로 저장하지 않고 종료합니다.")
            return 0

        if open_card is not None:
            open_card.effective_to = effective_from

        session.add(
            CCPRateCard(
                provider=normalized_provider,
                model=normalized_model,
                input_price_per_1k=input_price,
                output_price_per_1k=output_price,
                currency="KRW",
                effective_from=effective_from,
                effective_to=None,
                source_note=note,
            )
        )
        # get_session_immediate 는 컨텍스트 종료 시 커밋한다.
    print("[ccp] 저장 완료.")
    return 0


def main() -> int:
    """CLI 진입점.

    반환
    ----
    프로세스 종료 코드.
    """
    parser = argparse.ArgumentParser(description="CCP 요율 카드 등록/조회")
    parser.add_argument("--list", action="store_true", help="등록된 요율 조회")
    parser.add_argument("--provider", help="LLM 공급자 (예: nvidia)")
    parser.add_argument("--model", help="모델 식별자")
    parser.add_argument(
        "--input-price", type=_parse_price, help="입력 1,000 토큰당 단가(KRW)"
    )
    parser.add_argument(
        "--output-price", type=_parse_price, help="출력 1,000 토큰당 단가(KRW)"
    )
    parser.add_argument(
        "--effective-from",
        type=_parse_datetime,
        default=None,
        help="적용 시작 시각 ISO 8601 (기본: 현재 UTC)",
    )
    parser.add_argument("--note", default=None, help="단가 출처 메모(소명 근거)")
    parser.add_argument(
        "--dry-run", action="store_true", help="저장하지 않고 계획만 출력"
    )
    args = parser.parse_args()

    if args.list:
        return list_rates()

    missing = [
        name
        for name, value in (
            ("--provider", args.provider),
            ("--model", args.model),
            ("--input-price", args.input_price),
            ("--output-price", args.output_price),
        )
        if value is None
    ]
    if missing:
        parser.error(f"다음 인자가 필요합니다: {', '.join(missing)}")

    effective_from = args.effective_from or datetime.now(timezone.utc).replace(
        tzinfo=None
    )
    return upsert_rate(
        provider=args.provider,
        model=args.model,
        input_price=args.input_price,
        output_price=args.output_price,
        effective_from=effective_from,
        note=args.note,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
