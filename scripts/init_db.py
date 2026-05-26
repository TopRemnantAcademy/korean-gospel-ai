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


def _needs_stamp() -> bool:
    """기존 SQLite DB 가 있지만 alembic_version 테이블이 없으면 stamp 필요."""
    if not DATABASE_URL.startswith("sqlite"):
        return False
    db_path_str = DATABASE_URL.replace("sqlite:///", "")
    db_path = Path(db_path_str)
    if not db_path.exists():
        return False  # 신규 설치 → alembic upgrade head 가 fresh 생성
    import sqlite3
    con = sqlite3.connect(str(db_path))
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    con.close()
    return "alembic_version" not in tables and len(tables) > 0


def main():
    print(f"[init_db] DATABASE_URL = {DATABASE_URL}")

    if _needs_stamp():
        print("[init_db] 레거시 DB 감지 → Alembic baseline stamp ...")
        _alembic("stamp", "head")
        print("[init_db] stamp 완료")

    print("[init_db] alembic upgrade head 실행 ...")
    _alembic("upgrade", "head")
    print("[init_db] 마이그레이션 완료")

    # 기본 Category 시드 (있으면 skip)
    from backend.app.db import _init_default_categories
    _init_default_categories()
    print("[init_db] OK - DB 준비 완료")


if __name__ == "__main__":
    main()
