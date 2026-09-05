import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import app.db as dbmod
from app.db import Base, SessionLocal
from app.config import settings
# 注意：不要用 `from app.main import app`，因为 `import app.db` 会把顶层
# 名字 `app` 绑成「app 包模块」本身，导致 fixture 里 app 变成 module 而非
# FastAPI 实例。显式取到模块对象再取 .app 属性，避开名字遮蔽。
import app.main as _app_main
fastapi_app = _app_main.app

# 单一测试库（文件型 SQLite，便于跨连接可见）
DB_PATH = "/tmp/music_test_session.db"
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)

# 关键修复：重绑「同一个」sessionmaker 对象的 bind，而不是替换对象本身。
# songs.py / auth.py 等都用 `from app.db import SessionLocal`，持有的是该对象引用，
# 只有 configure(bind=...) 改同一对象才能让所有持有者都指向测试库。
SessionLocal.configure(bind=engine)
dbmod.engine = engine  # 让 lifespan / 其它用 dbmod.engine 的地方也指向测试库

import app.models  # 确保模型注册到 Base.metadata
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

from app.orchestrator.client import set_orchestrator
from app.orchestrator.mock import MockProvider

set_orchestrator(MockProvider())  # 注入 mock 编排层，全程不依赖真实 Suno

# 测试配置覆盖
settings.enable_rate_limit = False
settings.enable_moderation = True
settings.song_poll_interval = 0
settings.song_poll_timeout = 2
settings.jwt_secret = "test-secret-for-pytest-only"


@pytest.fixture(scope="session")
def client():
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    yield
    sl = SessionLocal()
    try:
        for tbl in reversed(Base.metadata.sorted_tables):
            sl.execute(tbl.delete())
        sl.commit()
    finally:
        sl.close()
