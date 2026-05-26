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

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


ROOT = settings.root_dir
DB_PATH = ROOT / ".gospel.db"


def _resolve_db_url() -> str:
    """DATABASE_URL 환경변수 우선, 없으면 SQLite 파일."""
    import os
    env = os.getenv("DATABASE_URL")
    if env:
        return env
    return f"sqlite:///{DB_PATH}"


DATABASE_URL = _resolve_db_url()


engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


# SQLite는 FK 기본 OFF - 강제로 켬
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


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
    _init_default_categories()


def _init_default_categories() -> None:
    """초기 Category 값 세팅 (신앙 단계, 감정 상태 등)"""
    from .models.orm import Category
    
    defaults = [
        {"type": "faith_stage", "name": "구도자 (seeker)", "desc": "아직 믿지 않으나 기독교에 관심을 가지고 탐구하는 사람"},
        {"type": "faith_stage", "name": "새신자 (new_believer)", "desc": "예수님을 영접한 지 얼마 안 된 사람"},
        {"type": "faith_stage", "name": "성장중 (growing)", "desc": "신앙의 성장을 위해 양육과 훈련을 받고 있는 사람"},
        {"type": "faith_stage", "name": "리더 (leader)", "desc": "다락방 조장/리더 및 사역자"},
        
        {"type": "emotional_state", "name": "평안함 (peaceful)", "desc": "특별한 문제 없이 평안한 상태"},
        {"type": "emotional_state", "name": "불안/두려움 (anxious)", "desc": "미래나 현실의 문제로 두렵고 염려하는 상태"},
        {"type": "emotional_state", "name": "우울/슬픔 (depressed)", "desc": "상처나 상실로 인해 마음이 무너지고 우울한 상태"},
        {"type": "emotional_state", "name": "분노/억울 (angry)", "desc": "부당한 일이나 관계의 갈등으로 화가 난 상태"},
    ]
    
    with get_session() as s:
        # 이미 데이터가 있으면 건너뜀
        if s.query(Category).first():
            return
            
        for item in defaults:
            s.add(Category(
                category_type=item["type"],
                name=item["name"],
                description=item["desc"]
            ))
        s.commit()
