"""Audit log 기록. immutable. 모든 state transition을 통과."""
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import Session

from ..models.orm import AuditLog


def log(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    who: str = "admin",
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    note: Optional[dict] = None,
) -> AuditLog:
    row = AuditLog(
        who=who,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_state=from_state,
        to_state=to_state,
        note=note or {},
    )
    session.add(row)
    session.flush()
    return row


def list_for(session: Session, entity_id: str, limit: int = 100) -> list[AuditLog]:
    return (
        session.query(AuditLog)
        .filter(AuditLog.entity_id == entity_id)
        .order_by(AuditLog.when.desc())
        .limit(limit)
        .all()
    )


def recent(session: Session, limit: int = 50) -> list[AuditLog]:
    return session.query(AuditLog).order_by(AuditLog.when.desc()).limit(limit).all()
