"""번역 용어집(Translation Glossary) 관리 — JSON 단일 진실공급원.

KO → ZH(简体) + EN 매핑을 보관. 채팅 파이프라인과 RAG 문서 번역 프롬프트에
강제 주입되어 신학 용어 번역 일관성을 보장한다. 관리 UI(Streamlit)에서 직접
읽기/쓰기하므로 외부 API 의존성이 없다.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parent / "data" / "glossary.json"
_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_mtime: float = 0.0


def _load_raw() -> dict:
    global _cache, _cache_mtime
    if not _DATA.exists():
        return {"version": "v2", "terms": []}
    mtime = _DATA.stat().st_mtime
    if _cache is not None and mtime == _cache_mtime:
        return _cache
    with _lock:
        # double-checked: 다른 스레드가 갱신했을 수 있음
        mtime2 = _DATA.stat().st_mtime
        if _cache is None or mtime2 != _cache_mtime:
            data = json.loads(_DATA.read_text(encoding="utf-8"))
            _cache = data
            _cache_mtime = mtime2
    return _cache


def get_terms() -> list[dict]:
    return _load_raw().get("terms", [])


def term_count() -> int:
    return len(get_terms())


def get_term(ko: str) -> Optional[dict]:
    for t in get_terms():
        if t.get("ko") == ko:
            return t
    return None


def build_glossary_block(query: str, target_lang: str = "zh", max_terms: int = 60) -> str:
    """쿼리에 등장하는 용어만 추출해 번역 지침 블록을 생성한다 (zh/en 지원).

    쿼리 매칭 용어가 적으면 '코어' 용어로 보강한다.
    target_lang 가 'zh'/'en' 이 아니면 빈 문자열(주입 안 함).
    """
    if target_lang not in ("zh", "en"):
        return ""
    terms = get_terms()
    present = [t for t in terms if t.get("ko") and t["ko"] in query]
    if len(present) < 8:
        core = [t for t in terms if t.get("category") in ("doctrine", "person")][:15]
        seen = {id(t) for t in present}
        for t in core:
            if id(t) not in seen:
                present.append(t)
                seen.add(id(t))
    present = present[:max_terms]
    lines = [
        f"- {t['ko']} → {t.get(target_lang, '')}"
        for t in present
        if t.get(target_lang)
    ]
    if not lines:
        return ""
    header = "术语对照" if target_lang == "zh" else "Terminology reference"
    return f"[번역 용어집 / {header}]\n" + "\n".join(lines)


def save_terms(terms: list[dict]) -> None:
    """용어 목록을 JSON 파일에 저장(관리 UI 용)."""
    global _cache, _cache_mtime
    raw = _load_raw()
    raw["terms"] = terms
    with _lock:
        _DATA.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _cache = raw
        _cache_mtime = _DATA.stat().st_mtime
