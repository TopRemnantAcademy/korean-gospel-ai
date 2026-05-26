"""E-E: 용어집 API.

GET  /glossary           전체 목록 (검색/필터)
GET  /glossary/pending   승인 대기 목록
GET  /glossary/stats     통계
POST /glossary/seed      기본 신학 용어 시드 (최초 1회)
POST /glossary/{id}/approve   승인
POST /glossary/{id}/reject    거부
POST /glossary/{id}/merge     동의어 통합
PATCH /glossary/{id}          정의/카테고리 수정
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..db import get_session
from ..services import glossary_service

router = APIRouter(prefix="/glossary", tags=["glossary"])


def _check_admin(authorization: Optional[str]):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(403, "missing admin token")
    if authorization.split(" ", 1)[1].strip() != settings.admin_api_key:
        raise HTTPException(403, "invalid admin token")


# ── 요청 모델 ──────────────────────────────────────────────────────────────
class ApproveIn(BaseModel):
    is_theology: bool = False
    definition: Optional[str] = None
    category: Optional[str] = None


class MergeIn(BaseModel):
    alias_ids: list[int]


class PatchTermIn(BaseModel):
    definition: Optional[str] = None
    category: Optional[str] = None
    canonical_form: Optional[str] = None
    is_theology_term: Optional[bool] = None


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
def list_terms(
    q: str = "",
    category: Optional[str] = None,
    verified_only: bool = False,
    theology_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        rows = glossary_service.search_terms(
            s, q=q, category=category,
            verified_only=verified_only, theology_only=theology_only,
            limit=limit, offset=offset,
        )
        return [_term_to_dict(r) for r in rows]


@router.get("/pending")
def list_pending(limit: int = 50, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        rows = glossary_service.list_pending(s, limit=limit)
        return [_term_to_dict(r) for r in rows]


@router.get("/stats")
def stats(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        return glossary_service.get_stats(s)


@router.post("/seed")
def seed(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        added = glossary_service.seed_theology_terms(s)
        return {"ok": True, "added": added}


@router.post("/{term_id}/approve")
def approve(term_id: int, payload: ApproveIn, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        t = glossary_service.approve_term(
            s, term_id=term_id,
            is_theology=payload.is_theology,
            definition=payload.definition,
            category=payload.category,
        )
        return _term_to_dict(t)


@router.post("/{term_id}/reject")
def reject(term_id: int, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        glossary_service.reject_term(s, term_id=term_id)
        return {"ok": True}


@router.post("/{term_id}/merge")
def merge(term_id: int, payload: MergeIn, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        t = glossary_service.merge_aliases(s, canonical_id=term_id, alias_ids=payload.alias_ids)
        return _term_to_dict(t)


@router.patch("/{term_id}")
def patch_term(term_id: int, payload: PatchTermIn, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        from ..models.orm import GlossaryTerm
        from datetime import datetime
        t = s.query(GlossaryTerm).filter(GlossaryTerm.id == term_id).first()
        if not t:
            raise HTTPException(404, "term not found")
        if payload.definition is not None:
            t.definition = payload.definition
        if payload.category is not None:
            t.category = payload.category
        if payload.canonical_form is not None:
            t.canonical_form = payload.canonical_form
        if payload.is_theology_term is not None:
            t.is_theology_term = payload.is_theology_term
        t.updated_at = datetime.utcnow()
        return _term_to_dict(t)


def _term_to_dict(t) -> dict:
    return {
        "id": t.id,
        "term": t.term,
        "canonical_form": t.canonical_form,
        "aliases": t.aliases or [],
        "category": t.category,
        "definition": t.definition,
        "related_terms": t.related_terms or [],
        "frequency_count": t.frequency_count,
        "first_seen_doc_id": t.first_seen_doc_id,
        "last_seen_at": t.last_seen_at.isoformat() if t.last_seen_at else None,
        "operator_verified": t.operator_verified,
        "is_theology_term": t.is_theology_term,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
