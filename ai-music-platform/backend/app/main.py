"""FastAPI 入口：CORS、路由挂载、启动建表。"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.audit import log_admin_access
from app.config import settings
from app.db import init_db
from app.routers import admin, auth, songs, flow, billing
from app.routers.auth import _resolve_admin_role

log = logging.getLogger("music-api")

# [D37] 공개된 기본 서명 키 집합(routers/auth.py 와 동일 기준).
# 여기서는 **기동 시점 가시성** 용으로만 쓴다 — 실제 차단은 auth.py 가 수행한다.
_INSECURE_JWT_SECRETS = frozenset(
    {"", "change-me-please", "changeme", "change-me", "secret", "test"}
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── T5.6 / X9 — create_all 폴백 환경 분기 (FLOW 와 동일) ──
    # 운영(공유 Postgres) 에서는 Alembic `upgrade head` 로 스키마를 구성하므로
    # create_all 을 비활성화한다(SCHEMA_CREATE_ALL=0). 개발·SQLite 기본값은 활성.
    # 빈 DB 에서 FLOW upgrade head 가 스키마를 완성하지 못하는 경우(D21) 를 대비해
    # 기본값은 "1"(활성) 로 둔다.
    if os.environ.get("SCHEMA_CREATE_ALL", "1") == "1":
        init_db()
    # [D37] 기동 즉시 경고 — 첫 로그인 시도 전에도 운영자가 오구성을 볼 수 있게 한다.
    # (차단 자체는 routers/auth.py:_assert_jwt_secret_configured 가 503 으로 수행)
    if settings.jwt_secret.strip().lower() in _INSECURE_JWT_SECRETS:
        log.error(
            "[SECURITY] JWT_SECRET 이 공개된 기본값(%r) 입니다 — 누구나 위조 토큰을 만들 수 있습니다. "
            "JWT_SECRET 환경변수를 반드시 설정하세요. (docker-compose.yml 의 기본값 주입도 제거됨)",
            settings.jwt_secret,
        )
    yield


app = FastAPI(title="AI 音乐平台 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def admin_rbac_audit(request: Request, call_next):
    """管理后台 RBAC + 审计（GAP-006）：

    - viewer 令牌对变更类(GET 外)接口直接 403；super 令牌不受影响。
    - 所有 /api/admin 访问（含 401/403/200）写入审计日志，便于追溯入侵与操作。
    """
    path = request.url.path
    is_admin = path.startswith("/api/admin")
    response = None
    if is_admin and request.method in _MUTATING_METHODS:
        if _resolve_admin_role(request.headers.get("X-Admin-Token")) == "viewer":
            response = JSONResponse(
                status_code=403, content={"detail": "只读管理员无权执行变更操作"}
            )
    if response is None:
        response = await call_next(request)
    if is_admin:
        token = request.headers.get("X-Admin-Token")
        role = _resolve_admin_role(token) or "none"
        ip = request.client.host if request.client else ""
        log_admin_access(
            method=request.method,
            path=path,
            status_code=response.status_code,
            token_prefix=(token or "")[:6],
            role=role,
            ip=ip,
        )
    return response


app.include_router(auth.router)
app.include_router(songs.router)
app.include_router(flow.router)
app.include_router(admin.router)
app.include_router(billing.router)


@app.get("/health")
def health():
    return {"status": "ok"}
