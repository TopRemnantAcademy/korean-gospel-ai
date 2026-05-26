"""SQLite → PostgreSQL 전체 데이터 이전 스크립트.

사용법:
    python scripts/migrate_sqlite_to_postgres.py \
        --sqlite .gospel.db \
        --postgres $SUPABASE_URL \
        [--tables subscriber audit_log salvation_journey ...] \
        [--batch 500] \
        [--dry-run]

전제 조건:
  - Alembic upgrade head 가 PostgreSQL 에 이미 적용되어 있어야 함
    (scripts/upgrade/tier_0_to_0_5.py Tier15To2._migrate_schema 참조)
  - pip install psycopg2-binary sqlalchemy
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("migrate")

# 이전할 테이블 순서 (외래 키 의존성 고려 — 부모 먼저)
DEFAULT_TABLE_ORDER = [
    "category",
    "subscriber",
    "token_usage",
    "conversation_history",
    "salvation_journey",
    "audit_log",
    "invite_code",
    "document_chunk",
    "glossary_entry",
    "draft",
]


def _get_sqlite_engine(sqlite_path: str):
    from sqlalchemy import create_engine
    url = f"sqlite:///{sqlite_path}"
    return create_engine(url, connect_args={"check_same_thread": False})


def _get_postgres_engine(pg_url: str):
    from sqlalchemy import create_engine
    url = pg_url if pg_url.startswith("postgresql") else f"postgresql://{pg_url}"
    return create_engine(url, pool_pre_ping=True)


def _reflect_table(engine, table_name: str):
    from sqlalchemy import MetaData, Table
    meta = MetaData()
    try:
        tbl = Table(table_name, meta, autoload_with=engine)
        return tbl
    except Exception as e:
        log.warning("테이블 반영 실패 '%s': %s", table_name, e)
        return None


def migrate_table(
    src_engine,
    dst_engine,
    table_name: str,
    batch_size: int = 500,
    dry_run: bool = False,
) -> int:
    """단일 테이블 이전. 이전된 행 수 반환."""
    from sqlalchemy import text

    with src_engine.connect() as src_conn:
        rows = src_conn.execute(text(f"SELECT * FROM {table_name}")).mappings().all()

    if not rows:
        log.info("  %s: 행 없음, 건너뜀", table_name)
        return 0

    total = len(rows)
    log.info("  %s: %d 행 이전 중...", table_name, total)

    if dry_run:
        log.info("  [dry-run] 실제 쓰기 생략")
        return total

    src_tbl = _reflect_table(src_engine, table_name)
    if src_tbl is None:
        return 0

    inserted = 0
    with dst_engine.begin() as dst_conn:
        # 기존 데이터 삭제 (멱등성 보장) — 운영 DB에서는 주의!
        dst_conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))

        for i in range(0, total, batch_size):
            batch = [dict(r) for r in rows[i : i + batch_size]]
            dst_conn.execute(src_tbl.insert(), batch)
            inserted += len(batch)
            log.info("    ... %d / %d", inserted, total)

    return inserted


def run_migration(
    sqlite_path: str,
    pg_url: str,
    tables: Optional[list[str]] = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, int]:
    """전체 이전 실행. {table_name: row_count} 반환."""
    if not Path(sqlite_path).exists():
        log.error("SQLite 파일을 찾을 수 없음: %s", sqlite_path)
        sys.exit(1)

    src = _get_sqlite_engine(sqlite_path)
    dst = _get_postgres_engine(pg_url)

    # 연결 테스트
    try:
        from sqlalchemy import text
        with dst.connect() as c:
            c.execute(text("SELECT 1"))
        log.info("PostgreSQL 연결 성공")
    except Exception as e:
        log.error("PostgreSQL 연결 실패: %s", e)
        sys.exit(1)

    target_tables = tables or DEFAULT_TABLE_ORDER
    results: dict[str, int] = {}

    for tbl in target_tables:
        try:
            count = migrate_table(src, dst, tbl, batch_size=batch_size, dry_run=dry_run)
            results[tbl] = count
        except Exception as e:
            log.error("  %s 이전 실패: %s", tbl, e)
            results[tbl] = -1

    log.info("=" * 50)
    log.info("이전 완료 요약:")
    for tbl, cnt in results.items():
        status = "❌ 실패" if cnt < 0 else (f"✅ {cnt}행" if cnt > 0 else "⚪ 비어있음")
        log.info("  %-30s %s", tbl, status)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 데이터 이전")
    parser.add_argument("--sqlite", default=".gospel.db", help="SQLite DB 경로")
    parser.add_argument("--postgres", required=True, help="PostgreSQL 연결 URL (SUPABASE_URL)")
    parser.add_argument("--tables", nargs="*", help="이전할 테이블 목록 (생략 시 전체)")
    parser.add_argument("--batch", type=int, default=500, help="배치 크기 (기본 500)")
    parser.add_argument("--dry-run", action="store_true", help="실제 쓰기 없이 행 수만 확인")
    args = parser.parse_args()

    if args.dry_run:
        log.info("[DRY-RUN 모드] 실제 데이터 쓰기를 수행하지 않습니다.")

    run_migration(
        sqlite_path=args.sqlite,
        pg_url=args.postgres,
        tables=args.tables,
        batch_size=args.batch,
        dry_run=args.dry_run,
    )
