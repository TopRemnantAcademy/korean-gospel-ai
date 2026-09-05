"""DB 초기화 + Alembic 마이그레이션 실행. idempotent.

사용:
    python scripts/init_db.py

동작:
1. 기존 DB (.gospel.db) 가 있고 alembic_version 테이블이 없으면 → stamp head (레거시 → Alembic 전환)
2. alembic upgrade head 실행 (새 컬럼·테이블 자동 추가)
3. 기본 Category 시드 데이터 삽입
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: F1 — Alembic 마이그레이션 도입 (create_all + _sqlite_migrate_columns 대체)
# Reason: ORDERS.md F1 — 신규 컬럼을 데이터 손실 없이 추가 가능하게
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.app.db import DATABASE_URL


def _alembic(*args: str) -> None:
    """alembic 명령 실행 (프로젝트 루트 기준)."""
    cmd = [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} 실패 (exit {result.returncode})")


def _db_path() -> Path:
    """DATABASE_URL 에서 SQLite 파일 경로를 추출한다(비 sqlite 는 빈 경로)."""
    if not DATABASE_URL.startswith("sqlite"):
        return Path()
    return Path(DATABASE_URL.replace("sqlite:///", ""))


def _existing_tables(db_path: Path) -> set[str]:
    import sqlite3

    con = sqlite3.connect(str(db_path))
    try:
        return {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        con.close()


def _needs_stamp() -> bool:
    """기존 SQLite DB 가 있지만 alembic_version 테이블이 없으면 stamp 필요."""
    if not DATABASE_URL.startswith("sqlite"):
        return False
    db_path = _db_path()
    if not db_path.exists():
        return False  # 신규 설치 → 아래 main() 에서 create_all + stamp head 처리
    return "alembic_version" not in _existing_tables(db_path)


def _create_tables_via_metadata() -> None:
    """신규 설치: Alembic baseline(c2fbb2654cf3)이 ALTER-only 라 빈 DB 에서
    'no such table: document_version' 로 실패한다. 따라서 ORM 메타데이터로
    테이블을 먼저 생성한 뒤 stamp head 로 Alembic 체인과 정렬한다
    (데이터 손실 없는 idempotent 동작)."""
    from backend.app.db import Base, engine
    import backend.app.models.orm  # noqa: F401  모든 테이블을 Base.metadata 에 등록

    Base.metadata.create_all(bind=engine)


def main():
    print(f"[init_db] DATABASE_URL = {DATABASE_URL}")

    if not DATABASE_URL.startswith("sqlite"):
        # Postgres 등: 빈 스키마에 Alembic 이 직접 생성하므로 upgrade head.
        print("[init_db] 비-sqlite → alembic upgrade head 실행 ...")
        _alembic("upgrade", "head")
        print("[init_db] 마이그레이션 완료")
        _seed_default_categories()
        return

    db_path = _db_path()

    if not db_path.exists():
        # ── 신규 설치(빈 DB) 경로 ──
        # baseline 마이그레이션은 ALTER-only 이므로 빈 DB 에서 upgrade head 가
        # 실패한다. ORM 메타데이터로 테이블을 먼저 생성하고 stamp head 로
        # Alembic 버전 테이블을 현재 HEAD 와 정렬한다(무 DDL).
        print("[init_db] 신규 설치 감지 → ORM 메타데이터로 테이블 생성 ...")
        _create_tables_via_metadata()
        print("[init_db] Alembic HEAD stamp (baseline 정렬) ...")
        _alembic("stamp", "head")
        print("[init_db] stamp 완료")
    elif _needs_stamp():
        # ── 레거시 DB(테이블은 있으나 alembic_version 없음) 경로 ──
        print("[init_db] 레거시 DB 감지 → Alembic baseline stamp ...")
        _alembic("stamp", "head")
        print("[init_db] stamp 완료")
    else:
        # ── 이미 Alembic 추적 중인 DB 경로 ──
        print("[init_db] alembic upgrade head 실행 ...")
        _alembic("upgrade", "head")
        print("[init_db] 마이그레이션 완료")

    _seed_default_categories()
    print("[init_db] OK - DB 준비 완료")


def _seed_default_categories() -> None:
    """기본 Category 시드 (이미 있으면 _init_default_categories 내부에서 skip)."""
    from backend.app.db import _init_default_categories, get_session

    with get_session() as s:
        _init_default_categories(s)


if __name__ == "__main__":
    main()
