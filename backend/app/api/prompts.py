"""GET/PUT /prompts/* - 시스템 프롬프트 편집."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..models.schemas import PromptIn
from ..services import prompt_service


router = APIRouter(prefix="/prompts", tags=["prompts"])


from .auth import check_admin as _check_admin


# PromptIn → models/schemas.py 로 이전됨

@router.get("/current")
def get_current(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    return prompt_service.current_detail()


@router.put("/current")
def put_current(payload: PromptIn, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    if not payload.content or len(payload.content) < 20:
        raise HTTPException(400, "프롬프트가 너무 짧습니다 (최소 20자)")
    return prompt_service.save(payload.content, note=payload.note)


@router.post("/reset")
def reset(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    return prompt_service.reset_to_default()


@router.get("/history")
def history(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    return prompt_service.history()
