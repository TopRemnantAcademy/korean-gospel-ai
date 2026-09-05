"""설정/로깅 단위 테스트 (경량 — 무거운 ML 의존성 불필요).

실행:
    ./venv/Scripts/python.exe -m pytest tests/test_config.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.app.db as dbmod
from backend.app.config import settings
from backend.app.logging_setup import scrub_secrets


def test_settings_loaded():
    """중앙 설정 싱글턴이 로드되고 provider 가 유효한 값."""
    assert settings is not None
    assert settings.llm_provider in {
        "gemini", "openai", "claude", "ollama", "deepseek", "tencent"
    }


def test_db_url_resolves_sqlite_when_no_database_url(monkeypatch):
    """DATABASE_URL 미설정 시 SQLite 파일 URL 로 해석 (Postgres 전환 분기 검증)."""
    monkeypatch.setattr(settings, "database_url", None)
    url = dbmod._resolve_db_url()
    assert url.startswith("sqlite:///")
    assert ".gospel.db" in url or "gospel.db" in url


def test_scrub_secrets_masks_api_key_and_token():
    """P10-7: API 키/토큰이 로그에 기록되기 전 마스킹되는지."""
    sample = (
        "call failed api_key=sk-1234567890abcdef token=abc123secret "
        "db=postgresql://user:supersecret@host/db"
    )
    out = scrub_secrets(sample)
    assert "sk-1234567890abcdef" not in out
    assert "supersecret" not in out
    assert "[REDACTED]" in out


def test_scrub_secrets_passthrough_safe_text():
    """시크릿이 없는 일반 텍스트는 그대로."""
    assert scrub_secrets("normal log line") == "normal log line"
