"""Langfuse 통합 - @observe 데코레이터로 자동 추적.
LANGFUSE_ENABLED=false 일 때는 noop.
"""
from __future__ import annotations
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional


def get_client():
    """Langfuse 클라이언트 반환. connections.py 레지스트리에서 가져옴."""
    try:
        from ..connections import connections
        return connections.langfuse()
    except Exception:
        return None


# ----- Decorator -----
def observe(name: str | None = None, as_type: str = "span"):
    """Langfuse 활성화 시 함수를 trace에 기록. 비활성 시 그냥 통과."""
    def deco(fn: Callable[..., Any]):
        @wraps(fn)
        async def aw(*args, **kwargs):
            client = get_client()
            if client is None:
                return await fn(*args, **kwargs)
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
            if client is None:
                return fn(*args, **kwargs)
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
    if client is None:
        yield None
        return
    gen = client.generation(name=name, model=model, input=_safe_repr(input))
    try:
        yield gen
    finally:
        # 호출자가 .end()/update()로 마무리 권장
        pass


def record_user_feedback(trace_id: str | None, value: int, *, comment: str = "") -> bool:
    """Langfuse trace에 user_feedback score 기록. value: +1 / -1."""
    if not trace_id or value not in (1, -1):
        return False
    client = get_client()
    if client is None:
        return False
    try:
        client.score(
            trace_id=trace_id,
            name="user_feedback",
            value=float(value),
            comment=comment or ("helpful" if value > 0 else "not_helpful"),
        )
        return True
    except Exception:
        return False


def _safe_repr(obj: Any) -> str:
    try:
        import json
        return json.dumps(obj, ensure_ascii=False, default=str)[:8000]
    except Exception:
        return str(obj)[:8000]
