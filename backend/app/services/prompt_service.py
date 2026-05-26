"""Prompt service - 운영자가 편집 가능한 시스템 프롬프트.

current() 가 항상 1개의 활성 프롬프트를 반환. 없으면 코드 기본값 사용.
"""
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import Session

from ..db import get_session
from ..models.orm import PromptTemplate
from ..prompts.system import GOSPEL_SYSTEM_PROMPT as DEFAULT_PROMPT


def current_text() -> str:
    """현재 활성 프롬프트 텍스트. DB에 없으면 코드 기본값."""
    try:
        with get_session() as s:
            row = s.query(PromptTemplate).filter(PromptTemplate.active == True).order_by(
                PromptTemplate.updated_at.desc()
            ).first()
            if row:
                return row.content
    except Exception:
        pass
    return DEFAULT_PROMPT


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
