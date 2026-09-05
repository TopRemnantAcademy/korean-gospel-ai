"""E-F: 임시저장 API.

PUT  /drafts/{version_id}     저장 (upsert)
GET  /drafts/{version_id}     불러오기 (최신)
DELETE /drafts/{version_id}   삭제 (publish 후 정리)
GET  /drafts                  운영자 전체 임시저장 목록
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..db import get_session
from ..models.orm import DocumentDraft, DocumentVersion
from ..models.schemas import DraftIn

router = APIRouter(prefix="/drafts", tags=["drafts"])


from .auth import check_admin as _check_admin


# DraftIn → models/schemas.py 로 이전됨


@router.put("/{version_id}")
def save_draft(version_id: str, payload: DraftIn, authorization: Optional[str] = Header(default=None)):
    """임시저장 upsert — version_id + operator_id 조합으로 1행 유지."""
    _check_admin(authorization)
    with get_session() as s:
        # 버전 존재 확인
        ver = s.query(DocumentVersion).filter(DocumentVersion.version_id == version_id).first()
        if not ver:
            raise HTTPException(404, "version not found")

        existing = (
            s.query(DocumentDraft)
            .filter(DocumentDraft.version_id == version_id,
                    DocumentDraft.operator_id == payload.operator_id)
            .first()
        )
        now = datetime.now(timezone.utc)
        if existing:
            if payload.draft_body is not None:
                existing.draft_body = payload.draft_body
            if payload.draft_meta is not None:
                existing.draft_meta = payload.draft_meta
            existing.saved_at = now
            existing.device_id = payload.device_id
        else:
            s.add(DocumentDraft(
                version_id=version_id,
                operator_id=payload.operator_id,
                draft_body=payload.draft_body,
                draft_meta=payload.draft_meta or {},
                device_id=payload.device_id,
                saved_at=now,
            ))
        return {"ok": True, "saved_at": now.isoformat()}


@router.get("/{version_id}")
def load_draft(
    version_id: str,
    operator_id: str = "admin",
    authorization: Optional[str] = Header(default=None),
):
    """최신 임시저장 반환. 없으면 404."""
    _check_admin(authorization)
    with get_session() as s:
        d = (
            s.query(DocumentDraft)
            .filter(DocumentDraft.version_id == version_id,
                    DocumentDraft.operator_id == operator_id)
            .first()
        )
        if not d:
            raise HTTPException(404, "no draft found")
        return {
            "version_id": d.version_id,
            "draft_body": d.draft_body,
            "draft_meta": d.draft_meta,
            "saved_at": d.saved_at.isoformat(),
            "device_id": d.device_id,
            "operator_id": d.operator_id,
        }


@router.delete("/{version_id}")
def delete_draft(
    version_id: str,
    operator_id: str = "admin",
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        rows = (
            s.query(DocumentDraft)
            .filter(DocumentDraft.version_id == version_id,
                    DocumentDraft.operator_id == operator_id)
            .all()
        )
        for r in rows:
            s.delete(r)
        return {"ok": True, "deleted": len(rows)}


@router.get("")
def list_drafts(
    operator_id: str = "admin",
    authorization: Optional[str] = Header(default=None),
):
    """전체 임시저장 목록 (가장 최근 수정 순)."""
    _check_admin(authorization)
    with get_session() as s:
        rows = (
            s.query(DocumentDraft)
            .filter(DocumentDraft.operator_id == operator_id)
            .order_by(DocumentDraft.saved_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": r.id,
                "version_id": r.version_id,
                "saved_at": r.saved_at.isoformat(),
                "device_id": r.device_id,
                "body_preview": (r.draft_body or "")[:100],
            }
            for r in rows
        ]
