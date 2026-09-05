"""SQLAlchemy 엔진 + 세션 + 초기화.

운영 데이터(문서, 버전, audit) 저장소.
디폴트: SQLite 파일 (.gospel.db). 나중에 DATABASE_URL 한 줄로 Postgres 전환 가능.

마이그레이션: Alembic (scripts/init_db.py 참고).
  - 신규 컬럼·테이블 추가: alembic revision --autogenerate -m "설명"
  - 적용: alembic upgrade head  (또는 python scripts/init_db.py)
  - ❌ 더 이상 _sqlite_migrate_columns() 는 사용하지 않음 (F1 Alembic 으로 대체)
"""

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: F1 — _sqlite_migrate_columns() 제거, Alembic 으로 대체
# Reason: ORDERS.md F1
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


ROOT = settings.root_dir
# P9-0 (P0 데이터유실 수정): SQLite 파일 경로를 환경변수 DB_PATH 로 오버라이드 가능케 함.
# 로컬: 미설정 → ROOT/.gospel.db (기존 동작 유지).
# Docker : compose 가 DB_PATH=/app/gospel.db 로 주입 + ./gospel.db:/app/gospel.db 마운트
#          → 컨테이너 재생성 후에도 데이터 보존. (이전엔 /app/.gospel.db 에 기록되어
#          바인드 마운트와 불일치 → 재시작 시 모든 구독자/대화기록 유실)
DB_PATH = Path(os.environ.get("DB_PATH", str(ROOT / ".gospel.db"))).expanduser()


def _resolve_db_url() -> str:
    """DATABASE_URL 환경변수 우선, 없으면 SQLite 파일.

    config.py (settings.database_url) 가 환경변수를 이미 로드하므로 단일 소스.
    """
    env = settings.database_url
    if env:
        return env
    return f"sqlite:///{DB_PATH}"


DATABASE_URL = _resolve_db_url()


# ── 커넥션 풀 설정 (동시 접속 20명 대응) ───────────────────────────────────
# SQLite 기본 풀은 최대 5(QueuePool)라 동시 20접속 시 커넥션 경합 → busy_timeout 초과.
# pool_size=20 + max_overflow=10 으로 최대 30 커넥션 허용(동시 20 CCU 충분).
# pool_pre_ping=True 로 끊긴 커넥션 자동 재확인(스레드 풀 환경에서 유휴 커넥션 복구).
# pool_timeout=30 으로 풀 고갈 시 30초 대기 후 예외(무한 대기 방지).
# read_engine: 읽기 전용 경로용 분리 풀 — 쓰기(BEGIN IMMEDIATE) 배타락과 격리.
_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))
_POOL_MAX_OVERFLOW = int(os.environ.get("DB_POOL_MAX_OVERFLOW", "10"))
_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))


def _engine_kwargs(is_sqlite: bool, pool_size: int | None = None) -> dict:
    base = dict(
        echo=False,
        future=True,
        pool_size=_POOL_SIZE if pool_size is None else pool_size,
        max_overflow=_POOL_MAX_OVERFLOW,
        pool_timeout=_POOL_TIMEOUT,
        pool_pre_ping=True,
        pool_recycle=1800,  # 30분 유휴 커넥션 재생성 (메모리/락 안정성)
    )
    if is_sqlite:
        # SQLite 는 단일 파일 + check_same_thread=False 로 다중 스레드 허용.
        base["connect_args"] = {"check_same_thread": False, "timeout": 30}
    return base


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL.startswith("sqlite")))

# 읽기 전용 격리 풀 (정적 조회 /mobile/* 등 고빈도 경로)
_READ_POOL_SIZE = int(os.environ.get("DB_READ_POOL_SIZE", "24"))
# [FIX] 풀 크기는 생성 시점에 전달(생성 후 .pool.size 직접 변이는 취약했음)
read_engine = create_engine(
    DATABASE_URL,
    **_engine_kwargs(
        DATABASE_URL.startswith("sqlite"),
        pool_size=_READ_POOL_SIZE if DATABASE_URL.startswith("sqlite") else _POOL_SIZE,
    ),
)



# SQLite는 FK 기본 OFF - 강제로 켬
if DATABASE_URL.startswith("sqlite"):

    def _apply_sqlite_pragma(dbapi_conn) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-4000")
        cur.close()

    # [FIX] read_engine 에도 동일 PRAGMA 적용(이전엔 write engine 에만 있어
    # read_engine 커넥션은 cache_size 등이 기본값으로 누락됐음)
    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_conn, _):
        _apply_sqlite_pragma(dbapi_conn)

    @event.listens_for(read_engine, "connect")
    def _sqlite_pragma_read(dbapi_conn, _):
        _apply_sqlite_pragma(dbapi_conn)


SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)

# 읽기 전용 세션 팩토리 — read_engine 바인딩(쓰기 배타락과 격리, 동시 읽기 20+ 지원)
ReadSessionLocal = sessionmaker(
    bind=read_engine, autoflush=False, autocommit=False, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_session() -> Iterator[Session]:
    """with get_session() as s: ..."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@contextmanager
def get_session_immediate() -> Iterator[Session]:
    """SQLite BEGIN IMMEDIATE 세션 — 쓰기 경합 방지 (배타적 락)."""
    s = SessionLocal()
    try:
        if DATABASE_URL.startswith("sqlite"):
            s.execute(text("BEGIN IMMEDIATE"))
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@contextmanager
def get_read_session() -> Iterator[Session]:
    """읽기 전용 세션 — read_engine 풀 사용(쓰기 배타락과 격리).

    동시 20+ 읽기 요청(정적 엔드포인트) 시 쓰기 경로와 커넥션 경합을 분리.
    SQLite 는 read-uncommitted 가 아니므로 WAL 모드에서도 쓰기 진행 중 읽기는
    snapshot 을 봄(블로킹 최소화). BEGIN IMMEDIATE 미사용 → 읽기 병목 제거.
    """
    s = ReadSessionLocal()
    try:
        yield s
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """FastAPI Depends용 DB 세션 제너레이터."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """테이블 생성 (신규 설치용 fallback). 정식 마이그레이션은 scripts/init_db.py 사용.

    ⚠️ 직접 호출보다 `python scripts/init_db.py` (alembic upgrade head) 를 권장.
    이 함수는 Alembic 없이 FastAPI 가 시작될 때 최소한의 테이블 보장용.
    """
    from .models import orm  # noqa: F401  ensure models are registered

    Base.metadata.create_all(bind=engine)
    with get_session() as s:
        _init_default_categories(s)


def _init_default_categories(s: Session) -> None:
    """초기 Category 값 세팅 (신앙 단계, 감정 상태 등)"""
    from .models.orm import Category

    defaults = [
        {
            "type": "faith_stage",
            "name": "구도자 (seeker)",
            "desc": "아직 믿지 않으나 기독교에 관심을 가지고 탐구하는 사람",
        },
        {
            "type": "faith_stage",
            "name": "새신자 (new_believer)",
            "desc": "예수님을 영접한 지 얼마 안 된 사람",
        },
        {
            "type": "faith_stage",
            "name": "성장중 (growing)",
            "desc": "신앙의 성장을 위해 양육과 훈련을 받고 있는 사람",
        },
        {
            "type": "faith_stage",
            "name": "리더 (leader)",
            "desc": "다락방 조장/리더 및 사역자",
        },
        {
            "type": "emotional_state",
            "name": "평안함 (peaceful)",
            "desc": "특별한 문제 없이 평안한 상태",
        },
        {
            "type": "emotional_state",
            "name": "불안/두려움 (anxious)",
            "desc": "미래나 현실의 문제로 두렵고 염려하는 상태",
        },
        {
            "type": "emotional_state",
            "name": "우울/슬픔 (depressed)",
            "desc": "상처나 상실로 인해 마음이 무너지고 우울한 상태",
        },
        {
            "type": "emotional_state",
            "name": "분노/억울 (angry)",
            "desc": "부당한 일이나 관계의 갈등으로 화가 난 상태",
        },
    ]

    # 이미 데이터가 있으면 건너뜀
    if s.query(Category).first():
        return

    for item in defaults:
        s.add(
            Category(
                category_type=item["type"], name=item["name"], description=item["desc"]
            )
        )
    s.flush()
