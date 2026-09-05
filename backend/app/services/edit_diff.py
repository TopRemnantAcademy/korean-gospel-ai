"""편집 diff 생성 서비스 — 텍스트 비교 + 변경 요약 + 성경구절 감지.

설계 문서 §12.11 기반 구현.
"""

from __future__ import annotations

import difflib
import re
from typing import Optional

# ── 성경 책 이름 패턴 (한글) ──
_BIBLE_BOOKS = (
    r"(?:마태|마가|누가|요한|요한복음|로마서|고린도전서|고린도후서|갈라디아서|에베소서|빌립보서|골로새서"
    r"|데살로니가전서|데살로니가후서|디모데전서|디모데후서|디도서|빌레몬서|히브리서"
    r"|야고보서|베드로전서|베드로후서|요한일서|요한이서|요한삼서|유다서|요한계시록"
    r"|창세기|출애굽기|레위기|민수기|신명기|여호수아|사사기|룻기|사무엘상|사무엘하"
    r"|열왕기상|열왕기하|역대상|역대하|에스라|느헤미야|에스더|욥기|시편|잠언|전도서|아가"
    r"|이사야|예레미야|예레미야애가|에스겔|다니엘|호세아|요엘|아모스|오바댜|요나|미가"
    r"|나훔|하박국|스바냐|학개|스가랴|말라기)"
)

_BIBLE_PATTERN = re.compile(_BIBLE_BOOKS + r"\s*\d+:\d+")

# ── 긴 성경 책 약어 ──
_BIBLE_SHORT = {
    "요": "요한복음", "마": "마태복음", "막": "마가복음", "눅": "누가복음",
    "롬": "로마서", "고전": "고린도전서", "고후": "고린도후서", "갈": "갈라디아서",
    "엡": "에베소서", "빌": "빌립보서", "골": "골로새서",
    "살전": "데살로니가전서", "살후": "데살로니가후서",
    "딤전": "디모데전서", "딤후": "디모데후서", "딛": "디도서",
    "몬": "빌레몬서", "히": "히브리서", "약": "야고보서",
    "벧전": "베드로전서", "벧후": "베드로후서",
    "요일": "요한일서", "요이": "요한이서", "요삼": "요한삼서",
    "유": "유다서", "계": "요한계시록",
    "창": "창세기", "출": "출애굽기", "레": "레위기", "민": "민수기",
    "신": "신명기", "수": "여호수아", "삿": "사사기", "룻": "룻기",
    "삼상": "사무엘상", "삼하": "사무엘하", "왕상": "열왕기상", "왕하": "열왕기하",
    "대상": "역대상", "대하": "역대하", "스": "에스라", "느": "느헤미야",
    "에": "에스더", "욥": "욥기", "시": "시편", "잠": "잠언",
    "전": "전도서", "아": "아가", "사": "이사야", "렘": "예레미야",
    "애": "예레미야애가", "겔": "에스겔", "단": "다니엘",
    "호": "호세아", "욜": "요엘", "암": "아모스", "옵": "오바댜",
    "욘": "요나", "미": "미가", "나": "나훔", "합": "하박국",
    "습": "스바냐", "학": "학개", "슥": "스가랴", "말": "말라기",
}

# 약어 패턴 (예: "요 8:11", "롬 8:1-2")
_SHORT_PATTERN = re.compile(
    r"(" + "|".join(re.escape(k) for k in _BIBLE_SHORT) + r")\s*\d+[:\.]\d+"
)


def compute_diff(old_text: Optional[str], new_text: Optional[str]) -> dict:
    """두 텍스트의 diff를 생성하고 변경 요약을 반환.

    Returns:
        {
            "changed": bool,
            "added_chars": int,
            "removed_chars": int,
            "changed_sentences": int,
            "summary": str,
            "added_bible_refs": list[str],
            "inline_diff_html": Optional[str],
        }
    """
    if old_text is None:
        old_text = ""
    if new_text is None:
        new_text = ""

    # 문장 단위 분리
    old_sentences = _split_sentences(old_text)
    new_sentences = _split_sentences(new_text)

    # diff
    matcher = difflib.SequenceMatcher(None, old_sentences, new_sentences)
    changed_sentences = sum(
        1 for tag, _, _, _, _ in matcher.get_opcodes() if tag != "equal"
    )

    # 성경 구절 감지
    old_refs = _extract_bible_refs(old_text)
    new_refs = _extract_bible_refs(new_text)
    added_bible_refs = [r for r in new_refs if r not in old_refs]

    char_diff = len(new_text) - len(old_text)

    parts = []
    if changed_sentences > 0:
        parts.append(f"{changed_sentences}문장 수정")
    if char_diff > 0:
        parts.append(f"{char_diff}자 증가")
    elif char_diff < 0:
        parts.append(f"{-char_diff}자 감소")
    if added_bible_refs:
        parts.append(f"성경 구절 {len(added_bible_refs)}건 추가 ({', '.join(added_bible_refs[:3])})")

    return {
        "changed": old_text != new_text,
        "added_chars": max(0, char_diff),
        "removed_chars": max(0, -char_diff),
        "changed_sentences": changed_sentences,
        "summary": ", ".join(parts) if parts else "변경 없음",
        "added_bible_refs": added_bible_refs,
        "inline_diff_html": _generate_html_diff(old_text, new_text),
    }


def _split_sentences(text: str) -> list[str]:
    """한국어 문장 분리 (마침표, 물음표, 느낌표 기준)."""
    # 한국어 종결어미 + 구두점 조합
    sentences = re.split(r"(?<=[.!?⋯…])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _extract_bible_refs(text: str) -> list[str]:
    """텍스트에서 성경 구절 참조를 추출."""
    refs = []
    # 전체 이름 패턴
    refs.extend(m.group(0).strip() for m in _BIBLE_PATTERN.finditer(text))
    # 약어 패턴
    for m in _SHORT_PATTERN.finditer(text):
        refs.append(m.group(0).strip())
    return sorted(set(refs))


def _generate_html_diff(old: str, new: str) -> Optional[str]:
    """HTML 기반 diff 생성."""
    if not old and not new:
        return None

    differ = difflib.HtmlDiff(wrapcolumn=60)
    return differ.make_table(
        old.splitlines() or [""],
        new.splitlines() or [""],
        context=True,
        numlines=2,
    )


def truncate_value(value: Optional[str], max_chars: int = 10000) -> tuple[Optional[str], Optional[str]]:
    """값을 최대 max_chars로 truncate하고 SHA-256 해시 반환.

    Returns:
        (truncated_value, sha256_hash_hex)
    """
    if value is None:
        return None, None

    import hashlib

    hash_hex = hashlib.sha256(value.encode("utf-8")).hexdigest()

    if len(value) <= max_chars:
        return value, hash_hex

    truncated = value[:max_chars] + "...[TRUNCATED]"
    return truncated, hash_hex
