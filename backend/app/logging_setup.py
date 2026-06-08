"""로그 설정 — 파일 로테이션 + 콘솔 + Windows 알람 알리미.

사용:
    from .logging_setup import setup_logging, notify_critical
    setup_logging()          # 앱 시작 시 1회
    notify_critical("msg")   # CRITICAL 에러 시 Windows 알림 팝업
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent   # korean-gospel-ai/
LOG_DIR  = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "backend.log"
ERR_FILE = LOG_DIR / "errors.log"       # ERROR 이상만 별도 파일


def setup_logging(log_level: str = "INFO") -> None:
    """로테이팅 파일 핸들러 + 콘솔 핸들러 설치."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── 전체 로그 (INFO 이상, 10MB × 5개 로테이션)
    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)

    # ── 에러만 별도 파일 (ERROR 이상, 5MB × 3개)
    eh = RotatingFileHandler(
        ERR_FILE, maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)

    # ── 콘솔
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)

    # 중복 핸들러 방지
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(fh)
        root.addHandler(eh)
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
               for h in root.handlers):
        root.addHandler(ch)

    logging.getLogger("gospel-api").info(
        "Logging initialised → %s  (errors → %s)", LOG_FILE, ERR_FILE
    )


# ── Windows 알림 ─────────────────────────────────────────────────────────────
_notified_recently: dict[str, float] = {}   # 중복 팝업 방지 (60초 쿨다운)

def notify_critical(title: str, message: str, cooldown_sec: int = 60) -> None:
    """Windows 토스트 알림 팝업. 60초 이내 같은 제목은 무시."""
    import time
    now = time.time()
    if now - _notified_recently.get(title, 0) < cooldown_sec:
        return
    _notified_recently[title] = now

    try:
        from plyer import notification
        notification.notify(
            title=f"🚨 Gospel API — {title}",
            message=message[:200],
            app_name="Korean Gospel AI",
            timeout=8,
        )
    except Exception:
        pass   # 알림 실패 시 서비스 중단 없음


# ── 에러 모니터링 미들웨어용 훅 ─────────────────────────────────────────────
def alert_on_critical(level: str, path: str, error_type: str, message: str) -> None:
    """ErrorMonitorMiddleware 에서 CRITICAL 발생 시 호출."""
    if level == "CRITICAL":
        notify_critical(
            title=f"CRITICAL: {error_type}",
            message=f"{path}\n{message[:150]}",
        )
    logging.getLogger("gospel-api.alert").error(
        "[%s] %s %s — %s", level, path, error_type, message[:200]
    )
