"""FastAPI entry point - v3.

실행: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db


logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("gospel-api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Korean Gospel RAG API",
        version="0.3.1",
        description="Lifecycle-aware ingestion + hybrid search + safety policy",
    )

    # E-B2: Rate Limit 미들웨어 (CORS 보다 바깥에 등록 → 먼저 실행)
    try:
        from .middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
        log.info("[OK] RateLimitMiddleware registered")
    except Exception as e:
        log.warning("[WARN] RateLimitMiddleware 등록 실패 (무시): %s", e)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"],
    )

    init_db()
    log.info("[OK] DB initialized")

    try:
        from .api import chat, retrieval, eval as eval_api, admin, documents, memory, prompts, subscriber, admin_agent, invite_codes, auth, glossary, drafts
        app.include_router(chat.router)
        app.include_router(retrieval.router)
        app.include_router(eval_api.router)
        app.include_router(admin.router)
        app.include_router(documents.router)
        app.include_router(memory.router)
        app.include_router(prompts.router)
        app.include_router(subscriber.router)
        app.include_router(admin_agent.router)
        app.include_router(invite_codes.router)
        app.include_router(auth.router)
        app.include_router(glossary.router)
        app.include_router(drafts.router)
        log.info("[OK] routers: chat, retrieval, eval, admin, documents, subscriber, admin_agent, invite_codes, auth, glossary, drafts")
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
        log.info("=" * 60)

    return app


try:
    app = create_app()
except Exception as e:
    print("[FATAL] FastAPI app creation failed:", e, file=sys.stderr)
    raise
