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


# ── ZZ-1 / ZZ-3: 청킹 선행 정규화 (Stage 0.5) ─────────────────────────────────
# STT 설교 원고는 단어 중간 띄어쓰기 오염 + 문장부호 부재가 심각.
# 인제스트·청킹 직전에 한 번 더 정규화해 임베딩/검색 품질을 높인다.
# (의미 보존 원칙: 조사/어미 경계만 다루며 내용을 바꾸지 않음)

# ZZ-1: 흔히 붙여 쓰이는 복합어·조사 패턴 (하이픈/붙임 → 분리)
_ZZ_COMMON_SPLITS = [
    ("말씀-", "말씀 "), ("하나님-", "하나님 "), ("예수-", "예수 "),
    ("성경-", "성경 "), ("신앙-", "신앙 "), ("교회-", "교회 "),
    ("기독교-", "기독교 "), ("복음-", "복음 "), ("은혜-", "은혜 "),
    ("사랑-", "사랑 "), ("기도-", "기도 "), ("죄-", "죄 "),
    ("구원-", "구원 "), ("믿음-", "믿음 "), ("소망-", "소망 "),
    ("감사-", "감사 "), ("용서-", "용서 "), ("찬양-", "찬양 "),
    ("성령-", "성령 "), ("주님-", "주님 "),
    ("하나님의", "하나님의 "), ("예수님의", "예수님의 "), ("말씀의", "말씀의 "),
    ("말씀을", "말씀을 "), ("하나님을", "하나님을 "), ("예수를", "예수를 "),
    ("은혜를", "은혜를 "), ("사람을", "사람을 "), ("세상을", "세상을 "),
    ("마음을", "마음을 "), ("우리를", "우리를 "), ("그들을", "그들을 "),
    ("하나님이", "하나님이 "), ("예수님이", "예수님이 "), ("말씀이", "말씀이 "),
    ("은혜가", "은혜가 "), ("사랑이", "사랑이 "), ("기도가", "기도가 "),
    ("믿음이", "믿음이 "), ("사람이", "사람이 "), ("세상이", "세상이 "),
    ("마음이", "마음이 "), ("우리가", "우리가 "), ("그들이", "그들이 "),
    ("하나님과", "하나님과 "), ("예수님과", "예수님과 "), ("말씀과", "말씀과 "),
    ("은혜와", "은혜와 "), ("사랑과", "사랑과 "), ("기도와", "기도와 "),
    ("믿음과", "믿음과 "), ("사람과", "사람과 "), ("세상과", "세상과 "),
    ("우리와", "우리와 "), ("그들과", "그들과 "),
]

# ZZ-3: 문장 종결 패턴 뒤 마침표 추정 (무부호 STT 보완)
_ZZ_BOUNDARY_WORDS = [
    "습니다", "합니다", "입니다", "보입니다", "됩니다", "드립니다", "받습니다",
    "나옵니다", "이루어집니다", "바랍니다", "원합니다", "기도합니다", "말합니다",
    "생각합니다", "좋습니다", "것입니다", "때입니다", "곳입니다",
    "분입니다", "중입니다", "후입니다", "예요", "이에요", "이죠", "하죠",
    "그러죠", "맞죠", "되죠", "해요", "그래요", "맞아요", "그럼요",
    "한다", "하다", "된다", "있다", "없다", "했다", "까요", "나요", "할까요",
]
_ZZ_BOUNDARY_RE = re.compile(
    r"(" + "|".join(_ZZ_BOUNDARY_WORDS) + r")\s*(?=[\s가-힣])"
)
# '다/요/죠'로 끝나고 바로 한국어 단어가 이어지면 마침표 삽입
# ('까/지' 는 '까지' 등에서 오탐이 많아 제외)
_ZZ_TAIL_RE = re.compile(r"(다|요|죠)(?=\s+[가-힣])")

_PARTICLES = r"(은|는|이|가|을|를|에|의|와|과|도|로|으로|에서|에게|만|까지|부터|보다|께|처럼|마저|조차|이나|거나|든지)"
# 공백 문자 클래스 (백슬래시 이스케이프 없이 조립 - raw string 오탐 방지)
_WS_CLASS = " " + chr(9) + chr(10) + chr(13)
_WORD_SPACING_RE = re.compile(
    "([가-힣]{2,})[" + _WS_CLASS + "]+(" + _PARTICLES + ")(?=[" + _WS_CLASS + "]|[.,!?]|$)"
)


def fix_word_spacing(text: str) -> str:
    """ZZ-1: 단어 중간 띄어쓰기·붙임 복원 (조사 경계만 다룸).

    '하나님 의' → '하나님 의'(단일 공백), '말씀-은' → '말씀 은'.
    내용을 바꾸지 않고 공백만 정돈한다.
    """
    if not text:
        return ""
    for wrong, right in _ZZ_COMMON_SPLITS:
        if wrong in text:
            text = text.replace(wrong, right)
    text = _WORD_SPACING_RE.sub(r"\1 \2", text)
    return text


def estimate_sentence_boundaries(text: str) -> str:
    """ZZ-3: STT 무부호 원고에 문장 끝 마침표를 추정 삽입.

    종결어미/조사 뒤에 바로 한국어 단어가 오면 마침표를 넣어
    뒤이은 문장분리가 정상 동작하도록 한다. 이미 부호가 있으면 무시.
    """
    if not text:
        return ""
    text = _ZZ_BOUNDARY_RE.sub(lambda m: m.group(0).rstrip() + ". ", text)
    text = _ZZ_TAIL_RE.sub(r"\1. ", text)
    text = re.sub(r"\.{2,}", ".", text)          # 연속 마침표 정리
    text = re.sub(r"\s*\.\s*", ". ", text)        # 마침표 뒤 정규 공백
    return text


def preprocess_for_chunking(text: str) -> str:
    """Stage 0.5: 청킹 직전 정규화 (ZZ-1 단어결합 + ZZ-3 마침표 + 공백)."""
    if not text:
        return ""
    text = _normalize_whitespace(text)
    text = fix_word_spacing(text)
    text = estimate_sentence_boundaries(text)
    # ZZ-1(fix_word_spacing)이 이미 공백이 있는 단어 뒤에도 무조건 공백을 추가해
    # 이중 공백("하나님이  세상을")이 생기므로, 마지막에 한 번 더 정리한다.
    text = _normalize_whitespace(text)
    return text
