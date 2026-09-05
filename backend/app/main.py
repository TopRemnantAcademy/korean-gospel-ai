"""FastAPI entry point - v3.

실행: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations
import logging
import os
import sys
from contextlib import asynccontextmanager

import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info(" RAG v0.3.1 starting")
    log.info("  LLM       : %s", settings.llm_provider)
    log.info("  Embedder  : %s", settings.embedder)
    log.info("  Qdrant    : %s", settings.qdrant_url)
    log.info("  Policy    : %s", "ON" if settings.policy_enabled else "OFF")
    log.info("  Langfuse  : %s", "ON" if settings.langfuse_enabled else "OFF")
    log.info("  CORS      : %s", settings.cors_origins)
    if settings.admin_api_key == "change-me":
        log.critical("⛔ SECURITY: admin_api_key 가 기본값 — 관리자 API 비활성화됨")
        log.critical(
            "   .env 파일에 ADMIN_API_KEY 를 설정하고 서버를 재시작하세요."
        )
    if settings.dify_api_key == "change-me":
        log.warning("⚠️  SECURITY: dify_api_key 가 기본값입니다.")

    # 결제(PortOne) 구성 검증 — 채널키/웹훅시크릿 누락 시 명확한 경고 (기동 시 조기 발견)
    if not settings.portone_channel_key:
        log.warning(
            "⚠️  PAYMENT: PORTONE_CHANNEL_KEY 미설정 — 결제 준비(/api/payment/prepare)가 503 으로 실패합니다. "
            "PortOne 콘솔에서 채널키를 발급해 .env 에 설정하세요."
        )
    if not settings.portone_webhook_secret:
        log.warning(
            "⚠️  PAYMENT: PORTONE_WEBHOOK_SECRET 미설정 — 결제 웹훅이 거부됩니다(fail-closed, P0-3). "
            "랜덤 값을 생성해 PortOne 콘솔과 .env 양쪽에 동일하게 등록하세요."
        )

    # ── 운영(prod) 보안 구성 강제 (P0-5 / P0-8) ──
    if (settings.app_env or "").strip().lower() == "prod":
        if not settings.auth_secret:
            log.critical(
                "⛔ SECURITY: APP_ENV=prod 인데 AUTH_SECRET 미설정 — "
                "위조 가능한 서명 키로 기동을 거부합니다. AUTH_SECRET 을 설정하세요."
            )
            raise RuntimeError("AUTH_SECRET is required when APP_ENV=prod (P0-5)")
        if settings.email_mode != "smtp":
            log.critical(
                "⛔ SECURITY: APP_ENV=prod 인데 EMAIL_MODE=%s — 이메일 인증이 자동 통과된다. "
                "EMAIL_MODE=smtp + SMTP_* 설정을 권장한다. (P0-8)",
                settings.email_mode,
            )

    try:
        _q_url = (settings.qdrant_url or "").strip()
        if _q_url.startswith("local:"):
            from pathlib import Path as _Path

            _raw = _q_url.split(":", 1)[1] or "./.qdrant_local"
            _q_dir = (_Path(settings.root_dir) / _raw).resolve()
            _lock_file = _q_dir / ".lock"
            if _lock_file.exists():
                _lock_file.unlink()
                log.warning(
                    "[STARTUP] 스테일 Qdrant 잠금 파일 삭제: %s", _lock_file
                )
            else:
                log.info("[STARTUP] Qdrant 잠금 파일 없음 ✅")
    except Exception as _le:
        log.warning("[STARTUP] Qdrant 잠금 파일 정리 실패 (무시): %s", _le)

    try:
        from .connections import connections

        connections.log_status()
    except Exception as _ce:
        log.warning("[STARTUP] connections 상태 확인 실패: %s", _ce)

    try:
        from .services import job_service as _js

        _cleaned = _js.cleanup_stale_jobs(older_than_minutes=30)
        if _cleaned > 0:
            log.warning(
                "[STARTUP] 미완료 백그라운드 작업 %d개 자동 실패 처리 완료",
                _cleaned,
            )
        else:
            log.info("[STARTUP] 미완료 작업 없음 ✅")
    except Exception as _e:
        log.warning("[STARTUP] 잡 정리 실패 (무시): %s", _e)

    import asyncio as _asyncio

    async def _warmup_models():
        try:
            from .services.retriever import get_retriever as _gr

            _r = _gr()
            await _asyncio.to_thread(_r.embedder.embed_query, "warmup")
            log.info("[STARTUP] ✅ KURE 임베딩 모델 사전 로딩 완료")
            from .services.sparse_index import rebuild_from_qdrant as _rebuild

            _n = await _asyncio.to_thread(
                _rebuild, _r.store.collection, _r.store._client
            )
            log.info("[STARTUP] ✅ BM25 sparse 인덱스 재구축: %d개 청크", _n)
        except Exception as _we:
            log.warning("[STARTUP] 모델 사전 로딩 실패 (무시): %s", _we)

        # OPT-SPEED: LLM(분류/답변 공통, 폴백체인 1순위) 사전 웜업 → 첫 요청 TTFT 단축.
        #   nvidia NIM 은 첫 호출 시 모델 인스턴스 기동 지연이 있으므로 기동 단계에서
        #   더미 스트리밍 1토큰으로 예열. 실패 시 무시(런타임에 폴백이 커버).
        try:
            from .services.llm.factory import get_llm as _get_llm
            from .services.llm.base import Message as _Msg
            _chain_raw = settings.llm_fallback_chain or settings.llm_provider
            _chain = [p.strip() for p in _chain_raw.split(",") if p.strip()] if isinstance(_chain_raw, str) else list(_chain_raw)
            _prov = _chain[0]
            _llm = _get_llm(_prov)
            _agen = _llm.stream([_Msg(role="user", content="hi")], max_tokens=1)
            async for _ in _agen:
                break
            log.info("[STARTUP] ✅ LLM(%s) 사전 웜업 완료", _prov)
        except Exception as _lle:
            log.warning("[STARTUP] LLM 사전 웜업 실패 (무시): %s", _lle)

        # OPT-SPEED: 분류기(Gemini) 사전 웜업 → 첫 요청 classify 콜드스타트/3s 타임아웃 회피.
        #   classify_input 은 gemini-2.5-flash 를 쓰며 3s 타임아웃. 콜드 클라이언트는 타임아웃에
        #   걸려 보수적 기본 분류를 쓰거나 3s 를 낭비한다. 기동 단계에서 한 번 호출해 클라이언트를
        #   예열하고 1시간 캐시를 미리 채운다(검색과 병렬 실행되므로 전체 TTFT 영향은 미미하나,
        #   첫 요청 분류 품질·API 낭비를 제거). 실패 시 무시(런타임 폴백이 커버).
        try:
            from .services.classifier import classify_input as _classify

            await _classify("warmup", "ko")
            log.info("[STARTUP] ✅ 분류기(Gemini) 사전 웜업 완료")
        except Exception as _cle:
            log.warning("[STARTUP] 분류기 사전 웜업 실패 (무시): %s", _cle)

    # 웜업을 lifespan 시작 단계(=아직 외부 요청이 없음)에서 동기적(await)으로 실행.
    # app 생성 시점에 create_task 로 띄우면 (a) 참조 미보관으로 GC 위험,
    # (b) lifespan 과 경합하여 embedded Qdrant 클라이언트에 동시 접근(락 충돌) 위험이 있어
    # 의도적으로 yield 이전에 await 로 직렬 실행한다.
    # SKIP_WARMUP=1 이면 웜업 생략(외부 API 블로킹 우려 시 기동 속도 우선, 부하 테스트 등).
    if os.environ.get("SKIP_WARMUP", "0") == "1":
        log.warning("[STARTUP] SKIP_WARMUP=1 — 모델/분류기 사전 웜업 생략")
    else:
        await _warmup_models()
    log.info("[STARTUP] KURE 임베딩 사전 로딩 시작 (백그라운드)…")

    # ── 푸시 알림 스케줄러 (PUSH_ENABLED=true 일 때만 시작)
    try:
        from .services.push_scheduler import start_scheduler as _start_push

        _start_push()
    except Exception as _push_err:
        log.warning("[STARTUP] 푸시 스케줄러 시작 실패 (무시): %s", _push_err)

    # ── 트렌딩 집계 스케줄러 (1분 주기)
    try:
        from .services.trending_scheduler import start_scheduler as _start_trending

        _start_trending()
    except Exception as _trend_err:
        log.warning("[STARTUP] 트렌딩 스케줄러 시작 실패 (무시): %s", _trend_err)

    # ── 미디어 발행/알림 스케줄러 (예약 발행 + 저녁 배치 푸시)
    try:
        from .services.media_publisher import start_scheduler as _start_media_pub

        _start_media_pub()
    except Exception as _mpub_err:
        log.warning("[STARTUP] 미디어 발행 스케줄러 시작 실패 (무시): %s", _mpub_err)

    # ── 미디어 스키마 마이그레이션 (신규 컬럼 존재 보장)
    try:
        from .services import media_service as _media_svc

        _media_svc.ensure_media_schema()
    except Exception as _mschema_err:
        log.warning("[STARTUP] 미디어 스키마 보강 실패 (무시): %s", _mschema_err)

    log.info("=" * 60)
    yield

    # ── 종료: 푸시 스케줄러 정리
    try:
        from .services.push_scheduler import stop_scheduler as _stop_push

        await _stop_push()
    except Exception as _push_err:
        log.warning("[SHUTDOWN] 푸시 스케줄러 종료 실패 (무시): %s", _push_err)

    # ── 종료: 트렌딩 스케줄러 정리
    try:
        from .services.trending_scheduler import stop_scheduler as _stop_trending

        _stop_trending()
    except Exception as _trend_err:
        log.warning("[SHUTDOWN] 트렌딩 스케줄러 종료 실패 (무시): %s", _trend_err)

    # ── 종료: 미디어 발행 스케줄러 정리
    try:
        from .services.media_publisher import stop_scheduler as _stop_media_pub

        _stop_media_pub()
    except Exception as _mpub_err:
        log.warning("[SHUTDOWN] 미디어 발행 스케줄러 종료 실패 (무시): %s", _mpub_err)

    # ── 종료: 전역 커넥션 풀/클라이언트 정리 (소켓/연결 누수 방지)
    try:
        from .connections import connections as _conn

        await _conn.close_connections()
    except Exception as _conn_err:
        log.warning("[SHUTDOWN] 커넥션 정리 실패 (무시): %s", _conn_err)

    # ── 종료: DB 엔진 커넥션 풀 해제
    try:
        from .db import engine as _db_engine

        _db_engine.dispose()
    except Exception as _db_err:
        log.warning("[SHUTDOWN] DB 엔진 dispose 실패 (무시): %s", _db_err)


def create_app() -> FastAPI:
    # P0-3: 프로덕션에서 Swagger/OpenAPI 노출 차단 (env 게이트 DOCS_ENABLED=false)
    _docs_kwargs = (
        {} if settings.docs_enabled
        else {"docs_url": None, "openapi_url": None, "redoc_url": None}
    )
    app = FastAPI(
        title=" RAG API",
        version="0.3.1",
        description="Lifecycle-aware ingestion + hybrid search + safety policy",
        lifespan=lifespan,
        **_docs_kwargs,
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
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],  # P3: 명시적 메서드 제한
        allow_headers=[
            "X-Request-ID",
            "Content-Type",
            "Authorization",
        ],  # P3: 필요한 헤더만
        expose_headers=["X-Request-ID"],  # 클라이언트가 읽을 수 있는 헤더
    )

    init_db()
    log.info("[OK] DB initialized")

    # ── 스키마 마이그레이션은 Alembic 전담 (P1-4: 시작 시 raw DDL 제거)
    #   신규 컬럼/인덱스는 `alembic revision --autogenerate` + `alembic upgrade head` 로 반영.
    #   신규 테이블 생성은 init_db() 의 create_all 로 보장된다 (위 init_db() 호출).
    log.info("[OK] schema migrations delegated to Alembic (no startup DDL)")

    try:
        from .api import (
            chat,
            retrieval,
            admin,
            documents,
            memory,
            prompts,
            subscriber,
            auth,
            drafts,
            jobs,
            mobile,
            content_admin,
            media,
            bible,
            enhanced_rag,
            trending,
            support,
            ranking,
            ads,
            payment,
            ccp,
            events,
        )

        app.include_router(ads.public_router)
        app.include_router(ads.admin_router)
        app.include_router(chat.router)
        app.include_router(retrieval.router)
        app.include_router(admin.router)
        app.include_router(documents.router)
        app.include_router(memory.router)
        app.include_router(prompts.router)
        app.include_router(subscriber.router)
        app.include_router(auth.router)
        app.include_router(drafts.router)
        app.include_router(jobs.router)
        app.include_router(mobile.router)
        app.include_router(content_admin.router)
        app.include_router(media.admin_router)
        app.include_router(media.public_router)
        app.include_router(bible.admin_router)
        app.include_router(bible.public_router)
        app.include_router(enhanced_rag.router)
        app.include_router(trending.router)
        app.include_router(support.router)
        app.include_router(ranking.router)
        app.include_router(payment.router)
        app.include_router(ccp.router)
        app.include_router(events.mobile_router)
        app.include_router(events.admin_router)
        log.info(
            "[OK] routers: chat, retrieval, admin, documents, memory, prompts, subscriber, auth, drafts, jobs, mobile, content, media, bible, enhanced_rag, trending, support, ranking, ads, payment, ccp"
        )
    except Exception as e:
        log.exception("[FATAL] router registration failed: %s", e)
        raise

    @app.get("/")
    def root():
        return {
            "service": "korean-gospel-rag",
            "version": "0.3.1",
            "endpoints": [
                "/chat",
                "/retrieval",
                "/documents",
                "/feedback",
                "/rag/ingest",
                "/rag/query",
                "/rag/documents",
                "/rag/config",
                "/rag/evaluate",
                "/rag/health",
                "/health",
                "/admin/health",
                "/admin/collections",
                "/docs",
            ],
            "llm_provider": settings.llm_provider,
            "embedder": settings.embedder,
            "qdrant_url": settings.qdrant_url,
        }

    @app.get("/health")
    def health():
        """Kubernetes/Docker 헬스프로브용 라이브니스/레디니스 엔드포인트 (인증 불필요).

        docker-compose.prod.yml 및 deploy.sh 가 이 경로를 프로브한다.
        """
        return {"status": "healthy", "version": "0.3.1", "service": "korean-gospel-rag"}

    @app.get("/ready")
    def ready():
        """P0-4: 레디니스 프로브 — 실제 의존성 검증 후 트래픽 게이팅.

        /health(라이브니스)는 프로세스 생존만 확인. 본 엔드포인트는
        DB 연결 + Qdrant 컬렉션 비어있음 + LLM 키 설정을 실제로 검증하며,
        하나라도 실패하면 503 을 반환해 죽은/빈 배포에 트래픽이 라우팅되지 않게 한다.
        (배포 프로브 경로를 /health → /ready 로 전환하는 것은 P2-2 와 연동)
        """
        problems: list[str] = []

        # 1) DB 연결
        try:
            from .db import engine
            from sqlalchemy import text as _text

            with engine.connect() as _c:
                _c.execute(_text("SELECT 1"))
        except Exception as _e:
            problems.append(f"db:{type(_e).__name__}")

        # 2) Qdrant 컬렉션 (기존 클라이언트 캐시 재사용 — embedded 락 안전)
        try:
            from .connections import connections

            _client, _is_server = connections.qdrant()
            if _client is None:
                problems.append("qdrant:client_none")
            else:
                _col = settings.collection_name(settings.embedder)
                _cnt = _client.count(collection_name=_col).count
                if _cnt == 0:
                    problems.append("qdrant:empty_collection")
        except Exception as _e:
            problems.append(f"qdrant:{type(_e).__name__}")

        # 3) LLM 키 설정 (네트워크 호출 없이 config 수준만 확인)
        _prov = settings.llm_provider
        _key_ok = {
            "tencent": bool(settings.tencent_api_key),
            "gemini": bool(settings.google_api_key),
            "deepseek": bool(settings.deepseek_api_key),
            "openai": bool(settings.openai_api_key),
            "anthropic": bool(settings.anthropic_api_key),
            "ollama": True,
        }.get(_prov, False)
        if not _key_ok:
            problems.append(f"llm:key_missing({_prov})")

        if problems:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "problems": problems},
            )
        return {"status": "ready", "version": "0.3.1"}


    return app


try:
    app = create_app()
except Exception as e:
    print("[FATAL] FastAPI app creation failed:", e, file=sys.stderr)
    raise
