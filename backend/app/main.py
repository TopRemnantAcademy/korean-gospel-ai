"""FastAPI entry point - v3.

실행: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations
import logging
import sys

import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .db import init_db
from .logging_setup import setup_logging

# 파일 로테이션 로깅 초기화 (logs/backend.log, logs/errors.log)
setup_logging(settings.log_level)
log = logging.getLogger("gospel-api")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """X-Request-ID 헤더 주입 — 없으면 UUID 생성, 있으면 그대로 전달."""
    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="Korean Gospel RAG API",
        version="0.3.1",
        description="Lifecycle-aware ingestion + hybrid search + safety policy",
    )

    # Request ID 미들웨어 (가장 바깥에 — 모든 요청에 적용)
    app.add_middleware(RequestIDMiddleware)

    # 에러 모니터링 미들웨어 (가장 안쪽 — 실제 요청 처리에 가깝게)
    try:
        from .middleware.error_monitor import ErrorMonitorMiddleware
        app.add_middleware(ErrorMonitorMiddleware)
        log.info("[OK] ErrorMonitorMiddleware registered")
    except Exception as e:
        log.warning("[WARN] ErrorMonitorMiddleware 등록 실패 (무시): %s", e)

    # E-B2: Rate Limit 미들웨어 (CORS 보다 바깥에 등록 → 먼저 실행)
    try:
        from .middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
        log.info("[OK] RateLimitMiddleware registered")
    except Exception as e:
        log.warning("[WARN] RateLimitMiddleware 등록 실패 (무시): %s", e)

    _cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],  # P3: 명시적 메서드 제한
        allow_headers=["X-Request-ID", "Content-Type", "Authorization"],  # P3: 필요한 헤더만
        expose_headers=["X-Request-ID"],  # 클라이언트가 읽을 수 있는 헤더
    )

    init_db()
    log.info("[OK] DB initialized")

    # ── 시작 시 DB 컬럼 자동 보정 (ORM vs 실제 DB 불일치 방지)
    try:
        from sqlalchemy import inspect as _inspect, text as _text
        from .db import Base as _Base, engine as _engine
        from .models import orm as _orm_module  # noqa — 모델 등록
        _insp = _inspect(_engine)
        _existing = set(_insp.get_table_names())
        _patched = []
        with _engine.connect() as _conn:
            for _tbl in _Base.metadata.sorted_tables:
                if _tbl.name not in _existing:
                    _tbl.create(bind=_engine)
                    _patched.append(f"+TABLE:{_tbl.name}")
                    continue
                _ecols = {c["name"] for c in _insp.get_columns(_tbl.name)}
                for _col in _tbl.columns:
                    if _col.name not in _ecols:
                        _dtype = str(_col.type).upper()
                        _sql = f'ALTER TABLE "{_tbl.name}" ADD COLUMN "{_col.name}" {_dtype}'
                        try:
                            _conn.execute(_text(_sql))
                            _conn.commit()
                            _patched.append(f"+COL:{_tbl.name}.{_col.name}")
                        except Exception as _ce:
                            log.warning("[DB-PATCH] skip %s.%s: %s", _tbl.name, _col.name, _ce)
        if _patched:
            log.warning("[DB-PATCH] 자동 컬럼 추가: %s", _patched)
        else:
            log.info("[DB-PATCH] 스키마 일치 ✅")
    except Exception as _e:
        log.error("[DB-PATCH] 자동 마이그레이션 실패: %s", _e)

    try:
        from .api import chat, retrieval, eval as eval_api, admin, documents, memory, prompts, subscriber, auth, glossary, drafts, jobs
        app.include_router(chat.router)
        app.include_router(retrieval.router)
        app.include_router(eval_api.router)
        app.include_router(admin.router)
        app.include_router(documents.router)
        app.include_router(memory.router)
        app.include_router(prompts.router)
        app.include_router(subscriber.router)
        app.include_router(auth.router)
        app.include_router(glossary.router)
        app.include_router(drafts.router)
        app.include_router(jobs.router)
        log.info("[OK] routers: chat, retrieval, eval, admin, documents, subscriber, auth, glossary, drafts, jobs")
    except Exception as e:
        log.exception("[FATAL] router registration failed: %s", e)
        raise

    @app.get("/")
    def root():
        return {
            "service": "korean-gospel-rag",
            "version": "0.3.1",
            "endpoints": [
                "/chat", "/retrieval",
                "/documents", "/eval/ab", "/eval/generate-questions", "/eval/tune-weights",
                "/feedback",
                "/admin/health", "/admin/collections",
                "/docs",
            ],
            "llm_provider": settings.llm_provider,
            "embedder": settings.embedder,
            "qdrant_url": settings.qdrant_url,
        }

    @app.on_event("startup")
    async def on_startup():
        log.info("=" * 60)
        log.info("Korean Gospel RAG v0.3.1 starting")
        log.info("  LLM       : %s", settings.llm_provider)
        log.info("  Embedder  : %s", settings.embedder)
        log.info("  Qdrant    : %s", settings.qdrant_url)
        log.info("  Policy    : %s", "ON" if settings.policy_enabled else "OFF")
        log.info("  Langfuse  : %s", "ON" if settings.langfuse_enabled else "OFF")
        log.info("  CORS      : %s", settings.cors_origins)
        if settings.admin_api_key == "change-me":
            log.critical("⛔ SECURITY: admin_api_key 가 기본값 — 관리자 API 비활성화됨")
            log.critical("   .env 파일에 ADMIN_API_KEY 를 설정하고 서버를 재시작하세요.")
        if settings.dify_api_key == "change-me":
            log.warning("⚠️  SECURITY: dify_api_key 가 기본값입니다.")

        # embedded Qdrant 스테일 잠금 파일 자동 정리
        # 비정상 종료 시 .lock 파일이 남아 재시작 시 "already accessed" 오류 발생 방지
        try:
            _q_url = (settings.qdrant_url or "").strip()
            if _q_url.startswith("local:"):
                from pathlib import Path as _Path
                _raw = _q_url.split(":", 1)[1] or "./.qdrant_local"
                _q_dir = (_Path(settings.root_dir) / _raw).resolve()
                _lock_file = _q_dir / ".lock"
                if _lock_file.exists():
                    _lock_file.unlink()
                    log.warning("[STARTUP] 스테일 Qdrant 잠금 파일 삭제: %s", _lock_file)
                else:
                    log.info("[STARTUP] Qdrant 잠금 파일 없음 ✅")
        except Exception as _le:
            log.warning("[STARTUP] Qdrant 잠금 파일 정리 실패 (무시): %s", _le)

        # 중앙 연결 레지스트리 상태 로깅 (connections.py)
        try:
            from .connections import connections
            connections.log_status()
        except Exception as _ce:
            log.warning("[STARTUP] connections 상태 확인 실패: %s", _ce)

        # 이전 서버 실행 중 미완료된 background 잡 자동 실패 처리
        # (재시작 시 asyncio 태스크가 모두 소멸 → pending/running 잡이 영원히 남는 문제 방지)
        try:
            from .services import job_service as _js
            _cleaned = _js.cleanup_stale_jobs(older_than_minutes=30)
            if _cleaned > 0:
                log.warning("[STARTUP] 미완료 백그라운드 작업 %d개 자동 실패 처리 완료", _cleaned)
            else:
                log.info("[STARTUP] 미완료 작업 없음 ✅")
        except Exception as _e:
            log.warning("[STARTUP] 잡 정리 실패 (무시): %s", _e)

        # ⚡ 임베딩 모델 사전 로딩 — 첫 요청 지연(~10s) 방지
        import asyncio as _asyncio

        async def _warmup_models():
            try:
                from .services.retriever import get_retriever as _gr
                _r = _gr()
                await _asyncio.to_thread(_r.embedder.embed_query, "warmup")
                log.info("[STARTUP] ✅ KURE 임베딩 모델 사전 로딩 완료")
                # V2: 자체 BM25 sparse 인덱스를 Qdrant 에서 재구축 (하이브리드 검색)
                from .services.sparse_index import rebuild_from_qdrant as _rebuild
                _n = await _asyncio.to_thread(_rebuild, _r.store.collection, _r.store.client)
                log.info("[STARTUP] ✅ BM25 sparse 인덱스 재구축: %d개 청크", _n)
            except Exception as _we:
                log.warning("[STARTUP] 모델 사전 로딩 실패 (무시): %s", _we)

        _asyncio.create_task(_warmup_models())
        log.info("[STARTUP] KURE 임베딩 사전 로딩 시작 (백그라운드)…")

        log.info("=" * 60)

    return app


try:
    app = create_app()
except Exception as e:
    print("[FATAL] FastAPI app creation failed:", e, file=sys.stderr)
    raise
