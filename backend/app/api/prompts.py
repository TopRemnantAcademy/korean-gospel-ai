"""GET/PUT /prompts/* - 시스템 프롬프트 편집."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services import prompt_service


router = APIRouter(prefix="/prompts", tags=["prompts"])


def _check_admin(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="missing admin token")
    if authorization.split(" ", 1)[1].strip() != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin token")


class PromptIn(BaseModel):
    content: str
    note: Optional[str] = None


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
