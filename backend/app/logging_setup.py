"""로그 설정 — 파일 로테이션 + 콘솔 + Windows 알람 알리미.

사용:
    from .logging_setup import setup_logging, notify_critical
    setup_logging()          # 앱 시작 시 1회
    notify_critical("msg")   # CRITICAL 에러 시 Windows 알림 팝업
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent   # korean-gospel-ai/
LOG_DIR  = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "backend.log"
ERR_FILE = LOG_DIR / "errors.log"       # ERROR 이상만 별도 파일


# ── P10-7 (P2 보안): 로그 시크릿 마스킹 ──────────────────────────────────────
# API 키 / 토큰 / 비밀번호 / DB URL 비밀번호 등이 로그에 기록되는 것을 차단.
_SECRET_RE = re.compile(
    r"""(?ix)
    (?:
        (?P<key>api[_-]?key|apikey|secret|token|password|passwd|access[_-]?key
         |client[_-]?secret|authorization|bearer)
        (?:\s*[:=]\s*|\s+)(?:bearer\s+)?['\"]?
        (?P<val>[A-Za-z0-9_\-\.]{6,})
      |
        (?P<bare>(?:sk|pk|AKIA|ya29|AIza|eyJ)[A-Za-z0-9_\-\.]{10,})
      |
        (?P<url>postgres(?:ql)?://[^:]+:[^@]+@)
    )
    """
)


# 최적화(성능): 시크릿 마스킹은 핸들러당(3개) 매 로그 레코드마다 실행된다.
# 대다수 로그는 무해하므로, 지표 키워드가 하나도 없으면 고비용 정규식을
# 건너뛰고 원문을 그대로 반환한다. (키워드가 없는 라인에는 실제 시크릿이
# 동반되지 않음 — api_key/secret/token/bearer/postgres:// 등은 항상 지표와 함께 나타남)
_SECRET_KEYWORDS = (
    "api_key", "apikey", "secret", "token", "password", "passwd",
    "authorization", "bearer", "client_secret", "access_key",
    "sk-", "pk-", "akia", "ya29", "aiza", "eyj",
    "postgres://", "postgresql://",
)


def _looks_like_secret(text: str) -> bool:
    """저비용 하위 필터 — 시크릿 가능성이 있는 라인만 정규식 검사."""
    low = text.lower()
    return any(k in low for k in _SECRET_KEYWORDS)


def scrub_secrets(text: str | None) -> str:
    """로그/에러 메시지/트레이스백에서 시크릿 패턴을 [REDACTED] 로 치환.

    최적화: 무해한 로그는 _looks_like_secret() 게이트로 정규식 실행을 건너뛴다.

    보안 수정: 이전 콜백은 매칭 본문(group(0))에서 키 이름만 추출해 `[REDACTED]` 를
    붙였으나, 실제 시크릿(특히 `Authorization: Bearer <JWT>` 형태에서 JWT, 또는
    `eyJ...`/`sk-...` 형태의 裸 토큰)은 매칭에서 누락되어 그대로 노출되었다.
    이제 키 형식은 `key=[REDACTED]`, 그 외(裸 토큰/DB URL)는 전체 `[REDACTED]` 로 치환된다.
    """
    if not text:
        return text or ""
    if not _looks_like_secret(text):
        return text

    def _redact(m: "re.Match") -> str:
        if m.group("key"):
            return f"{m.group('key')}=[REDACTED]"
        return "[REDACTED]"

    return _SECRET_RE.sub(_redact, text)


class RedactingFilter(logging.Filter):
    """모든 레코드의 message / args 에 시크릿 마스킹 적용."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_secrets(record.msg)
        if record.args:
            try:
                record.args = tuple(
                    scrub_secrets(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
            except Exception:
                pass
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """로테이팅 파일 핸들러 + 콘솔 핸들러 설치 (시크릿 마스킹 포함)."""
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

    # 시크릿 마스킹 필터: 핸들러마다(3개) 적용하면 레코드당 정규식을 3번 실행하므로,
    # 로거 레벨에 1개만 부착해 레코드당 1번만 실행되도록 한다 (마스킹 결과는 동일).
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())

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


# ── Windows 알림 ────────────────────────────────────────────────────────────────
_notified_recently: dict[str, float] = {}   # 중복 팝업 방지 (60초 쿨다운)
_notified_lock = threading.Lock()           # 스레드 ASGI 워커 환경에서 딕셔너리 동시 변경 방지
_NOTIFY_MAX_ENTRIES = 500  # [FIX #24] 항목 최대 개수 제한

def notify_critical(title: str, message: str, cooldown_sec: int = 60) -> None:
    """CRITICAL 알림. 데스크톱(plyer) + 선택 웹훅 + 로그 3중 전송.

    P10-5 (P2): 이전엔 plyer(Windows 데스크톱 전용)만 시도 → 컨테이너/서버에서는
    import 실패로 알림이 무조건 유실됨. 이제:
      - 웹훅(ALERT_WEBHOOK_URL) 이 설정되어 있으면 백그라운드 POST
      - plyer 는 Windows 데스크톱에서만 시도 (그 외 환경은 스킵)
      - 항상 errors.log 에 기록 (alert_on_critical 경유)
    """
    import time
    now = time.time()
    # 딕셔너리 읽기/할당/순회/pop 이 한 번에 일어나도록 락으로 보호
    # (락 없으면 멀티워커/스레드 환경에서 "dictionary changed size during iteration" 발생)
    with _notified_lock:
        if now - _notified_recently.get(title, 0) < cooldown_sec:
            return
        _notified_recently[title] = now

        # [FIX #24] 만료된 항목 정리 및 사이즈 제한
        expired = [k for k, v in _notified_recently.items() if now - v > max(cooldown_sec * 10, 3600)]
        for k in expired:
            _notified_recently.pop(k, None)
        if len(_notified_recently) > _NOTIFY_MAX_ENTRIES:
            # 가장 오래된 항목부터 제거
            oldest = sorted(_notified_recently, key=_notified_recently.get)[:50]
            for k in oldest:
                _notified_recently.pop(k, None)

    safe_title = scrub_secrets(title)
    safe_msg = scrub_secrets(message)[:200]

    # 1) 선택 웹훅 (Slack/Discord/자체 엔드포인트)
    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook:
        try:
            import threading

            def _post():
                try:
                    import httpx
                    httpx.post(
                        webhook,
                        json={"text": f"🚨 Gospel API — {safe_title}\n{safe_msg}"},
                        timeout=5.0,
                    )
                except Exception:
                    pass

            threading.Thread(target=_post, daemon=True).start()
        except Exception:
            pass

    # 2) 데스크톱 토스트 (Windows 데스크톱에서만)
    if sys.platform.startswith("win"):
        try:
            from plyer import notification
            notification.notify(
                title=f"🚨 Gospel API — {safe_title}",
                message=safe_msg,
                app_name="",
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
