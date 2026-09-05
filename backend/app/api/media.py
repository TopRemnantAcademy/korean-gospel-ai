"""업로드된 오디오 미디어 API.

관리자:
  POST /admin/media            — 오디오 파일 업로드 (찬양/설교음성)
  GET  /admin/media            — 전체 목록 (비활성 포함)
  PATCH /admin/media/{id}      — 메타데이터 수정
  DELETE /admin/media/{id}     — 삭제

공개 (모바일 앱):
  GET  /mobile/media           — 카탈로그 (stream_url 포함)
  GET  /mobile/media/{id}/stream — Range 스트리밍
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .auth import check_admin as _check_admin
from ..config import settings
from ..services import media_service

log = logging.getLogger("gospel-api.media")

admin_router = APIRouter(prefix="/admin/media", tags=["admin-media"])
public_router = APIRouter(prefix="/mobile/media", tags=["mobile-media"])


class MediaMetaPatch(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    scripture_refs: Optional[list] = None
    order_index: Optional[int] = None
    active: Optional[bool] = None


# ═══════════════════════════════════════════════════════════════════════════
# 관리자
# ═══════════════════════════════════════════════════════════════════════════

def _parse_publish_at(raw: Optional[str]) -> Optional[datetime]:
    """관리자 입력(ISO, KST 기준) → UTC datetime. 빈값/파싱 실패 시 None."""
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    # tz 미지정이면 KST(UTC+9) 로 간주 → UTC 로 변환
    if dt.tzinfo is None:
        dt = dt - timedelta(hours=9)
    return dt.astimezone(timezone.utc)


@admin_router.post("")
async def admin_upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("worship"),
    artist: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    scripture_refs: Optional[str] = Form(None),
    order_index: int = Form(0),
    active: bool = Form(True),
    publish_at: Optional[str] = Form(None),
    notify_mode: str = Form("immediate"),
    authorization: Optional[str] = Header(default=None),
):
    """오디오 파일 업로드 + 메타데이터 저장.

    publish_at : 발행 예약 시각(ISO, KST). 미래 시각이면 예약 발행.
    notify_mode : "immediate" | "batch"(저녁 배치) | "none".
    """
    _check_admin(authorization)

    data = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다 ({settings.max_upload_size_mb}MB 제한).",
        )

    # scripture_refs 는 쉼표 구분 문자열 → 리스트
    refs: list[str] = []
    if scripture_refs:
        refs = [r.strip() for r in scripture_refs.split(",") if r.strip()]

    pub_dt = _parse_publish_at(publish_at)
    if notify_mode not in ("immediate", "batch", "none"):
        notify_mode = "immediate"

    try:
        return media_service.save_upload(
            filename=file.filename or "audio",
            data=data,
            title=title,
            category=category,
            artist=artist,
            description=description,
            scripture_refs=refs,
            order_index=order_index,
            active=active,
            publish_at=pub_dt,
            notify_mode=notify_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@admin_router.get("")
def admin_list_media(
    category: Optional[str] = Query(None, description="worship|sermon"),
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    items = media_service.list_admin(category=category)
    return {"items": items, "total": len(items)}


@admin_router.patch("/{asset_id}")
def admin_update_media(
    asset_id: str,
    payload: MediaMetaPatch,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    try:
        fields = payload.model_dump(exclude_unset=True)
        return media_service.update_asset(asset_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@admin_router.delete("/{asset_id}")
def admin_delete_media(
    asset_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    ok = media_service.delete_media(asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")
    return {"ok": True, "asset_id": asset_id}


# ═══════════════════════════════════════════════════════════════════════════
# 공개 (모바일 앱)
# ═══════════════════════════════════════════════════════════════════════════

@public_router.get("")
def list_media_catalog(
    category: Optional[str] = Query(None, description="worship|sermon"),
):
    """공개 미디어 카탈로그 (찬양/설교). stream_url 포함."""
    import json

    items = media_service.list_public(category=category)
    return Response(
        content=json.dumps({"items": items, "total": len(items)}, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=30, stale-while-revalidate=120"},
    )


@public_router.get("/version")
def media_catalog_version():
    """공개 카탈로그 변경 감지용 경량 버전. 모바일이 풀 동기화 전 저비용으로 갱신 필요 여부 판단."""
    return media_service.media_version()


@public_router.get("/{asset_id}/stream")
def stream_media(asset_id: str):
    """오디오 파일 스트리밍 (Range 지원)."""
    result = media_service.get_file(asset_id)
    if not result:
        raise HTTPException(status_code=404, detail="미디어 파일이 없습니다.")
    path, mime = result
    return FileResponse(str(path), media_type=mime, filename=path.name)
