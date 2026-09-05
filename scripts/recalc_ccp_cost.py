"""이미 저장된 interaction 행의 원가를 소급 산정한다(멱등).

용도
----
- CCP 도입 이전에 쌓인 과거 행의 원가 백필(backfill)
- 요율 카드를 뒤늦게 등록해 ``cost_krw`` 가 NULL 로 남은 행의 복구

멱등성
------
기본적으로 ``cost_krw IS NULL`` 인 행만 처리하므로 몇 번을 실행해도
결과가 같다. 이미 확정된 원가는 건드리지 않는다(증빙 신뢰성 보호).

``--force`` 는 이미 계산된 행까지 재계산한다. 요율을 잘못 등록해
정정이 필요한 예외 상황에만 사용해야 하며, 기본 동작이 아니다.

원가는 **각 행의 created_at 시점 요율**로 계산되므로, 과거 행에는 과거
요율이 적용된다.

사용 예::

    python scripts/recalc_ccp_cost.py --dry-run
    python scripts/recalc_ccp_cost.py --batch-size 500
    python scripts/recalc_ccp_cost.py --force --since 2026-07-01T00:00:00
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import select  # noqa: E402

from backend.app.db import get_session_immediate  # noqa: E402
from backend.app.models.orm import Interaction  # noqa: E402
from backend.app.services.ccp.rate_service import (  # noqa: E402
    RateNotFoundError,
    compute_cost_from_card,
    resolve_rate_card,
)

# 한 트랜잭션에서 처리할 기본 행 수. SQLite 쓰기 락 점유 시간을 제한한다.
DEFAULT_BATCH_SIZE = 500


def _parse_datetime(raw: str) -> datetime:
    """ISO 8601 문자열을 UTC naive datetime 으로 변환한다.

    매개변수
    --------
    raw: ISO 8601 문자열.

    반환
    ----
    UTC 기준 naive datetime.

    예외
    ----
    argparse.ArgumentTypeError: 형식 오류 시.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"ISO 8601 형식이 아닙니다: {raw!r}"
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def recalc(
    batch_size: int,
    force: bool,
    since: datetime | None,
    dry_run: bool,
) -> int:
    """대상 interaction 행의 원가를 배치 단위로 산정한다.

    매개변수
    --------
    batch_size: 한 트랜잭션에서 처리할 행 수(1 이상).
    force: True 이면 이미 원가가 있는 행도 재계산한다.
    since: 이 시각 이후 생성된 행만 처리. None 이면 전체.
    dry_run: True 이면 DB 를 변경하지 않는다.

    반환
    ----
    프로세스 종료 코드(항상 0).
    """
    total_updated = 0
    total_skipped = 0
    # 요율 미등록 조합을 집계해 운영자가 무엇을 등록해야 하는지 알려준다.
    missing_rates: dict[tuple[str, str], int] = {}
    # 이미 처리한 마지막 PK — 커서 기반 페이징으로 배치 간 중복/누락을 방지한다.
    last_id: str | None = None

    while True:
        with get_session_immediate() as session:
            stmt = select(Interaction).where(
                Interaction.llm_provider.isnot(None),
                Interaction.llm_model.isnot(None),
                Interaction.prompt_tokens.isnot(None),
                Interaction.completion_tokens.isnot(None),
            )
            if not force:
                stmt = stmt.where(Interaction.cost_krw.is_(None))
            if since is not None:
                stmt = stmt.where(Interaction.created_at >= since)
            if last_id is not None:
                stmt = stmt.where(Interaction.interaction_id > last_id)

            rows = (
                session.execute(
                    stmt.order_by(Interaction.interaction_id).limit(batch_size)
                )
                .scalars()
                .all()
            )
            if not rows:
                break

            last_id = rows[-1].interaction_id

            for row in rows:
                try:
                    card = resolve_rate_card(
                        session,
                        row.llm_provider,
                        row.llm_model,
                        at=row.created_at,
                    )
                    breakdown = compute_cost_from_card(
                        card, row.prompt_tokens, row.completion_tokens
                    )
                except RateNotFoundError:
                    key = (row.llm_provider, row.llm_model)
                    missing_rates[key] = missing_rates.get(key, 0) + 1
                    total_skipped += 1
                    continue
                except (TypeError, ValueError) as exc:
                    print(
                        f"[ccp] 건너뜀 interaction_id={row.interaction_id}: {exc}"
                    )
                    total_skipped += 1
                    continue

                if not dry_run:
                    row.cost_krw = breakdown.cost_krw
                    row.rate_card_id = breakdown.rate_card_id
                total_updated += 1

            if dry_run:
                # 변경 사항을 커밋하지 않도록 세션을 정리한다.
                session.expunge_all()

        # 커서(last_id)가 매 배치마다 전진하므로 종료가 보장된다.
        print(f"[ccp] 진행: 산정 {total_updated}건 / 건너뜀 {total_skipped}건")

    print(
        f"[ccp] 완료 — 산정 {total_updated}건, 건너뜀 {total_skipped}건"
        + (" (dry-run: 저장하지 않음)" if dry_run else "")
    )
    if missing_rates:
        print("[ccp] 요율 미등록으로 건너뛴 조합 (scripts/seed_ccp_rates.py 로 등록 필요):")
        for (provider, model), count in sorted(
            missing_rates.items(), key=lambda kv: kv[1], reverse=True
        ):
            print(f"  - {provider}/{model}: {count}건")
    return 0


def main() -> int:
    """CLI 진입점.

    반환
    ----
    프로세스 종료 코드.
    """
    parser = argparse.ArgumentParser(description="CCP 원가 소급 산정(멱등)")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"배치 크기 (기본 {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 산정된 원가도 재계산 (요율 정정 시에만 사용)",
    )
    parser.add_argument(
        "--since",
        type=_parse_datetime,
        default=None,
        help="이 시각 이후 생성된 행만 처리 (ISO 8601)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="저장하지 않고 건수만 확인"
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size 는 1 이상이어야 합니다")

    return recalc(
        batch_size=args.batch_size,
        force=args.force,
        since=args.since,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
