"""Prompt service - 운영자가 편집 가능한 시스템 프롬프트.

current() 가 항상 1개의 활성 프롬프트를 반환. 없으면 코드 기본값 사용.
"""
from __future__ import annotations
import time as _time
from typing import Optional

from sqlalchemy.orm import Session

from ..db import get_session
from ..models.orm import PromptTemplate
from ..prompts.system import GOSPEL_SYSTEM_PROMPT as DEFAULT_PROMPT

# 60초 TTL 인-메모리 캐시 — 요청마다 DB 조회 방지
_cache_text: str | None = None
_cache_expires: float = 0.0


def _invalidate_cache() -> None:
    global _cache_text, _cache_expires
    _cache_text = None
    _cache_expires = 0.0


def current_text() -> str:
    """현재 활성 프롬프트 텍스트. DB에 없으면 코드 기본값. 60초 TTL 캐시 적용."""
    global _cache_text, _cache_expires
    now = _time.monotonic()
    if _cache_text is not None and now < _cache_expires:
        return _cache_text
    try:
        with get_session() as s:
            row = s.query(PromptTemplate).filter(PromptTemplate.active == True).order_by(
                PromptTemplate.updated_at.desc()
            ).first()
            result = row.content if row else DEFAULT_PROMPT
    except Exception:
        result = DEFAULT_PROMPT
    _cache_text = result
    _cache_expires = now + 60.0
    return result


def current_detail() -> dict:
    """UI 표시용 — 현재 프롬프트 + 메타."""
    try:
        with get_session() as s:
            row = s.query(PromptTemplate).filter(PromptTemplate.active == True).order_by(
                PromptTemplate.updated_at.desc()
            ).first()
            if row:
                return {
                    "template_id": row.template_id,
                    "name": row.name,
                    "content": row.content,
                    "note": row.note,
                    "updated_by": row.updated_by,
                    "updated_at": row.updated_at.isoformat(),
                    "is_custom": True,
                }
    except Exception:
        pass
    return {
        "template_id": None,
        "name": "default (코드 기본값)",
        "content": DEFAULT_PROMPT,
        "note": "운영자가 편집한 적이 없습니다. 첫 저장 시 DB로 옮겨갑니다.",
        "updated_by": "system",
        "updated_at": None,
        "is_custom": False,
    }


def save(content: str, *, name: str = "gospel_default", note: Optional[str] = None, who: str = "admin") -> dict:
    """현재 활성을 비활성화하고 새 활성으로 저장 (이력 보존)."""
    _invalidate_cache()
    with get_session() as s:
        # 모두 비활성
        s.query(PromptTemplate).filter(PromptTemplate.active == True).update(
            {"active": False}
        )
        # 새 활성 추가
        new = PromptTemplate(
            name=name, content=content, active=True, note=note, updated_by=who,
        )
        s.add(new)
        s.flush()
        return {
            "template_id": new.template_id,
            "name": new.name,
            "content": new.content,
            "updated_at": new.updated_at.isoformat(),
        }


def reset_to_default(who: str = "admin") -> dict:
    """모든 커스텀 비활성화 → 코드 기본값으로 돌아감."""
    _invalidate_cache()
    with get_session() as s:
        s.query(PromptTemplate).filter(PromptTemplate.active == True).update(
            {"active": False}
        )
    return {"ok": True, "now_using": "code_default"}


def history(limit: int = 10) -> list[dict]:
    with get_session() as s:
        rows = s.query(PromptTemplate).order_by(PromptTemplate.updated_at.desc()).limit(limit).all()
        return [{
            "template_id": r.template_id,
            "name": r.name,
            "content": r.content,
            "active": r.active,
            "note": r.note,
            "updated_by": r.updated_by,
            "updated_at": r.updated_at.isoformat(),
        } for r in rows]
