"""ErrorMonitorMiddleware — 런타임 에러 + 슬로우 리퀘스트 자동 DB 기록.

기록 조건:
  ERROR    : HTTP 응답 500 이상
  SLOW     : 정상 응답이지만 10~30초 소요
  CRITICAL : 30초 초과 또는 미처리 예외(traceback 포함)

DB write 는 asyncio.create_task() 로 비동기 분리 — 응답 속도에 영향 없음.
실패해도 앱은 정상 동작 (try/except 전체 보호).
"""
from __future__ import annotations

import asyncio
import time
import traceback as tb_module
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 슬로우 리퀘스트 기준 (ms)
_SLOW_MS = 10_000     # 10초 이상 → SLOW
_CRIT_MS = 30_000     # 30초 이상 → CRITICAL

# 노이즈 경로 제외 (정적 리소스 등)
_SKIP_PREFIXES = ("/docs", "/openapi", "/favicon")

# 백그라운드 태스크 참조 보관 — GC 방지
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg_task(coro) -> None:
    """asyncio.create_task 참조를 보관하여 예기치 않은 GC 를 방지."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _write_error_log(
    *,
    level: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    traceback_str: Optional[str] = None,
    request_id: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> None:
    """DB에 에러 로그 1건 저장. 실패해도 예외를 외부로 전파하지 않는다."""
    try:
        from ..models.orm import AppErrorLog
        from ..logging_setup import scrub_secrets

        row = AppErrorLog(
            level=level,
            method=method,
            path=path[:200],
            status_code=status_code,
            error_type=(error_type or "")[:120],
            # P10-7 (P2 보안): 예외 메시지/트레이스백에 API 키·토큰·DB 비밀번호 등이
            # 들어갈 수 있으므로 저장 전 마스킹.
            error_message=scrub_secrets((error_message or ""))[:2000],
            traceback=scrub_secrets(traceback_str)[:5000] if traceback_str else None,
            duration_ms=duration_ms,
            request_id=(request_id or "")[:40],
            client_ip=(client_ip or "")[:50],
        )
        # get_session() 은 동기 컨텍스트 매니저 → to_thread 로 분리
        await asyncio.to_thread(_sync_write, row)
    except Exception:
        pass  # 로깅 실패는 무조건 무시


def _sync_write(row) -> None:
    from ..db import get_session
    with get_session() as s:
        s.add(row)


class ErrorMonitorMiddleware(BaseHTTPMiddleware):
    """모든 HTTP 요청을 감시하여 에러와 느린 요청을 DB에 자동 기록."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 노이즈 경로 건너뜀
        path = request.url.path
        if any(path.startswith(pfx) for pfx in _SKIP_PREFIXES):
            return await call_next(request)

        t0 = time.time()
        method = request.method
        request_id = request.headers.get("X-Request-ID", "")
        client_ip = (request.client.host if request.client else "") or ""

        # ── 요청 실행 ──────────────────────────────────────────────────────────
        exc_tb: Optional[str] = None
        exc_type: Optional[str] = None
        response: Optional[Response] = None

        try:
            response = await call_next(request)
        except Exception as exc:
            # 미처리 예외 — traceback 캡처 후 re-raise
            exc_tb = tb_module.format_exc()
            exc_type = type(exc).__name__
            duration_ms = int((time.time() - t0) * 1000)
            _spawn_bg_task(_write_error_log(
                level="CRITICAL",
                method=method, path=path, status_code=500,
                duration_ms=duration_ms,
                error_type=exc_type,
                error_message=str(exc)[:500],
                traceback_str=exc_tb,
                request_id=request_id, client_ip=client_ip,
            ))
            # Windows 알림 팝업
            try:
                from ..logging_setup import alert_on_critical
                alert_on_critical("CRITICAL", path, exc_type, str(exc)[:200])
            except Exception:
                pass
            raise

        # ── 응답 분석 ──────────────────────────────────────────────────────────
        duration_ms = int((time.time() - t0) * 1000)
        status = response.status_code

        if status >= 500:
            # HTTP 에러 응답 (예외는 위에서 처리됨, 여기는 route가 반환한 500)
            _spawn_bg_task(_write_error_log(
                level="ERROR",
                method=method, path=path, status_code=status,
                duration_ms=duration_ms,
                error_type=f"HTTP_{status}",
                error_message=f"{method} {path} → {status} ({duration_ms}ms)",
                request_id=request_id, client_ip=client_ip,
            ))
        elif duration_ms >= _CRIT_MS:
            _spawn_bg_task(_write_error_log(
                level="CRITICAL",
                method=method, path=path, status_code=status,
                duration_ms=duration_ms,
                error_type="SLOW_REQUEST",
                error_message=f"{method} {path} — {duration_ms}ms (임계값 {_CRIT_MS}ms 초과)",
                request_id=request_id, client_ip=client_ip,
            ))
            try:
                from ..logging_setup import alert_on_critical
                alert_on_critical("CRITICAL", path, "SLOW_REQUEST",
                                  f"{method} {path} — {duration_ms//1000}초 초과")
            except Exception:
                pass
        elif duration_ms >= _SLOW_MS:
            _spawn_bg_task(_write_error_log(
                level="SLOW",
                method=method, path=path, status_code=status,
                duration_ms=duration_ms,
                error_type="SLOW_REQUEST",
                error_message=f"{method} {path} — {duration_ms}ms",
                request_id=request_id, client_ip=client_ip,
            ))

        return response
