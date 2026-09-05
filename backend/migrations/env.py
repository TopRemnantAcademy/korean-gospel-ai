"""Alembic 환경 설정 — .

DB URL: DATABASE_URL 환경변수 우선, 없으면 .gospel.db SQLite.
모델: backend.app.models.orm (SQLAlchemy ORM 전체).
"""
from __future__ import annotations
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, event, pool

from alembic import context

# ── 프로젝트 루트를 sys.path 에 추가 (import 보장) ──────────────────────────
ROOT = Path(__file__).resolve().parents[2]  # backend/migrations → korean-gospel-ai
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── .env 로드 (DATABASE_URL 등) ─────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── ORM 모델 임포트 (autogenerate 가 테이블 변경 감지) ─────────────────────
from backend.app.db import Base  # noqa: F401 — Base 등록
import backend.app.models.orm  # noqa: F401 — 모든 테이블을 Base.metadata 에 등록

# ── DB URL 동적 결정 (ini 파일 override) ────────────────────────────────────
def _resolve_url() -> str:
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return f"sqlite:///{ROOT / '.gospel.db'}"


# Alembic config 객체
config = context.config
config.set_main_option("sqlalchemy.url", _resolve_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _apply_sqlite_pragmas(conn, _):
    """SQLite FK + WAL 강제 (db.py 와 동일)."""
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER TABLE 지원
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    url = config.get_main_option("sqlalchemy.url")
    if url.startswith("sqlite"):
        event.listen(connectable, "connect", _apply_sqlite_pragmas)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 에서 컬럼 수정·삭제 가능하게 함
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
