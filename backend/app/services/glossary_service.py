"""E-E: 자동 용어집 서비스.

- extract_terms_from_text(): 텍스트에서 신학용어·반복명사 추출 → GlossaryTerm 후보 생성
- approve_term() / reject_term(): 운영자 검토
- merge_aliases(): 동의어 통합
- get_theology_whitelist(): D3 가드레일용 승인된 신학 용어 목록
- search_terms(): 검색
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.orm import GlossaryTerm

# 기본 신학 용어 시드 (최초 실행 시 자동 등록)
_SEED_THEOLOGY_TERMS = [
    ("칭의", "칭의", "doctrine"),
    ("성화", "성화", "doctrine"),
    ("영화", "영화", "doctrine"),
    ("대속", "대속", "doctrine"),
    ("화목제", "화목제", "doctrine"),
    ("구속", "구속", "doctrine"),
    ("중보", "중보", "doctrine"),
    ("부활", "부활", "doctrine"),
    ("승천", "승천", "doctrine"),
    ("재림", "재림", "doctrine"),
    ("십자가", "십자가", "doctrine"),
    ("은혜", "은혜", "doctrine"),
    ("믿음", "믿음", "doctrine"),
    ("회개", "회개", "doctrine"),
    ("의롭다하심", "의롭다하심", "doctrine"),
    ("하나님", "하나님", "person"),
    ("예수님", "예수님", "person"),
    ("예수", "예수님", "person"),
    ("그리스도", "그리스도", "person"),
    ("성령님", "성령님", "person"),
    ("성령", "성령님", "person"),
    ("삼위일체", "삼위일체", "doctrine"),
    ("복음", "복음", "doctrine"),
    ("구원", "구원", "doctrine"),
    ("영접", "영접", "doctrine"),
    ("거듭남", "거듭남", "doctrine"),
]


def seed_theology_terms(session: Session) -> int:
    """최초 실행 시 기본 신학 용어 시드. 이미 있으면 skip. 추가된 수 반환."""
    added = 0
    for term, canonical, category in _SEED_THEOLOGY_TERMS:
        existing = session.query(GlossaryTerm).filter(GlossaryTerm.term == term).first()
        if not existing:
            session.add(GlossaryTerm(
                term=term,
                canonical_form=canonical,
                category=category,
                is_theology_term=True,
                operator_verified=True,
                frequency_count=0,
            ))
            added += 1
    session.flush()
    return added


def extract_terms_from_text(
    session: Session,
    text: str,
    doc_id: Optional[str] = None,
    min_freq: int = 3,
    min_len: int = 2,
) -> list[GlossaryTerm]:
    """텍스트에서 반복 등장 한글 명사(추정)를 추출, 빈도 업데이트 또는 신규 후보 등록.

    kiwipiepy/mecab 없이 regex 기반 단순 추출 (E-E 기본 구현).
    5자 이상 단어는 min_freq=3, 2~4자 고유명사(대문자로 시작 불가 → 단어 빈도)는
    min_freq를 5로 높여 노이즈 감소.
    """
    # 한글 단어 추출 (2~30자)
    words = re.findall(r"[가-힣]{%d,30}" % min_len, text)
    from collections import Counter
    freq = Counter(words)

    updated: list[GlossaryTerm] = []
    now = datetime.utcnow()

    for word, cnt in freq.items():
        effective_min = min_freq if len(word) >= 5 else min_freq + 2
        if cnt < effective_min:
            continue

        existing = session.query(GlossaryTerm).filter(GlossaryTerm.term == word).first()
        if existing:
            existing.frequency_count += cnt
            existing.last_seen_at = now
            updated.append(existing)
        else:
            new_term = GlossaryTerm(
                term=word,
                canonical_form=word,
                category="other",
                frequency_count=cnt,
                first_seen_doc_id=doc_id,
                last_seen_at=now,
                operator_verified=False,
                is_theology_term=False,
            )
            session.add(new_term)
            updated.append(new_term)

    session.flush()
    return updated


def approve_term(
    session: Session,
    term_id: int,
    is_theology: bool = False,
    definition: Optional[str] = None,
    category: Optional[str] = None,
) -> GlossaryTerm:
    t = session.query(GlossaryTerm).filter(GlossaryTerm.id == term_id).first()
    if not t:
        raise ValueError(f"GlossaryTerm id={term_id} not found")
    t.operator_verified = True
    t.is_theology_term = is_theology
    if definition is not None:
        t.definition = definition
    if category is not None:
        t.category = category
    t.updated_at = datetime.utcnow()
    session.flush()
    return t


def reject_term(session: Session, term_id: int) -> None:
    t = session.query(GlossaryTerm).filter(GlossaryTerm.id == term_id).first()
    if t:
        session.delete(t)
        session.flush()


def merge_aliases(session: Session, canonical_id: int, alias_ids: list[int]) -> GlossaryTerm:
    """alias_ids 의 term들을 canonical_id 의 aliases 로 통합 후 원본 행 삭제."""
    canonical = session.query(GlossaryTerm).filter(GlossaryTerm.id == canonical_id).first()
    if not canonical:
        raise ValueError("canonical term not found")
    existing_aliases = list(canonical.aliases or [])
    for aid in alias_ids:
        alias = session.query(GlossaryTerm).filter(GlossaryTerm.id == aid).first()
        if not alias:
            continue
        if alias.term not in existing_aliases:
            existing_aliases.append(alias.term)
        canonical.frequency_count += alias.frequency_count
        session.delete(alias)
    canonical.aliases = existing_aliases
    canonical.updated_at = datetime.utcnow()
    session.flush()
    return canonical


def get_theology_whitelist(session: Session) -> list[str]:
    """D3 가드레일용 승인된 신학 용어 + aliases 목록."""
    rows = session.query(GlossaryTerm).filter(
        GlossaryTerm.is_theology_term == True,
        GlossaryTerm.operator_verified == True,
    ).all()
    result: list[str] = []
    for r in rows:
        result.append(r.term)
        result.extend(r.aliases or [])
    return list(set(result))


def search_terms(
    session: Session,
    q: str = "",
    category: Optional[str] = None,
    verified_only: bool = False,
    theology_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[GlossaryTerm]:
    query = session.query(GlossaryTerm)
    if q:
        query = query.filter(GlossaryTerm.term.like(f"%{q}%"))
    if category:
        query = query.filter(GlossaryTerm.category == category)
    if verified_only:
        query = query.filter(GlossaryTerm.operator_verified == True)
    if theology_only:
        query = query.filter(GlossaryTerm.is_theology_term == True)
    return query.order_by(GlossaryTerm.frequency_count.desc()).offset(offset).limit(limit).all()


def list_pending(session: Session, limit: int = 50) -> list[GlossaryTerm]:
    """승인 대기 중인 용어 (operator_verified=False, is_theology_term=False)."""
    return (
        session.query(GlossaryTerm)
        .filter(GlossaryTerm.operator_verified == False)
        .order_by(GlossaryTerm.frequency_count.desc())
        .limit(limit)
        .all()
    )


def get_stats(session: Session) -> dict:
    total = session.query(GlossaryTerm).count()
    verified = session.query(GlossaryTerm).filter(GlossaryTerm.operator_verified == True).count()
    theology = session.query(GlossaryTerm).filter(GlossaryTerm.is_theology_term == True).count()
    pending = session.query(GlossaryTerm).filter(GlossaryTerm.operator_verified == False).count()
    return {
        "total": total,
        "verified": verified,
        "theology": theology,
        "pending": pending,
    }
