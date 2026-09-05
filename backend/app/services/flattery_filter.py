"""EPIC G-4.5: 아첨금지 Layer A — 정규식·키워드 사전 필터.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-4.5 — check_flattery() 결정론적 키워드 필터
# Reason: ORDERS_COUNSELING.md G-4.5 — LLM Judge 전 비용 0·지연 0 사전 필터 (Layer A)
# Related: data/policy/flattery_patterns.yaml (NEW), api/chat.py (MODIFY)
# Status: COMPLETED
# =============================================================================
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FlatteryFilterResult(BaseModel):
    violated: bool
    matched_patterns: list[str] = []   # 어떤 패턴이 잡혔는지 (디버깅용)
    category: Optional[str] = None     # flattery / excessive_praise / childish_friendliness


# 패턴 사전 경로 — config.root_dir 기준
_YAML_PATH = Path(__file__).resolve().parents[3] / "data" / "policy" / "flattery_patterns.yaml"


_compiled_cache: dict[str, tuple] = {}
_compiled_cache_mtime: float = 0.0

def _load_compiled() -> dict[str, dict[str, list[tuple[str, re.Pattern]]]]:
    """YAML 패턴을 로드하여 컴파일된 정규식 딕셔너리로 반환.

    구조: { lang: { category: [(raw_pat, compiled), ...] } }
    파일 수정 시간(mtime) 기반 캐시로 무효화.
    """
    global _compiled_cache, _compiled_cache_mtime
    try:
        mtime = _YAML_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _compiled_cache and _compiled_cache_mtime == mtime:
        return _compiled_cache
    if not _YAML_PATH.exists():
        logger.warning("flattery_patterns.yaml not found at %s", _YAML_PATH)
        return {}

    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8")) or {}
    compiled: dict[str, dict[str, list[tuple[str, re.Pattern]]]] = {}

    for lang, categories in raw.items():
        compiled[lang] = {}
        for category, patterns in (categories or {}).items():
            compiled_patterns = []
            for pat in (patterns or []):
                try:
                    compiled_patterns.append((pat, re.compile(pat, re.IGNORECASE | re.DOTALL)))
                except re.error as e:
                    logger.error("flattery_filter: invalid regex '%s' (%s) — skipped", pat, e)
            compiled[lang][category] = compiled_patterns

    _compiled_cache = compiled
    _compiled_cache_mtime = mtime
    return compiled


def check_flattery(text: str, target_lang: str = "ko") -> FlatteryFilterResult:
    """LLM 답변 텍스트에서 아첨 패턴을 결정론적으로 검출한다.

    언어별 패턴 사전을 우선 검사하고, 한국어 패턴은 언어 무관하게 추가 검사한다.
    (한국어 아첨 표현은 ko 모드 외에도 섞일 수 있음)
    """
    compiled = _load_compiled()
    matched: list[str] = []
    first_category: Optional[str] = None

    # 검사할 언어 목록 — 요청 언어 우선, ko 패턴은 항상 보조 검사
    langs_to_check = [target_lang]
    if target_lang != "ko":
        langs_to_check.append("ko")

    for lang in langs_to_check:
        lang_patterns = compiled.get(lang, {})
        for category, patterns in lang_patterns.items():
            for raw_pat, compiled_pat in patterns:
                if compiled_pat.search(text):
                    matched.append(f"{lang}/{category}/{raw_pat}")
                    if first_category is None:
                        first_category = category

    if matched:
        return FlatteryFilterResult(
            violated=True,
            matched_patterns=matched,
            category=first_category,
        )
    return FlatteryFilterResult(violated=False)
