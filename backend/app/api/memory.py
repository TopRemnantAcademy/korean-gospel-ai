"""GET /memory/* - 대화 기록 조회/검색/삭제."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..models.schemas import FeedbackIn
from ..services import memory_service


router = APIRouter(prefix="/memory", tags=["memory"])


from .auth import check_admin as _check_admin


@router.get("/list")
def list_memory(
    search: Optional[str] = None,
    limit: int = 200,
    subscriber_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    return memory_service.all_interactions(
        subscriber_id=subscriber_id, limit=limit, search=search,
    )


@router.get("/stats")
def stats(
    subscriber_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    return memory_service.stats(subscriber_id=subscriber_id)


@router.delete("/{interaction_id}")
def delete(
    interaction_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    ok = memory_service.delete_interaction(interaction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}



# FeedbackIn → models/schemas.py 로 이전됨

@router.patch("/{interaction_id}/feedback")
def set_feedback(
    interaction_id: str,
    payload: FeedbackIn,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    result = memory_service.set_feedback(interaction_id, payload.value)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail="not found or invalid value")
    return result
