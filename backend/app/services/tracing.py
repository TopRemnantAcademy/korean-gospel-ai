"""관측(트레이싱) — Langfuse 우선, 비활성 시 셀프호스팅 구조화 로그로 폴백.

Langfuse 가 활성(LANGFUSE_ENABLED=true + 키)이면 Langfuse 를 사용하고,
비활성이면 외부 SaaS 없이도 동일한 인터페이스(trace/event/generation/score)로
`logs/traces.jsonl` 에 구조화 JSON 을 남긴다(기업 수준 셀프 관측).

- 시크릿 마스킹: logging_setup.scrub_secrets 재사용 (API 키/토큰/비밀번호 유출 차단)
- 로테이션: RotatingFileHandler (10MB × 5)
- 인터페이스는 Langfuse 와 동일 → 호출부(chat.py/chat_pipeline.py) 변경 없음.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# 셀프호스팅 트레이스 (Langfuse 미사용 시 폴백) — 구조화 JSONL 로그
# ──────────────────────────────────────────────────────────────────────────
_trace_logger: logging.Logger | None = None
_trace_logger_lock = threading.Lock()


def _get_trace_logger() -> logging.Logger:
    """셀프호스팅 트레이스 전용 로거 (logs/traces.jsonl, 메인 로그와 분리)."""
    global _trace_logger
    if _trace_logger is not None:
        return _trace_logger
    with _trace_logger_lock:
        if _trace_logger is not None:
            return _trace_logger

        lg = logging.getLogger("gospel-api.trace")
        lg.setLevel(logging.INFO)
        lg.propagate = False  # backend.log 와 분리(트레이스 노이즈 방지)
        if not lg.handlers:
            from logging.handlers import RotatingFileHandler

            # logs/ 디렉터리 결정 (logging_setup 과 동일 규칙: 프로젝트 루트/logs)
            root = Path(__file__).resolve().parent.parent.parent.parent
            log_dir = root / "logs"
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError:
                pass
            fh = RotatingFileHandler(
                log_dir / "traces.jsonl",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(logging.Formatter("%(message)s"))
            lg.addHandler(fh)
        _trace_logger = lg
        return lg


def _scrub(value: Any) -> Any:
    """트레이스에 기록 전 시크릿 마스킹 (문자열만 처리, dict/list 는 재귀)."""
    try:
        from ..logging_setup import scrub_secrets
    except Exception:
        return value
    if isinstance(value, str):
        return scrub_secrets(value)
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


def _emit(type_: str, trace_id: str, trace_name: str, **payload: Any) -> None:
    rec = {
        "ts": round(time.time(), 3),
        "trace_id": trace_id,
        "trace_name": trace_name,
        "type": type_,
        **payload,
    }
    try:
        line = json.dumps(_scrub(rec), ensure_ascii=False, default=str)
        _get_trace_logger().info(line)
    except Exception as _e:  # 관측 실패는 비즈니스 로직에 영향 없어야 함
        logger.debug("trace emit 실패: %s", _e)


class _LocalGeneration:
    """셀프호스팅 generation span."""

    __slots__ = ("_trace_id", "_trace_name", "_name", "_model", "_start")

    def __init__(self, trace_id: str, trace_name: str, name: str, model: str):
        self._trace_id = trace_id
        self._trace_name = trace_name
        self._name = name
        self._model = model or ""
        self._start = time.perf_counter()

    def update(self, model: str | None = None, **_: Any) -> None:
        if model:
            self._model = model

    def end(self, output: Any = None, usage: Any = None) -> None:
        _emit(
            "generation",
            self._trace_id,
            self._trace_name,
            name=self._name,
            model=self._model,
            output=output,
            usage=usage,
            latency_ms=round((time.perf_counter() - self._start) * 1000, 2),
        )


class _LocalTrace:
    """셀프호스팅 trace (Langfuse Trace 와 동일 인터페이스)."""

    __slots__ = ("_id", "_name", "_start")

    def __init__(self, trace_id: str, name: str):
        self._id = trace_id
        self._name = name
        self._start = time.perf_counter()

    @property
    def id(self) -> str:
        return self._id

    def event(self, name: str, input: Any = None, output: Any = None) -> None:
        _emit("event", self._id, self._name, name=name, input=input, output=output)

    def update(
        self,
        output: Any = None,
        tags: Any = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        _emit(
            "update",
            self._id,
            self._name,
            output=output,
            tags=tags,
            level=level,
            status_message=status_message,
        )

    def generation(self, name: str, model: str = "", input: Any = None) -> "_LocalGeneration":
        return _LocalGeneration(self._id, self._name, name, model)


class _LocalTraceClient:
    """셀프호스팅 클라이언트 — Langfuse Client 와 동일 최소 인터페이스."""

    def trace(self, name: str, input: Any = None, user_id: str | None = None, **_: Any) -> "_LocalTrace":
        tid = uuid.uuid4().hex
        tr = _LocalTrace(tid, name)
        _emit("trace_start", tid, name, input=input, user_id=user_id)
        return tr

    def generation(self, name: str, model: str = "", input: Any = None) -> "_LocalGeneration":
        tid = uuid.uuid4().hex
        return _LocalGeneration(tid, name, name, model)

    def score(self, trace_id: str, name: str, value: float, comment: str = "") -> bool:
        _emit("score", trace_id or "", "", name=name, value=value, comment=comment)
        return True


_local_client = _LocalTraceClient()


def get_client():
    """Langfuse 클라이언트 반환. 비활성/사용불가 시 셀프호스팅 로컬 클라이언트 반환.

    (기존엔 Langfuse 비활성 시 None 을 반환해 모든 trace.event() 관측이
     조용히 폐기됐다. 이제는 로컬 JSONL 로 폴백해 관측이 항상 동작한다.)
    """
    try:
        from ..connections import connections
        client = connections.langfuse()
        if client is not None:
            return client
    except Exception as e:
        logger.warning("[tracing] Langfuse client unavailable; self-hosted fallback: %s", e)
    return _local_client


# ----- Decorator -----
def observe(name: str | None = None, as_type: str = "span"):
    """Langfuse 활성 시 함수를 trace에 기록. 비활성 시 로컬 JSONL로 기록."""
    def deco(fn: Callable[..., Any]):
        @wraps(fn)
        async def aw(*args, **kwargs):
            client = get_client()
            trace = client.trace(name=name or fn.__name__)
            try:
                result = await fn(*args, **kwargs)
                trace.update(output=_safe_repr(result))
                return result
            except Exception as e:
                trace.update(level="ERROR", status_message=str(e))
                raise

        @wraps(fn)
        def sw(*args, **kwargs):
            client = get_client()
            trace = client.trace(name=name or fn.__name__)
            try:
                result = fn(*args, **kwargs)
                trace.update(output=_safe_repr(result))
                return result
            except Exception as e:
                trace.update(level="ERROR", status_message=str(e))
                raise

        import asyncio
        return aw if asyncio.iscoroutinefunction(fn) else sw
    return deco


@contextmanager
def trace_generation(name: str, *, model: str = "", input: Any = None):
    client = get_client()
    gen = client.generation(name=name, model=model, input=_safe_repr(input))
    try:
        yield gen
    finally:
        pass


def record_user_feedback(trace_id: str | None, value: int, *, comment: str = "") -> bool:
    """trace에 user_feedback score 기록. value: +1 / -1."""
    if not trace_id or value not in (1, -1):
        return False
    client = get_client()
    try:
        return bool(client.score(
            trace_id=trace_id,
            name="user_feedback",
            value=float(value),
            comment=comment or ("helpful" if value > 0 else "not_helpful"),
        ))
    except Exception:
        return False


def _safe_repr(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)[:8000]
    except Exception:
        return str(obj)[:8000]
