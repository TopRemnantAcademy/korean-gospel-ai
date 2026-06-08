"""자동 용어집 서비스.

변경 2026-05-29:
- 한국어 형태소 인식 기반 노이즈 필터 추가 (동사어미·조사 제거)
- 복음/교회 도메인 전용어 whitelist → 자동 승인
- 한국어 일반 불용어(stopwords) 목록 추가
- 일반 단어 최소 빈도 상향 (3 → 7) + 화이트리스트 도메인어는 1회로도 등록
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.orm import GlossaryTerm

# ─────────────────────────────────────────────────────────────────────────────
# 복음/교회 도메인 전용어 — 이 목록에 있으면 1회 등장만으로 자동 승인
# ─────────────────────────────────────────────────────────────────────────────
_DOMAIN_WHITELIST: frozenset[str] = frozenset({
    # 신학 교리
    "칭의", "성화", "영화", "대속", "화목제", "구속", "중보", "부활",
    "승천", "재림", "십자가", "은혜", "믿음", "회개", "의롭다하심",
    "삼위일체", "복음", "구원", "영접", "거듭남", "성령세례", "방언",
    "예정론", "언약신학", "속죄론", "기독론", "종말론",
    # 성경 인물·장소
    "예수님", "예수", "그리스도", "하나님", "성령님", "성령",
    "아브라함", "모세", "바울", "베드로", "요한", "다윗", "솔로몬",
    "예루살렘", "가나안", "갈릴리", "유대",
    # 성경 책명
    "요한복음", "로마서", "갈라디아서", "에베소서", "빌립보서",
    "골로새서", "데살로니가", "디모데", "히브리서", "야고보서",
    "요한계시록", "창세기", "출애굽기", "레위기", "신명기",
    "사무엘", "열왕기", "역대기", "에스라", "느헤미야", "에스더",
    "잠언", "전도서", "아가서", "이사야", "예레미야",
    # 교회·사역 고유어
    "렘넌트", "미션홈", "다락방", "전도폭발", "제자훈련", "제자도",
    "교회개척", "선교지", "선교사", "단기선교", "사역자",
    "구역장", "셀모임", "소그룹", "청년부", "구역모임",
    "주일학교", "기독교교육", "전도여행", "영적지도",
    "목사님", "전도사", "강도사", "장로님", "집사님", "권사님",
    "교단총회", "노회", "당회", "부흥회", "사경회", "특새",
    "찬양대", "예배인도", "성경공부", "복음화", "영적성장",
    "성화과정", "영적훈련", "간증", "증거", "시험", "연단",
    "세례", "침례", "성찬", "헌신", "봉사", "섬김", "디아코니아",
    "케리그마", "디다케", "코이노니아", "마라나타",
})

# ─────────────────────────────────────────────────────────────────────────────
# 동사어미·조사 끝을 가진 단어 → 명사가 아니므로 제외
# ─────────────────────────────────────────────────────────────────────────────
_NON_NOUN_ENDINGS: tuple[str, ...] = (
    # 경어 서술어
    "습니다", "입니다", "이에요", "예요", "이었습니다", "였습니다",
    "셨습니다", "겠습니다", "했습니다", "됩니다", "됐습니다",
    "합니다", "됩니다", "드립니다", "받습니다", "있습니다", "없습니다",
    # 동사 활용
    "하여서", "하므로", "하기에", "하면서", "하지만", "하더니",
    "하여도", "하여야", "하지만", "하지마", "하거나",
    "하고요", "하는데", "하는지", "하더라",
    # 연결형
    "이라고", "이라는", "이라도", "이라며",
    "이고요", "이며요",
    # 조사 결합형 — 이 형태로 끝나는 건 조사가 붙은 것
    "에서요", "에게요", "으로요", "까지요", "부터요",
    "이에요", "이어요",
    # 부사형
    "하게도", "하게만", "하게끔",
)

# ─────────────────────────────────────────────────────────────────────────────
# 한국어 고빈도 일반 불용어 — 어떤 텍스트에나 자주 나와서 의미 없음
# ─────────────────────────────────────────────────────────────────────────────
_STOPWORDS: frozenset[str] = frozenset({
    # 접속사
    "그래서", "하지만", "그러나", "그리고", "또한", "그런데", "왜냐하면",
    "따라서", "그러므로", "그렇지만", "게다가", "더구나", "더욱이",
    # 지시대명사·부사
    "이렇게", "저렇게", "그렇게", "어떻게", "이미", "아직도",
    "바로요", "정말로", "많이도", "조금씩", "오히려",
    # 불완전 명사·의존명사 복합
    "때문에", "위해서", "통해서", "위하여", "통하여",
    "것이다", "것이며", "것이고", "수있다", "수없다",
    "수있는", "수없는", "것들이", "것들을",
    # 사람 복수형 + 조사 결합
    "사람들이", "사람들은", "사람들을", "사람들의", "사람들에",
    "우리들이", "우리들은", "우리들을",
    # 핵심 종교어의 굴절형 (격조사 결합) — 도메인 화이트리스트의 굴절형은 제외
    "하나님의", "하나님께", "하나님이", "하나님이시",
    "예수님의", "예수님께", "예수님이",
    "성령님의", "성령님께", "성령님이",
    "말씀을", "말씀이", "말씀의", "말씀으로", "말씀에",
    "마음이", "마음을", "마음으로", "마음속에", "마음에서",
    "믿음이", "믿음을", "믿음으로", "믿음의",
    "기도로", "기도가", "기도를",
    "사랑이", "사랑을", "사랑의", "사랑으로",
    "삶이", "삶을", "삶의", "삶에서",
})


def _is_glossary_candidate(word: str) -> bool:
    """해당 단어가 용어집에 등록할 만한 명사형인지 판별.

    규칙:
    1. 한국어 불용어 목록에 있으면 False
    2. 동사/형용사 어미·조사로 끝나면 False
    3. 도메인 화이트리스트에 있으면 True (즉시 통과)
    4. 그 외: 길이 2자 이상이고 어미·불용어 미해당이면 True
    """
    if word in _STOPWORDS:
        return False
    for ending in _NON_NOUN_ENDINGS:
        if word.endswith(ending):
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 신학 용어 시드 (최초 실행 시)
# ─────────────────────────────────────────────────────────────────────────────
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
    ("렘넌트", "렘넌트", "church"),
    ("미션홈", "미션홈", "church"),
    ("다락방", "다락방", "church"),
    ("제자훈련", "제자훈련", "church"),
    ("전도폭발", "전도폭발", "church"),
]


def seed_theology_terms(session: Session) -> int:
    added = 0
    for term, canonical, category in _SEED_THEOLOGY_TERMS:
        existing = session.query(GlossaryTerm).filter(GlossaryTerm.term == term).first()
        if not existing:
            session.add(GlossaryTerm(
                term=term,
                canonical_form=canonical,
                category=category,
                is_theology_term=(category in ("doctrine", "person")),
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
    min_freq: int = 7,          # 일반 단어: 7회 이상 (노이즈 감소)
    domain_min_freq: int = 1,   # 도메인 전용어: 1회만 나와도 등록
    min_len: int = 2,
) -> list[GlossaryTerm]:
    """텍스트에서 전문 명사를 추출해 용어집에 등록/업데이트.

    개선:
    - 동사어미·조사 결합형 제외
    - 한국어 일반 불용어 제외
    - 복음/교회 도메인 전용어는 낮은 빈도에서도 자동 승인
    - 일반 단어는 높은 빈도 임계값 적용 (노이즈 감소)
    """
    from collections import Counter

    words = re.findall(r"[가-힣]{%d,30}" % min_len, text)
    freq  = Counter(words)

    updated: list[GlossaryTerm] = []
    now = datetime.now(datetime.UTC)

    for word, cnt in freq.items():
        # ── 필터 1: 명사형인지 판별 ────────────────────────────
        if not _is_glossary_candidate(word):
            continue

        # ── 필터 2: 빈도 기준 ──────────────────────────────────
        is_domain = word in _DOMAIN_WHITELIST
        required  = domain_min_freq if is_domain else min_freq
        if cnt < required:
            continue

        # ── 등록 또는 빈도 업데이트 ───────────────────────────
        existing = session.query(GlossaryTerm).filter(GlossaryTerm.term == word).first()
        if existing:
            existing.frequency_count += cnt
            existing.last_seen_at = now
            # 도메인 단어는 재확인 시 자동 승인 보장
            if is_domain and not existing.operator_verified:
                existing.operator_verified = True
                existing.is_theology_term  = (existing.category in ("doctrine", "person"))
            updated.append(existing)
        else:
            is_theology = is_domain and word in {
                t for t, _, cat in _SEED_THEOLOGY_TERMS if cat in ("doctrine", "person")
            }
            category = "church" if is_domain else "other"
            if is_theology:
                category = "doctrine"

            new_term = GlossaryTerm(
                term              = word,
                canonical_form    = word,
                category          = category,
                frequency_count   = cnt,
                first_seen_doc_id = doc_id,
                last_seen_at      = now,
                operator_verified = is_domain,   # 도메인어는 즉시 승인
                is_theology_term  = is_theology,
            )
            session.add(new_term)
            updated.append(new_term)

    session.flush()
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# 나머지 서비스 함수 (기존 유지)
# ─────────────────────────────────────────────────────────────────────────────

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
    t.is_theology_term  = is_theology
    if definition is not None:
        t.definition = definition
    if category is not None:
        t.category = category
    t.updated_at = datetime.now(datetime.UTC)
    session.flush()
    return t


def reject_term(session: Session, term_id: int) -> None:
    t = session.query(GlossaryTerm).filter(GlossaryTerm.id == term_id).first()
    if t:
        session.delete(t)
        session.flush()


def merge_aliases(session: Session, canonical_id: int, alias_ids: list[int]) -> GlossaryTerm:
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
    canonical.aliases    = existing_aliases
    canonical.updated_at = datetime.now(datetime.UTC)
    session.flush()
    return canonical


def get_theology_whitelist(session: Session) -> list[str]:
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
    return (
        session.query(GlossaryTerm)
        .filter(GlossaryTerm.operator_verified == False)
        .order_by(GlossaryTerm.frequency_count.desc())
        .limit(limit)
        .all()
    )


def get_stats(session: Session) -> dict:
    total    = session.query(GlossaryTerm).count()
    verified = session.query(GlossaryTerm).filter(GlossaryTerm.operator_verified == True).count()
    theology = session.query(GlossaryTerm).filter(GlossaryTerm.is_theology_term == True).count()
    pending  = session.query(GlossaryTerm).filter(GlossaryTerm.operator_verified == False).count()
    return {"total": total, "verified": verified, "theology": theology, "pending": pending}
