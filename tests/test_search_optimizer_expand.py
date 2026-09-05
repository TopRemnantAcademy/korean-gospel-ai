"""search_optimizer — LLM 쿼리 확장(async) 단위 테스트.

실행:
    ./venv/Scripts/python.exe -m pytest tests/test_search_optimizer_expand.py -q

검증 범위
--------
- `_parse_expansion` : JSON 배열 파싱 / 마크다운 펜스 제거 / 원본·중복 제외 / 상한(_EXPANSION_MAX).
- `_expand_query_async` : chat_with_fallback 모킹 → 정상 확장 / 타임아웃 흡수 / 예외 흡수(fail-open).
- `analyze_query_async` : search_expand_enabled 스위치가 꺼지면 LLM 확장 미주입, 켜지면 주입.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.services.search_optimizer import (  # noqa: E402
    _EXPANSION_MAX,
    _expand_query_async,
    _expansion_cache,
    _parse_expansion,
    analyze_query_async,
)


@pytest.fixture(autouse=True)
def _clear_expansion_cache():
    """각 테스트는 독립적인 캐시에서 시작(쿼리별 캐시串扰 방지)."""
    _expansion_cache.clear()
    yield
    _expansion_cache.clear()


# ── _parse_expansion ──────────────────────────────────────────────
def test_parse_expansion_plain_json():
    raw = '["예수님 구원", "구원의 의미"]'
    out = _parse_expansion(raw, "구원이란")
    assert out == ["예수님 구원", "구원의 의미"]


def test_parse_expansion_strips_fence():
    raw = '```json\n["믿음", "회개"]\n```'
    out = _parse_expansion(raw, "q")
    assert out == ["믿음", "회개"]


def test_parse_expansion_removes_original_and_duplicates():
    raw = '["구원", "믿음", "구원"]'
    out = _parse_expansion(raw, "구원")
    assert out == ["믿음"]


def test_parse_expansion_empty_and_garbage():
    assert _parse_expansion("", "q") == []
    assert _parse_expansion("not json", "q") == []
    assert _parse_expansion("{}", "q") == []


def test_parse_expansion_respects_max():
    many = "[" + ",".join(f'"x{i}"' for i in range(_EXPANSION_MAX + 5)) + "]"
    out = _parse_expansion(many, "q")
    assert len(out) == _EXPANSION_MAX


# ── _expand_query_async (chat_with_fallback 모킹) ─────────────────
def _fake_llm_response(text: str):
    """chat_with_fallback 가 돌려주는 (LLMResponse, BaseLLM, list) 형태 모킹."""
    resp = mock.MagicMock()
    resp.text = text
    return (resp, mock.MagicMock(), ["nvidia"])


def test_expand_query_async_success():
    payload = '["예수님 구원", "구원의 의미"]'
    with mock.patch(
        "app.services.llm.fallback.chat_with_fallback",
        new=mock.AsyncMock(return_value=_fake_llm_response(payload)),
    ), mock.patch("app.services.llm.base.Message"):
        out = asyncio.run(_expand_query_async("구원이란_unique_a"))
    assert "예수님 구원" in out
    assert "구원의 의미" in out


def test_expand_query_async_timeout_fail_open():
    with mock.patch(
        "app.services.llm.fallback.chat_with_fallback",
        new=mock.AsyncMock(side_effect=asyncio.TimeoutError),
    ), mock.patch("app.services.llm.base.Message"):
        out = asyncio.run(_expand_query_async("구원이란_unique_b"))
    assert out == []  # 타임아웃은 흡수 → 빈 리스트


def test_expand_query_async_exception_fail_open():
    with mock.patch(
        "app.services.llm.fallback.chat_with_fallback",
        new=mock.AsyncMock(side_effect=RuntimeError("boom")),
    ), mock.patch("app.services.llm.base.Message"):
        out = asyncio.run(_expand_query_async("구원이란_unique_c"))
    assert out == []  # 예외도 흡수 → 빈 리스트


# ── analyze_query_async (스위치 동작) ────────────────────────────
@pytest.fixture
def settings_toggle():
    """search_expand_enabled 를 임시 토글 후 복구."""
    from app.config import settings

    original = settings.search_expand_enabled
    yield settings
    settings.search_expand_enabled = original


def test_analyze_query_async_expand_disabled_by_default(settings_toggle):
    """기본(스위치 off)이면 짧은 쿼리에도 LLM 확장 미주입(원본만)."""
    settings_toggle.search_expand_enabled = False
    with mock.patch(
        "app.services.llm.fallback.chat_with_fallback",
        new=mock.AsyncMock(return_value=_fake_llm_response('["확장A"]')),
    ), mock.patch("app.services.llm.base.Message"):
        qa = asyncio.run(analyze_query_async("구원_unique_d"))
    assert qa.original == "구원_unique_d"
    # 확장이 주입되지 않았으므로 원본만
    assert qa.expanded_queries == ["구원_unique_d"]


def test_analyze_query_async_expand_enabled_injects(settings_toggle):
    """스위치 on 이면 LLM 확장이 주입된다."""
    settings_toggle.search_expand_enabled = True
    with mock.patch(
        "app.services.llm.fallback.chat_with_fallback",
        new=mock.AsyncMock(return_value=_fake_llm_response('["예수님 구원"]')),
    ), mock.patch("app.services.llm.base.Message"):
        qa = asyncio.run(analyze_query_async("구원_unique_e"))
    assert "예수님 구원" in qa.expanded_queries
    assert "구원_unique_e" in qa.expanded_queries  # 원본은 항상 포함
