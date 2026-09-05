"""数据库引擎与会话（SQLAlchemy 2.x）。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # 开发兜底：幂等建表，便于本地快速启动；生产 schema 演进以 Alembic 为准
    # （见 migrations/，部署用 `alembic upgrade head`）。两者共存无害。
    import app.models  # noqa: F401 确保模型注册
    import app.billing.models  # noqa: F401 支付/订阅模型注册(GAP-004)
    Base.metadata.create_all(bind=engine)
    # 注入默认后台配置（引擎/路由/计费）；已存在则保留后台值（见 app.orchestrator.selection.seed_default_config）
    from app.orchestrator.selection import seed_default_config
    seed_default_config(SessionLocal())
