"""성경 본문 관리 API.

관리자:
  POST /admin/bible/upload      — 성경 책 텍스트 파일 업로드 (data/bible/{책}.txt)
  GET  /admin/bible/books        — 색인된 책 목록 + 구조 (관리자)
  DELETE /admin/bible/books/{book} — 책 삭제

공개 (모바일 앱):
  GET  /mobile/bible/books       — 색인된 책 목록 + 구조 (book/chapter/verse 선택기용)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile

from .auth import check_admin as _check_admin
from ..config import settings
from ..services import bible_service

log = logging.getLogger("gospel-api.bible")

admin_router = APIRouter(prefix="/admin/bible", tags=["admin-bible"])
public_router = APIRouter(prefix="/mobile/bible", tags=["mobile-bible"])

BIBLE_DIR = settings.root_dir / "data" / "bible"

# 업로드 허용 확장자
_BIBLE_EXTS = (".txt", ".md")


def _safe_book_name(filename: str) -> Optional[str]:
    """파일명에서 책명 추출 + 보안 검증. 경로 순회 시도 시 None."""
    stem = Path(filename).stem.strip()
    # 한글/영숫자/공백/하이픈/밑줄만 허용
    if not re.fullmatch(r"[가-힣一-鿿A-Za-z0-9 _-]{1,30}", stem):
        return None
    return stem


@admin_router.post("/upload")
async def admin_upload_bible(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    """성경 책 텍스트 업로드. 파일명이 책명이 됩니다 (예: 요한복음.txt)."""
    _check_admin(authorization)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _BIBLE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 형식입니다: {ext or '(없음)'}. .txt 또는 .md 만 가능.",
        )

    book = _safe_book_name(file.filename or "")
    if not book:
        raise HTTPException(
            status_code=400,
            detail="文件名不合法。请使用中文/英文书卷名保存（例如：约翰福音.txt）。",
        )

    data = await file.read()
    if not data.strip():
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    BIBLE_DIR.mkdir(parents=True, exist_ok=True)
    target = BIBLE_DIR / f"{book}.txt"
    target.write_bytes(data)

    # 캐시 무효화 (버전 키 형식 호환: 기존 '책명' + 신규 'version:책명')
    bible_service._book_cache.pop(book, None)
    bible_service._book_cache.pop(f"simpl:{book}", None)
    bible_service._book_cache.pop(f"trad:{book}", None)

    struct = bible_service.get_book_structure(book)
    return {
        "book": book,
        "file": target.name,
        "total_chapters": struct["total_chapters"] if struct else 0,
        "total_verses": sum(c["verse_count"] for c in struct["chapters"]) if struct else 0,
        "message": f"{book} 업로드 완료",
    }


@admin_router.get("/books")
def admin_list_books(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    books = bible_service.list_book_summaries()
    return {
        "books": books,
        "total": len(books),
        "groups": bible_service.list_books_grouped(),
    }


@admin_router.delete("/books/{book}")
def admin_delete_book(book: str, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    ok = bible_service.delete_book(book)
    if not ok:
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다.")
    return {"ok": True, "book": book}


@public_router.get("/books")
def public_list_books(version: str = Query("simpl", pattern=r"^(simpl|trad|kjv)$", description="성경 버전: simpl(간체)/trad(번체)/kjv(영어)")):
    """색인된 책 목록 + 구조 (모바일 성경 선택기용). 공개."""
    import json
    from fastapi import Response as _Resp

    books = bible_service.list_book_summaries(version=version)
    return _Resp(
        content=json.dumps({
            "version": version,
            "books": books,
            "total": len(books),
            "groups": bible_service.list_books_grouped(version=version),
        }, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=300"},
    )
