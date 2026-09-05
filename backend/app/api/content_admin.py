"""관리자용 영성훈련 콘텐츠 링크 관리 API.

모든 엔드포인트는 check_admin (ADMIN_API_KEY) 인증 필요.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import check_admin as _check_admin
from ..services import content_service

router = APIRouter(prefix="/admin/content", tags=["admin-content"])


class ContentLinkIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=500)
    source: Optional[str] = None  # 미지정 시 자동 감지
    category: str = "lecture"  # lecture | music | devotion
    lang: str = "ko"  # ko|zh|en|ja — 중국어 앱은 zh 만 노출
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    target_salvation_stage: Optional[list[str]] = None
    order_index: int = 0
    active: bool = True


class ContentLinkPatch(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    lang: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    target_salvation_stage: Optional[list[str]] = None
    order_index: Optional[int] = None
    active: Optional[bool] = None


class ReorderIn(BaseModel):
    order_index: int


@router.get("/links")
def admin_list_links(
    category: Optional[str] = None,
    active_only: bool = False,
    authorization: Optional[str] = Header(default=None),
):
    """전체 콘텐츠 링크 목록 (관리자용 — active/false 포함)."""
    _check_admin(authorization)
    items = content_service.list_content(
        category=category, source=None, active_only=active_only
    )
    return {"items": items, "total": len(items)}


@router.post("/links")
def admin_create_link(
    payload: ContentLinkIn,
    authorization: Optional[str] = Header(default=None),
):
    """콘텐츠 링크 생성. URL 보안 검증 + embed 변환 자동 수행."""
    _check_admin(authorization)
    try:
        return content_service.create_content(
            title=payload.title,
            url=payload.url,
            source=payload.source,
            category=payload.category,
            lang=payload.lang,
            description=payload.description,
            tags=payload.tags,
            target_salvation_stage=payload.target_salvation_stage,
            order_index=payload.order_index,
            active=payload.active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/links/{link_id}")
def admin_update_link(
    link_id: str,
    payload: ContentLinkPatch,
    authorization: Optional[str] = Header(default=None),
):
    """콘텐츠 링크 부분 수정."""
    _check_admin(authorization)
    try:
        # exclude_unset=True — 클라이언트가 명시적으로 보낸 필드만 처리
        # (미전송=None 제외, 전송된 False/빈문자열/빈리스트는 유지)
        fields = payload.model_dump(exclude_unset=True)
        return content_service.update_content(link_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/links/{link_id}")
def admin_delete_link(
    link_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """콘텐츠 링크 삭제."""
    _check_admin(authorization)
    ok = content_service.delete_content(link_id)
    if not ok:
        raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
    return {"ok": True, "link_id": link_id}


@router.post("/links/{link_id}/reorder")
def admin_reorder_link(
    link_id: str,
    payload: ReorderIn,
    authorization: Optional[str] = Header(default=None),
):
    """콘텐츠 정렬 순서 변경."""
    _check_admin(authorization)
    try:
        return content_service.reorder_content(link_id, payload.order_index)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
