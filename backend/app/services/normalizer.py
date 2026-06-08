"""정규화 — 구어체 필러·반복어 제거 + 성경표기 통일 (Stage 1).

규칙 기반(LLM 무관)이라 빠르고 안전. 의미를 절대 바꾸지 않는다.
구조화(Stage 2, LLM) 이전에 입력을 깨끗하게 만들어 LLM 품질·비용을 개선한다.

사용:
    from .normalizer import normalize_text
    clean = normalize_text(raw)
"""
from __future__ import annotations

import re


# ── 구어체 필러 (설교/강의 transcript 특유) ──────────────────────────────────
# 단독으로 쓰인 추임새만 제거 (단어 일부가 아닌 경계 기준)
_FILLER_WORDS = [
    "어", "음", "아", "그", "저", "뭐", "이제", "막", "좀", "딱", "그냥",
    "인제", "그래가지고", "그러니까", "뭐랄까", "뭐냐", "에",
]
# "어...", "음..", "그~" 형태 (말줄임표·물결 동반)
_FILLER_TRAIL_RE = re.compile(
    r"(?:^|(?<=\s))(?:" + "|".join(map(re.escape, _FILLER_WORDS)) + r")(?:[.…~]{2,}|\s*~+)\s*"
)

# 연속 반복 어절: "진짜 진짜 진짜" → "진짜"
_REPEAT_WORD_RE = re.compile(r"\b(\S{1,10})(?:\s+\1\b){1,}")


# ── 한글 성경 표기 정규화 ────────────────────────────────────────────────────
# "요한복음 삼장 십육절" → "요한복음 3:16"
_KOR_NUM = {
    "영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5,
    "육": 6, "칠": 7, "팔": 8, "구": 9, "십": 10,
}


def _kor_to_int(token: str) -> int | None:
    """간단한 한글 수사 → 정수 (1~99 범위, 설교 성경 인용 수준)."""
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    # 십 단위 처리: 십육=16, 이십삼=23, 삼십=30
    total = 0
    if "십" in token:
        parts = token.split("십")
        tens_part = parts[0]
        ones_part = parts[1] if len(parts) > 1 else ""
        tens = _KOR_NUM.get(tens_part, 1) if tens_part else 1
        ones = _KOR_NUM.get(ones_part, 0) if ones_part else 0
        total = tens * 10 + ones
    else:
        if token in _KOR_NUM:
            total = _KOR_NUM[token]
        else:
            return None
    return total if total > 0 else None


_SCRIPTURE_KOR_RE = re.compile(
    r"([가-힣]{1,8})\s*([영공일이삼사오육칠팔구십\d]{1,4})\s*장\s*"
    r"([영공일이삼사오육칠팔구십\d]{1,4})\s*절"
)


def _replace_kor_scripture(m: re.Match) -> str:
    book = m.group(1)
    chap = _kor_to_int(m.group(2))
    verse = _kor_to_int(m.group(3))
    if chap is None or verse is None:
        return m.group(0)  # 변환 실패 시 원문 유지
    return f"{book} {chap}:{verse}"


# ── 공백·줄바꿈 정규화 ───────────────────────────────────────────────────────
def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)        # 다중 공백 → 1
    text = re.sub(r" *\n *", "\n", text)        # 줄 끝/시작 공백 제거
    text = re.sub(r"\n{3,}", "\n\n", text)      # 3줄+ → 2줄
    return text.strip()


def normalize_text(text: str, *, remove_fillers: bool = True) -> str:
    """전체 정규화 파이프라인 적용.

    Args:
        remove_fillers: 구어체 필러·반복어 제거 여부 (설교는 True 권장)
    """
    if not text:
        return ""

    # 1) 한글 성경표기 → 숫자표기
    text = _SCRIPTURE_KOR_RE.sub(_replace_kor_scripture, text)

    # 2) 구어체 정리 (옵션)
    if remove_fillers:
        text = _FILLER_TRAIL_RE.sub("", text)
        text = _REPEAT_WORD_RE.sub(r"\1", text)

    # 3) 공백·줄바꿈
    text = _normalize_whitespace(text)
    return text
