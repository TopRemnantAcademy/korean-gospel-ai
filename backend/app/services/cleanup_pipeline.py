"""업로드 용어 추출 — 발행(publish) 시 자동 실행.

이미 정리된 설교 파일을 올리기 때문에 LLM 정제(오타수정·맥락분석)는 하지 않음.
필요한 것은 어떤 성경 구절·신학 용어·반복 단어가 나오는지 자동으로 뽑는 것뿐.

사용법 (내부 자동):
    terms = extract_terms(text)  # → list[str]

사용법 (API):
    result = await run_cleanup(text)  # 하위 호환 유지
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-29
# Task: 정제 파이프라인 대폭 간소화
#   · Stage 1 (기계적 정규화) 삭제 — 이미 정리된 파일 올림
#   · Stage 2 (LLM 오타 수정) 삭제 — 동일 이유
#   · Stage 3 (맥락 분석) 삭제 — 동일 이유
#   · Stage 4 (신학 보존 검증) 삭제 — 불필요
#   · Stage 5 (용어 추출) 유지 → 발행 시 자동 실행
# =============================================================================
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


# ── 신학 핵심 용어 화이트리스트 ───────────────────────────────────────────────
_THEOLOGY_TERMS = [
    "칭의", "성화", "영화", "대속", "화목제", "구속", "중보", "부활", "승천",
    "재림", "십자가", "은혜", "믿음", "회개", "의롭다하심", "하나님", "예수님",
    "그리스도", "성령님", "삼위일체", "복음", "구원", "영접", "거듭남",
    "요한복음", "로마서", "갈라디아서", "에베소서", "빌립보서",
]

# 성경 구절 패턴 (예: 요 3:16, 로마서 5:8)
_SCRIPTURE_PATTERN = re.compile(
    r"[가-힣A-Za-z]+\s*\d+:\d+[-–\d,\s]*"
)

# 성경 66권 정식명 + 통용 약어 화이트리스트 — 오탐(예: "진 4:0") 차단용
_BIBLE_BOOKS: frozenset[str] = frozenset({
    # 구약 정식명
    "창세기", "출애굽기", "레위기", "민수기", "신명기", "여호수아", "사사기", "룻기",
    "사무엘상", "사무엘하", "열왕기상", "열왕기하", "역대상", "역대하", "에스라",
    "느헤미야", "에스더", "욥기", "시편", "잠언", "전도서", "아가", "이사야",
    "예레미야", "예레미야애가", "에스겔", "다니엘", "호세아", "요엘", "아모스",
    "오바댜", "요나", "미가", "나훔", "하박국", "스바냐", "학개", "스가랴", "말라기",
    # 신약 정식명
    "마태복음", "마가복음", "누가복음", "요한복음", "사도행전", "로마서",
    "고린도전서", "고린도후서", "갈라디아서", "에베소서", "빌립보서", "골로새서",
    "데살로니가전서", "데살로니가후서", "디모데전서", "디모데후서", "디도서",
    "빌레몬서", "히브리서", "야고보서", "베드로전서", "베드로후서",
    "요한일서", "요한이서", "요한삼서", "유다서", "요한계시록",
    # 통용 약어
    "창", "출", "레", "민", "신", "수", "삿", "룻", "삼상", "삼하", "왕상", "왕하",
    "대상", "대하", "스", "느", "에", "욥", "시", "잠", "전", "아", "사", "렘", "애",
    "겔", "단", "호", "욜", "암", "옵", "욘", "미", "나", "합", "습", "학", "슥", "말",
    "마", "막", "눅", "요", "행", "롬", "고전", "고후", "갈", "엡", "빌", "골",
    "살전", "살후", "딤전", "딤후", "딛", "몬", "히", "약", "벧전", "벧후",
    "요일", "요이", "요삼", "유", "계",
})


def _is_valid_scripture(ref: str) -> bool:
    """성경 구절 유효성 검사 — 책 약어가 화이트리스트에 있고 장·절이 1 이상."""
    m = re.match(r"([가-힣A-Za-z]+)\s*(\d+):(\d+)", ref)
    if not m:
        return False
    book, chap, verse = m.group(1), int(m.group(2)), int(m.group(3))
    if book not in _BIBLE_BOOKS:
        return False
    return chap >= 1 and verse >= 1


@dataclass
class CleanupResult:
    """하위 호환 유지용 — API 응답 구조 동일하게 유지."""
    original_text: str
    final_text: str          # 텍스트 변경 없음 (원본 그대로)
    stage_texts: dict = field(default_factory=dict)
    diffs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    terms_found: list[str] = field(default_factory=list)
    theology_violations: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# 용어 추출 (규칙 기반, LLM 미사용, 빠름)
# ═══════════════════════════════════════════════════════════════════════════

def extract_terms(text: str) -> list[str]:
    """성경 구절 + 신학 용어 + 반복 등장 단어 추출.

    반환 예시:
        ["[성경구절] 요 3:16", "[신학용어] 십자가 (5회)", "[반복용어] 하나님의사랑 (4회)"]
    """
    found: list[str] = []

    # 성경 구절
    scriptures = set(_SCRIPTURE_PATTERN.findall(text))
    found.extend(sorted(f"[성경구절] {s.strip()}" for s in scriptures))

    # 신학 용어 (등장 횟수 포함)
    for term in _THEOLOGY_TERMS:
        count = text.count(term)
        if count > 0:
            found.append(f"[신학용어] {term} ({count}회)")

    # 반복 등장 한글 단어 (5글자 이상, 3회 이상, 신학 용어 제외)
    words = re.findall(r"[가-힣]{5,}", text)
    freq = Counter(words)
    for word, cnt in freq.most_common(15):
        if cnt >= 3 and word not in _THEOLOGY_TERMS:
            found.append(f"[반복용어] {word} ({cnt}회)")

    return found


def extract_metadata(text: str) -> dict:
    """검색 boost·필터링용 깨끗한 메타데이터 추출 (라벨 없는 순수 리스트).

    extract_terms() 는 표시용 라벨 문자열("[성경구절] 요 3:16")을 반환하지만,
    이 함수는 retriever boost matrix·필터에 바로 쓸 수 있는 정규화된 값을 반환한다.

    반환:
        {
          "scripture_refs": ["요 3:16", "로마서 5:8"],   # 정규화된 성경 구절
          "topic_tags": ["십자가", "은혜", "구원"],        # 본문 등장 신학 용어 (빈도순)
        }
    """
    # 성경 구절 — 공백 정규화 + 66권 화이트리스트 검증 + 중복 제거 (등장 순서 보존)
    refs: list[str] = []
    seen_refs: set[str] = set()
    for raw in _SCRIPTURE_PATTERN.findall(text):
        ref = re.sub(r"\s+", " ", raw).strip().rstrip(",").strip()
        if ref and ref not in seen_refs and _is_valid_scripture(ref):
            seen_refs.add(ref)
            refs.append(ref)

    # 주제어 — 본문에 실제 등장하는 신학 용어를 빈도순 정렬 (상위 12개)
    tag_counts: list[tuple[str, int]] = []
    for term in _THEOLOGY_TERMS:
        cnt = text.count(term)
        if cnt > 0:
            tag_counts.append((term, cnt))
    tag_counts.sort(key=lambda x: x[1], reverse=True)
    tags = [t for t, _ in tag_counts[:12]]

    return {"scripture_refs": refs, "topic_tags": tags}


# ═══════════════════════════════════════════════════════════════════════════
# 하위 호환 API (documents.py /cleanup 엔드포인트가 호출)
# ═══════════════════════════════════════════════════════════════════════════

async def run_cleanup(
    text: str,
    stages: list[int] | None = None,
) -> CleanupResult:
    """텍스트 변경 없이 용어만 추출. stages 인자는 무시 (하위 호환 유지)."""
    terms = extract_terms(text)
    return CleanupResult(
        original_text=text,
        final_text=text,   # 원본 그대로 — 수정 없음
        terms_found=terms,
    )
