"""한국어 친화 청킹 (토큰 기반 + 의미 경계 보존).

설계 목표 (docs/INGEST_PIPELINE_DESIGN.md Stage 3):
- 문장 경계 보존 → 청크가 문장 중간에서 끊기지 않음
- 토큰 기준 크기 관리 (KURE/BGE 임베더 512 토큰 한도 안전)
- 마크다운 헤딩(##)을 1순위 청크 경계로 (구조화 단계 산출물 활용)
- 부스러기(min 미만) 청크는 인접 청크에 병합
- overlap 은 문장 단위 (맥락 연속성)

하위 호환: Chunk.text / chunk_id / char_start / char_end 필드 유지.
추가 필드: token_estimate, section_title.
"""
from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)
from dataclasses import dataclass

from ..config import settings


# ── 토큰 추정 ────────────────────────────────────────────────────────────────
# 한국어는 형태소 기반 토크나이저에서 글자수 대비 토큰수가 0.5~0.7배.
# 보수적으로 0.55 를 곱해 추정 (정확 계산은 임베더 토크나이저 필요하나, 청킹엔 추정으로 충분).
_TOKEN_RATIO = 0.55

# 문자 종류별 토큰 비율 (실 토크나이저 로드 실패 시 폴백 추정용).
# 한글 ~0.55, ASCII(영문/숫자) ~0.25(4글자≈1토큰), 한자/기타 ~0.4.
# 기존 단일 0.55 는 "요 3:16" 같은 영문·숫자 혼용 청크에서 토큰을 과대 추정했다.
_ASCII_RE = re.compile(r"[A-Za-z0-9]")
_HANGUL_RE2 = re.compile(r"[가-힣]")

# 실제 임베더 토크나이저 캐시 (청킹은 발행 시점에만 실행 → 프로세스당 1회 로드 후 재사용)
_tokenizer_cache: dict[str, object] = {}


def _get_tokenizer():
    """로드된 임베더의 토크나이저 반환. 없거나 로드 실패 시 None (0.55 추정으로 폴백).

    get_embedder() 는 CachedEmbedder 래퍼를 반환하므로,
    실제 SentenceTransformer 모델은 .inner._model 에 있다. (취약점 3 수정)
    """
    if "tok" in _tokenizer_cache:
        return _tokenizer_cache["tok"]
    tok = None
    try:
        from .embedding.factory import get_embedder
        emb = get_embedder(getattr(settings, "embedder", "kure"))
        inner = getattr(emb, "inner", emb)
        model = getattr(inner, "_model", None)
        if model is not None and hasattr(model, "tokenizer"):
            tok = model.tokenizer
    except Exception:
        tok = None
    _tokenizer_cache["tok"] = tok
    return tok


def _fallback_token_estimate(text: str) -> int:
    """토크나이저 없을 때 문자 종류별 계수 기반 추정 (혼용 문자 오차 보정)."""
    hangul = len(_HANGUL_RE2.findall(text))
    ascii_n = len(_ASCII_RE.findall(text))
    other = max(0, len(text) - hangul - ascii_n)
    est = hangul * 0.55 + ascii_n * 0.25 + other * 0.4
    return max(1, int(est))


def estimate_tokens(text: str) -> int:
    """토큰 수 추정. 실제 토크나이저 우선, 폴백은 문자 종류별 계수 기반."""
    tok = _get_tokenizer()
    if tok is not None:
        try:
            ids = tok.encode(text)
            if hasattr(ids, "__len__"):
                return max(1, len(ids))
        except Exception as _e:
            logger.debug("tokenizer encode failed, falling back to ratio: %s", _e)
    return _fallback_token_estimate(text)


@dataclass
class Chunk:
    text: str
    chunk_id: int
    char_start: int
    char_end: int
    token_estimate: int = 0
    section_title: str = ""

    def __post_init__(self):
        if not self.token_estimate:
            self.token_estimate = estimate_tokens(self.text)


# ── 문장 분리 ────────────────────────────────────────────────────────────────
# kss(pecab 백엔드)는 한국어 대용량/다량 텍스트에서 수분~무한 지연됨 (Task O-1).
# 따라서 기본 문장분리는 빠른 regex 기반으로 하고, kss는 옵션으로 둔다.
# mecab 백엔드를 설치해 빠르게 쓰고 싶으면 True 로 켜도 되나, 배치(수백 문단)에는 비추천.
_USE_KSS = False

# 한국어 문장 종결 어미. 단일 음절(다/요/네/까/라/자/군 등)만으로 나누면
# "다락방/요한복음/이름/수고" 같은 단어 내부 음절에서 오분할되어 단어가 조각나므로,
# 반드시 "종결 어미 + 공백 + 다음 단어" 경계를 함께 요구한다.
# (기존 `(?<=[다까죠...])\s*` 는 `\s*` 가 0개 공백에도 매칭돼 단어 중간까지 쪼개는 치명 버그였음)
_KOR_SENT_ENDINGS = (
    r"습니다|합니다|입니다|입니까|합니까|었습니다|았습니다|였습니다|"
    r"어요|아요|여요|예요|이에요|에요|지요|네요|나요|까요|"
    r"니까|습니까|거예요|거에요|거야|"
    r"해요|했어요|했어|"
    r"다|요|죠|네|까|라|자|군|게|세|데|지"
)

# 문장부호(ZZ-3이 삽입한 마침표 포함) 뒤, 또는 종결 어미 뒤 + 공백 + 다음 단어 경계에서만 분리.
# re.split 은 캡처 그룹(구분자)을 유지하므로, 구분자를 앞 문장에 다시 붙여 종결 어미를 보존한다.
_SENT_SPLIT_RE = re.compile(
    r"([.!?。…?!]+\s*|\n{2,}|(?:" + _KOR_SENT_ENDINGS + r")(?=\s+[가-힣A-Za-z0-9(]))"
)


def _regex_split_sentences(t: str) -> list[str]:
    parts = _SENT_SPLIT_RE.split(t)
    sents: list[str] = []
    buf = ""
    for i, p in enumerate(parts):
        if p is None:
            continue
        if i % 2 == 0:
            buf += p
        else:
            buf += p          # 종결 어미/문장부호는 앞 문장에 붙임
            sents.append(buf)
            buf = ""
    if buf.strip():
        sents.append(buf)
    return [s.strip() for s in sents if s.strip()]


def split_korean_sentences(text: str) -> list[str]:
    """한국어 문장 분리.

    기본: 빠른 regex 기반 (kss pecab 지연 회피 — Task O-1).
    _USE_KSS=True 이고 kss 사용 가능하면 kss 적용(품질 우선, 소량에만 권장).
    """
    if _USE_KSS:
        try:
            import kss
            return [s.strip() for s in kss.split_sentences(text) if s.strip()]
        except Exception as _e:
            logger.debug("kss split failed, falling back to regex: %s", _e)
    return _regex_split_sentences(text)


# ── 헤딩 인식 분할 ───────────────────────────────────────────────────────────
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class _Section:
    title: str
    body: str


def split_sections(text: str) -> list[_Section]:
    """마크다운 헤딩(#~######)을 경계로 섹션 분리.

    헤딩이 없으면 전체를 단일 무제목 섹션으로 반환.
    구조화(Stage 2)를 거친 문서는 ## 헤딩이 있어 의미 단위로 분리된다.
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [_Section(title="", body=text.strip())]

    sections: list[_Section] = []
    # 첫 헤딩 이전 서두(있으면) → 무제목 섹션
    if matches[0].start() > 0:
        intro = text[: matches[0].start()].strip()
        if intro:
            sections.append(_Section(title="", body=intro))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body or title:
            sections.append(_Section(title=title, body=body))
    return sections


# ── 메인 청킹 ────────────────────────────────────────────────────────────────
def chunk_text(
    text: str,
    *,
    target_tokens: int | None = None,
    max_tokens: int | None = None,
    min_tokens: int | None = None,
    overlap_sentences: int = 1,
    # 하위 호환: 기존 호출부가 chunk_size/chunk_overlap(글자수)를 넘겨도 동작
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """문장 보존 + 토큰 기준 + 헤딩 인식 청킹.

    Args:
        target_tokens: 청크 목표 토큰 (기본 settings.ingest_chunk_target_tokens)
        max_tokens:    청크 최대 토큰 (초과 시 강제 분할)
        min_tokens:    이 미만 청크는 인접 청크에 병합
        overlap_sentences: 다음 청크 앞에 붙일 직전 문장 수
        chunk_size/chunk_overlap: (deprecated) 글자수 인자 — 토큰으로 환산
    """
    if not text or not text.strip():
        return []

    target = target_tokens or getattr(settings, "ingest_chunk_target_tokens", 350)
    hard_max = max_tokens or getattr(settings, "ingest_chunk_max_tokens", 512)
    soft_min = min_tokens or getattr(settings, "ingest_chunk_min_tokens", 50)

    # 하위 호환: 글자수 인자가 오면 토큰으로 환산
    if chunk_size is not None:
        target = estimate_tokens("x" * chunk_size)

    # chunk_overlap(글자수)은 본 구현에서 사용하지 않음 — overlap_sentences 가 권위 소스.
    # 넘겨도 조용히 무시되던 것을 경고로 표면화 (호출자 오인 방지).
    if chunk_overlap is not None:
        logger.warning(
            "chunk_text: chunk_overlap=%s 은(는) 무시됩니다. overlap_sentences 를 사용하세요.",
            chunk_overlap,
        )

    raw_chunks: list[Chunk] = []
    chunk_id = 0
    char_cursor = 0

    for section in split_sections(text):
        sents = split_korean_sentences(section.body)
        if not sents:
            continue

        buf: list[str] = []
        buf_tokens = 0

        def _flush():
            nonlocal chunk_id, char_cursor, buf, buf_tokens
            if not buf:
                return
            joined = " ".join(buf)
            raw_chunks.append(Chunk(
                text=joined,
                chunk_id=chunk_id,
                char_start=char_cursor,
                char_end=char_cursor + len(joined),
                token_estimate=estimate_tokens(joined),
                section_title=section.title,
            ))
            chunk_id += 1
            char_cursor += len(joined) + 1
            buf = []
            buf_tokens = 0

        for s in sents:
            s_tokens = estimate_tokens(s)

            # 단일 문장이 hard_max 초과 → 문장 자체를 토큰 단위로 강제 분할
            if s_tokens > hard_max:
                _flush()
                for piece in _split_long_sentence(s, hard_max):
                    raw_chunks.append(Chunk(
                        text=piece,
                        chunk_id=chunk_id,
                        char_start=char_cursor,
                        char_end=char_cursor + len(piece),
                        token_estimate=estimate_tokens(piece),
                        section_title=section.title,
                    ))
                    chunk_id += 1
                    char_cursor += len(piece) + 1
                continue

            # 현재 버퍼에 더하면 target 초과 → flush 후 overlap 유지
            if buf and buf_tokens + s_tokens > target:
                tail = buf[-overlap_sentences:] if overlap_sentences > 0 else []
                _flush()
                if tail:
                    buf = list(tail)
                    buf_tokens = sum(estimate_tokens(t) for t in buf)

            buf.append(s)
            buf_tokens += s_tokens

        _flush()

    # 부스러기 병합 + chunk_id 재정렬
    merged = _merge_tiny_chunks(raw_chunks, soft_min, hard_max)
    for i, c in enumerate(merged):
        c.chunk_id = i
    return merged


def _split_long_sentence(sentence: str, max_tokens: int) -> list[str]:
    """hard_max 초과하는 초장문 문장을 토큰 한도 내 조각으로 분할.

    1차: 공백(어절) 기반 분할. 2차: 공백이 없거나 1차가 실패하면 글자 수 기반으로
    강제 분할한다. (공백 없는 설교 transcript에서 512토큰 초과 청크 방지 — 취약점 2 수정)
    """
    max_chars = int(max_tokens / _TOKEN_RATIO)  # ≈ 931자

    # 1차: 공백(어절) 기반 분할
    words = sentence.split(" ")
    if len(words) > 1:
        pieces: list[str] = []
        cur: list[str] = []
        cur_len = 0
        for w in words:
            if cur and cur_len + len(w) + 1 > max_chars:
                pieces.append(" ".join(cur))
                cur, cur_len = [w], len(w)
            else:
                cur.append(w)
                cur_len += len(w) + 1
        if cur:
            pieces.append(" ".join(cur))
        if len(pieces) > 1:
            return pieces

    # 2차 폴백: 글자 수 기반 강제 분할 (공백이 없거나 1차 실패 시)
    if len(sentence) <= max_chars:
        return [sentence]
    pieces = [sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars)]
    return pieces if pieces else [sentence]


def _merge_tiny_chunks(chunks: list[Chunk], min_tokens: int, max_tokens: int) -> list[Chunk]:
    """min_tokens 미만 청크를 인접(같은 섹션 우선) 청크에 병합.

    병합 후 max_tokens 초과하지 않는 선에서만 합친다.
    """
    if not chunks:
        return []

    result: list[Chunk] = []
    for c in chunks:
        if (
            result
            and c.token_estimate < min_tokens
            and result[-1].section_title == c.section_title
            and result[-1].token_estimate + c.token_estimate <= max_tokens
        ):
            prev = result[-1]
            prev.text = prev.text + " " + c.text
            prev.char_end = c.char_end
            prev.token_estimate = estimate_tokens(prev.text)
        else:
            result.append(c)

    # 맨 앞 청크가 여전히 너무 작고 뒤에 합칠 수 있으면 한 번 더 시도
    if len(result) >= 2 and result[0].token_estimate < min_tokens:
        if result[0].token_estimate + result[1].token_estimate <= max_tokens:
            result[1].text = result[0].text + " " + result[1].text
            result[1].char_start = result[0].char_start
            result[1].token_estimate = estimate_tokens(result[1].text)
            result.pop(0)

    return result


# ── 다중 문서 청킹 (하위 호환) ───────────────────────────────────────────────
def chunk_documents(docs, **kw) -> list[tuple[Chunk, dict]]:
    """여러 문서를 한 번에 청킹. (text, metadata) → [(chunk, metadata_with_chunk_id), ...]"""
    out: list[tuple[Chunk, dict]] = []
    for text, meta in docs:
        for ch in chunk_text(text, **kw):
            m = dict(meta)
            m["chunk_id"] = ch.chunk_id
            m["char_start"] = ch.char_start
            m["char_end"] = ch.char_end
            m["token_estimate"] = ch.token_estimate
            m["section_title"] = ch.section_title
            out.append((ch, m))
    return out
