"""말씀 하이라이트/북마크/메모 CRUD (로그인 사용자 전용)."""
from __future__ import annotations

from typing import Optional

from ..db import get_session
from ..models.orm import VerseAnnotation

ALLOWED_COLORS = {"yellow", "green", "blue", "pink"}


def _serialize(r: VerseAnnotation) -> dict:
    return {
        "id": r.id,
        "book": r.book,
        "chapter": r.chapter,
        "verse": r.verse,
        "color": r.color,
        "note": r.note,
        "created_at": r.created_at.isoformat(),
    }


def list_annotations(subscriber_id: str) -> list[dict]:
    with get_session() as s:
        rows = (
            s.query(VerseAnnotation)
            .filter(VerseAnnotation.subscriber_id == subscriber_id)
            .order_by(VerseAnnotation.created_at.desc())
            .all()
        )
        return [_serialize(r) for r in rows]


def upsert_annotation(
    subscriber_id: str,
    book: str,
    chapter: int,
    verse: int,
    color: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """같은 (구독자, 책, 장, 절)이 있으면 갱신, 없으면 생성. color/note 는 항상 덮어씀."""
    if color not in ALLOWED_COLORS:
        color = None  # 알 수 없는 색은 하이라이트 없음으로 정규화
    with get_session() as s:
        row = (
            s.query(VerseAnnotation)
            .filter(
                VerseAnnotation.subscriber_id == subscriber_id,
                VerseAnnotation.book == book,
                VerseAnnotation.chapter == chapter,
                VerseAnnotation.verse == verse,
            )
            .first()
        )
        if row is None:
            row = VerseAnnotation(
                subscriber_id=subscriber_id, book=book, chapter=chapter,
                verse=verse, color=color, note=note,
            )
            s.add(row)
        else:
            row.color = color
            row.note = note
        s.commit()
        return _serialize(row)


def delete_annotation(annotation_id: str, subscriber_id: str) -> bool:
    with get_session() as s:
        row = (
            s.query(VerseAnnotation)
            .filter(
                VerseAnnotation.id == annotation_id,
                VerseAnnotation.subscriber_id == subscriber_id,
            )
            .first()
        )
        if not row:
            return False
        s.delete(row)
        return True


def delete_annotation_by_ref(subscriber_id: str, book: str, chapter: int, verse: int) -> bool:
    """(책, 장, 절) 기준 삭제 — 프론트 ref 기반 동기화용."""
    with get_session() as s:
        row = (
            s.query(VerseAnnotation)
            .filter(
                VerseAnnotation.subscriber_id == subscriber_id,
                VerseAnnotation.book == book,
                VerseAnnotation.chapter == chapter,
                VerseAnnotation.verse == verse,
            )
            .first()
        )
        if not row:
            return False
        s.delete(row)
        return True
