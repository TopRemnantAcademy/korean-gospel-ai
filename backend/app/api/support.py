"""P4 #8 — 신고/오류 제보 시스템.

- 공개: POST /support/tickets — 사용자가 버그/신고/오류/남용 제보. 서버 측 dedup.
- 관리: GET /admin/support/tickets, POST /admin/support/tickets/{id}/resolve
  (require_admin — X-API-Key == ADMIN_API_KEY, P0-3 인증 재사용)
- 에러 로깅은 기존 AppErrorLog(ErrorMonitorMiddleware) 재사용.
- 속도 제한은 RateLimitMiddleware 재사용(_RATE_PREFIXES 에 /support 포함).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models.orm import SupportTicket
from .enhanced_rag import require_admin

router = APIRouter(tags=["support"])

_ALLOWED_TYPES = {"bug", "report", "abuse", "error", "other"}
_DEDUP_WINDOW_SEC = 86400  # 24시간 내 동일 제보는 중복 처리


class TicketCreate(BaseModel):
    type: str = Field(..., description="bug|report|abuse|error|other")
    target: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=5000)
    contact: Optional[str] = Field(None, max_length=200)
    sub_id: Optional[str] = None  # 클라이언트 익명 ID (dedup 보조)


class TicketOut(BaseModel):
    ticket_id: str
    status: str
    duplicate: bool = False


class TicketAdminOut(BaseModel):
    ticket_id: str
    created_at: str
    sub_id: Optional[str]
    type: str
    target: Optional[str]
    content: str
    contact: Optional[str]
    status: str
    dedup_hash: Optional[str]


def _dedup_hash(type_: str, target: Optional[str], content: str) -> str:
    raw = f"{type_}|{target or ''}|{content}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _fingerprint(sub_id: Optional[str], request: Request) -> str:
    if sub_id:
        return f"sub:{sub_id}"
    ip = (request.client.host if request.client else "unknown") or "unknown"
    return f"ip:{ip}"


@router.post("/support/tickets", response_model=TicketOut, status_code=201)
async def create_ticket(
    req: TicketCreate,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_session),
):
    if req.type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="invalid ticket type")
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")

    fp = _fingerprint(req.sub_id, request)
    dhash = _dedup_hash(req.type, req.target, content)

    # 서버 측 dedup: 동일 제보자(fp) + 해시 + 미해결 상태 + 24h 이내 → 기존 티켓 반환.
    # fp 는 로그인 시 sub_id, 익명 시 IP 핑거프린트 → 제보자별 중복만 차단(타인 리포트 보존).
    cutoff = datetime.now(timezone.utc).timestamp() - _DEDUP_WINDOW_SEC
    existing = (
        db.execute(
            select(SupportTicket).where(
                SupportTicket.dedup_hash == dhash,
                SupportTicket.sub_id == fp,
                SupportTicket.status.in_(["open", "reviewing"]),
                SupportTicket.created_at >= datetime.fromtimestamp(cutoff, timezone.utc),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return TicketOut(ticket_id=existing.ticket_id, status=existing.status, duplicate=True)

    ticket = SupportTicket(
        type=req.type,
        target=(req.target or "")[:200] or None,
        content=content,
        contact=(req.contact or "")[:200] or None,
        sub_id=fp,  # 익명이면 IP 핑거프린트, 로그인이면 sub_id
        dedup_hash=dhash,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return TicketOut(ticket_id=ticket.ticket_id, status=ticket.status, duplicate=False)


@router.get("/admin/support/tickets", response_model=list[TicketAdminOut])
async def list_tickets(
    status: str = "open",
    limit: int = 100,
    _: None = Depends(require_admin),
    db: Session = Depends(get_session),
):
    if limit > 500:
        limit = 500
    rows = (
        db.execute(
            select(SupportTicket)
            .where(SupportTicket.status == status)
            .order_by(SupportTicket.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        TicketAdminOut(
            ticket_id=r.ticket_id,
            created_at=r.created_at.isoformat() if r.created_at else "",
            sub_id=r.sub_id,
            type=r.type,
            target=r.target,
            content=r.content,
            contact=r.contact,
            status=r.status,
            dedup_hash=r.dedup_hash,
        )
        for r in rows
    ]


@router.post("/admin/support/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: str,
    admin_note: Optional[str] = None,
    _: None = Depends(require_admin),
    db: Session = Depends(get_session),
):
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    ticket.status = "resolved"
    ticket.resolved_at = datetime.now(timezone.utc)
    if admin_note:
        ticket.admin_note = admin_note
    db.commit()
    return {"ticket_id": ticket_id, "status": "resolved"}
