"""简易内存限流（MVP）。

生产建议用 Redis + 滑动窗口（多实例共享计数）。这里用进程内 deque，
足够单实例 MVP 与 mock 测试（测试时 settings.enable_rate_limit=False 关闭）。
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def _sliding_window(key: str, window: float, limit: int, detail: str) -> None:
    """滑动窗口限流：key 在 window 秒内的请求数超过 limit 则抛 429。"""
    if not settings.enable_rate_limit:
        return
    now = time.monotonic()
    dq = _hits[key]
    while dq and dq[0] <= now - window:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status_code=429, detail=detail)
    dq.append(now)


async def rate_limit_sync(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    _sliding_window(f"sync:{ip}", 60.0, settings.sync_rate_limit_per_minute,
                    "同步过于频繁，请稍后再试")


def rate_limit_generate(user_key: str) -> None:
    _sliding_window(f"gen:{user_key}", 60.0, settings.generate_rate_limit_per_minute,
                    "生成过于频繁，请稍后再试")


def rate_limit_login(ip: str) -> None:
    _sliding_window(f"login:{ip}", 60.0, settings.login_rate_limit_per_minute,
                    "登录尝试过于频繁，请稍后再试")
