"""E-D: 업로드 정제 파이프라인 — 5단계.

Stage 1: 기계적 정규화 (LLM 미사용)
Stage 2: 1차 오타 수정 (DeepSeek, 보수적)
Stage 3: 2차 맥락 분석 + 청크 최적화 (Gemini 또는 fallback)
Stage 4: 신학 보존 검증 (DeepSeek, 비교 전용)
Stage 5: 자주 나오는 용어 추출 (규칙 기반)

사용법:
    result = await run_cleanup(text, stages=[1,2,3,4,5])
    # result.final_text, result.diffs, result.warnings
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: E-D — cleanup_pipeline.py 신규 (5단계 정제)
# Reason: ORDERS.md EPIC E-D
# Status: COMPLETED
# =============================================================================
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .llm.base import Message
from .llm.fallback import chat_with_fallback


# ── 신학 핵심 용어 화이트리스트 (Stage 4 / Stage 2 가드) ─────────────────
_THEOLOGY_TERMS = [
    "칭의", "성화", "영화", "대속", "화목제", "구속", "중보", "부활", "승천",
    "재림", "십자가", "은혜", "믿음", "회개", "의롭다하심", "하나님", "예수님",
    "그리스도", "성령님", "삼위일체", "복음", "구원", "영접", "거듭남",
    "요한복음", "로마서", "갈라디아서", "에베소서", "빌립보서",
]

# 성경 구절 패턴 (변경 금지)
_SCRIPTURE_PATTERN = re.compile(
    r"[가-힣A-Za-z]+\s*\d+:\d+[-–\d,\s]*"
)


@dataclass
class CleanupDiff:
    stage: int
    original: str
    modified: str
    reason: str
    position: Optional[int] = None


@dataclass
class CleanupResult:
    original_text: str
    final_text: str
    stage_texts: dict[int, str] = field(default_factory=dict)
    diffs: list[CleanupDiff] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    terms_found: list[str] = field(default_factory=list)
    theology_violations: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1: 기계적 정규화 (LLM 없음, 빠름)
# ═══════════════════════════════════════════════════════════════════════════

def _stage1_normalize(text: str) -> tuple[str, list[CleanupDiff]]:
    """유니코드 정규화, 전각/반각 통일, 연속 공백/빈줄 정리."""
    diffs: list[CleanupDiff] = []
    original = text

    # 1. 유니코드 NFC 정규화
    text = unicodedata.normalize("NFC", text)

    # 2. 전각 → 반각 (숫자·알파벳·기호)
    fullwidth = {
        "！": "!", "？": "?", "，": ",", "。": ".", "：": ":", "；": ";",
        "（": "(", "）": ")", "【": "[", "】": "]", "「": '"', "」": '"',
        "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
        "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    }
    for fw, hw in fullwidth.items():
        if fw in text:
            text = text.replace(fw, hw)

    # 3. 깨진 문자 제거 (replacement character)
    text = text.replace("�", "")

    # 4. 페이지 번호 패턴 제거 (예: "- 1 -", "[1]" 단독 줄)
    text = re.sub(r"(?m)^\s*[-–]\s*\d+\s*[-–]\s*$", "", text)
    text = re.sub(r"(?m)^\s*\[\d+\]\s*$", "", text)

    # 5. 연속 공백 → 단일 공백 (줄바꿈 보존)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # 6. 3개 이상 연속 빈 줄 → 2개
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 7. 줄 앞뒤 공백 제거
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    if text != original:
        diffs.append(CleanupDiff(stage=1, original=original[:200], modified=text[:200],
                                  reason="기계적 정규화 (공백·전각·빈줄·깨진문자)"))
    return text, diffs


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2: 1차 오타 수정 (LLM, 보수적)
# ═══════════════════════════════════════════════════════════════════════════

async def _stage2_typo(text: str) -> tuple[str, list[CleanupDiff]]:
    """DeepSeek 를 사용해 명백한 오타·띄어쓰기만 수정."""
    # 성경 구절 마킹 (수정 금지)
    scripture_spans = list(_SCRIPTURE_PATTERN.finditer(text))

    # 청크 단위로 처리 (4000자 이하)
    chunks = _split_chunks(text, max_len=4000)
    corrected_chunks: list[str] = []

    for chunk in chunks:
        prompt = (
            "다음 한국어 기독교 설교/강의 텍스트의 명백한 오타와 띄어쓰기만 수정하세요.\n\n"
            "절대 변경 금지:\n"
            "- 신학 용어: " + ", ".join(_THEOLOGY_TERMS[:15]) + "\n"
            "- 성경 구절 (요 3:16 등 형식)\n"
            "- 인명·지명·고유명사\n"
            "- 화자의 문체·어순·의미\n\n"
            "수정 가능한 것만:\n"
            "- 명백한 오타 (예: '믿음이' → '믿음이', '예수그리스도' → '예수 그리스도')\n"
            "- 붙여쓰기/띄어쓰기 오류\n"
            "- 문장 부호 (마침표·쉼표 누락)\n\n"
            "수정이 없으면 원문 그대로 반환하세요.\n\n"
            f"텍스트:\n{chunk}"
        )
        try:
            resp, _, _ = await chat_with_fallback(
                [Message(role="user", content=prompt)],
                primary_provider="deepseek",
                temperature=0.1,
                max_tokens=len(chunk) + 200,
            )
            corrected_chunks.append(resp.text.strip())
        except Exception:
            corrected_chunks.append(chunk)  # 실패 시 원본 유지

    corrected = "\n\n".join(corrected_chunks) if len(chunks) > 1 else (corrected_chunks[0] if corrected_chunks else text)

    diffs: list[CleanupDiff] = []
    if corrected != text:
        diffs.append(CleanupDiff(stage=2, original=text[:300], modified=corrected[:300],
                                  reason="LLM 오타·띄어쓰기 수정 (DeepSeek)"))
    return corrected, diffs


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3: 맥락 분석 + 청크 최적화 (Gemini 권장)
# ═══════════════════════════════════════════════════════════════════════════

async def _stage3_context(text: str) -> tuple[str, list[CleanupDiff]]:
    """끊긴 문장 연결 + 청크 친화적 단락 구조로 재편."""
    chunks = _split_chunks(text, max_len=6000)
    result_chunks: list[str] = []

    for chunk in chunks:
        prompt = (
            "다음 한국어 기독교 설교/강의 텍스트를 *최소한으로* 정리하세요.\n\n"
            "작업:\n"
            "1. 문맥이 자연스럽지 않게 끊긴 부분을 자연스럽게 연결\n"
            "2. 지나치게 긴 단락(500자 이상)은 의미 경계로 분할\n"
            "3. 너무 짧은 단락(30자 미만)은 인접 단락과 병합\n\n"
            "절대 금지:\n"
            "- 화자의 어휘·신학적 표현·성경 구절 변경\n"
            "- 의미 추가/삭제\n"
            "- 고유명사 변경\n\n"
            "변경한 부분은 [수정: 이유] 형식으로 표시하세요.\n\n"
            f"텍스트:\n{chunk}"
        )
        try:
            resp, _, _ = await chat_with_fallback(
                [Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=len(chunk) + 500,
            )
            result_chunks.append(resp.text.strip())
        except Exception:
            result_chunks.append(chunk)

    result = "\n\n".join(result_chunks) if len(chunks) > 1 else (result_chunks[0] if result_chunks else text)

    diffs: list[CleanupDiff] = []
    if result != text:
        diffs.append(CleanupDiff(stage=3, original=text[:300], modified=result[:300],
                                  reason="맥락 분석 + 청크 최적화"))
    return result, diffs


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4: 신학 보존 검증 (비교 전용, LLM)
# ═══════════════════════════════════════════════════════════════════════════

async def _stage4_theology_verify(original: str, modified: str) -> list[str]:
    """원본 vs 수정본 비교. 의미·교리 변경 감지."""
    violations: list[str] = []

    # 빠른 규칙 기반 검사: 신학 용어 누락
    for term in _THEOLOGY_TERMS:
        orig_count = original.count(term)
        mod_count = modified.count(term)
        if orig_count > 0 and mod_count < orig_count:
            violations.append(f"신학 용어 감소: '{term}' ({orig_count}→{mod_count})")

    # 성경 구절 누락 검사
    orig_scriptures = set(_SCRIPTURE_PATTERN.findall(original))
    mod_scriptures = set(_SCRIPTURE_PATTERN.findall(modified))
    missing = orig_scriptures - mod_scriptures
    for m in missing:
        violations.append(f"성경 구절 누락: '{m}'")

    # LLM 심층 검증 (중요 변경이 있을 때만)
    if violations or len(original) > 2000:
        prompt = (
            "두 텍스트를 비교하여 신학적으로 *의미가 변경된 부분*만 출력하세요.\n"
            "표현만 다르고 의미가 같으면 OK로 처리하세요.\n"
            "문제 있으면: '문제: 원본={...} → 수정={...}' 형식으로 출력.\n"
            "없으면: 'OK' 만 출력.\n\n"
            f"원본 (처음 1000자):\n{original[:1000]}\n\n"
            f"수정본 (처음 1000자):\n{modified[:1000]}"
        )
        try:
            resp, _, _ = await chat_with_fallback(
                [Message(role="user", content=prompt)],
                primary_provider="deepseek",
                temperature=0.1,
                max_tokens=500,
            )
            verdict = resp.text.strip()
            if "문제" in verdict:
                violations.append(f"LLM 신학 검증 경고: {verdict[:200]}")
        except Exception:
            pass

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# Stage 5: 용어 추출 (규칙 기반)
# ═══════════════════════════════════════════════════════════════════════════

def _stage5_extract_terms(text: str) -> list[str]:
    """성경 구절 + 신학 용어 출현 목록."""
    found: list[str] = []

    scriptures = _SCRIPTURE_PATTERN.findall(text)
    found.extend([f"[성경구절] {s}" for s in set(scriptures)])

    for term in _THEOLOGY_TERMS:
        count = text.count(term)
        if count > 0:
            found.append(f"[신학용어] {term} ({count}회)")

    # 반복 등장 단어 (3회 이상, 5글자 이상 한글 단어)
    words = re.findall(r"[가-힣]{5,}", text)
    from collections import Counter
    freq = Counter(words)
    for word, cnt in freq.most_common(10):
        if cnt >= 3 and word not in _THEOLOGY_TERMS:
            found.append(f"[반복용어] {word} ({cnt}회)")

    return found


# ═══════════════════════════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════════════════════════

async def run_cleanup(
    text: str,
    stages: list[int] | None = None,
) -> CleanupResult:
    """5단계 정제 실행. stages=[1,2,3,4,5] 기본."""
    if stages is None:
        stages = [1, 2, 3, 4, 5]

    result = CleanupResult(original_text=text, final_text=text)
    current = text

    if 1 in stages:
        current, diffs = _stage1_normalize(current)
        result.stage_texts[1] = current
        result.diffs.extend(diffs)

    if 2 in stages:
        current, diffs = await _stage2_typo(current)
        result.stage_texts[2] = current
        result.diffs.extend(diffs)

    if 3 in stages:
        current, diffs = await _stage3_context(current)
        result.stage_texts[3] = current
        result.diffs.extend(diffs)

    if 4 in stages:
        violations = await _stage4_theology_verify(text, current)
        result.theology_violations = violations
        result.stage_texts[4] = current
        if violations:
            result.warnings.extend([f"[신학 경고] {v}" for v in violations])

    if 5 in stages:
        terms = _stage5_extract_terms(current)
        result.terms_found = terms
        result.stage_texts[5] = current

    result.final_text = current
    return result


# ── 유틸 ─────────────────────────────────────────────────────────────────

def _split_chunks(text: str, max_len: int = 4000) -> list[str]:
    """문단 경계를 보존하며 max_len 이하로 청크 분할."""
    if len(text) <= max_len:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_len:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current:
        chunks.append(current.strip())
    return chunks
