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
from dataclasses import dataclass, field

from ..config import settings


# ── 토큰 추정 ────────────────────────────────────────────────────────────────
# 한국어는 형태소 기반 토크나이저에서 글자수 대비 토큰수가 0.5~0.7배.
# 보수적으로 0.55 를 곱해 추정 (정확 계산은 임베더 토크나이저 필요하나, 청킹엔 추정으로 충분).
_TOKEN_RATIO = 0.55


def estimate_tokens(text: str) -> int:
    """글자수 기반 토큰 추정 (한국어 휴리스틱)."""
    return max(1, int(len(text) * _TOKEN_RATIO))


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
def split_korean_sentences(text: str) -> list[str]:
    """kss로 한국어 문장 분리. kss 미설치/오류/대용량 시 regex fallback.

    kss는 C++ MeCab 없이 pecab 백엔드 사용 시 대용량 텍스트에서 수분 걸릴 수 있음.
    5,000자 이상 텍스트는 빠른 regex 분리를 사용.
    """
    def _regex_split(t: str) -> list[str]:
        # \s* : 한국어는 "은혜입니다.그러므로" 처럼 문장 종결 후 공백 없이
        #       바로 다음 문장이 시작되는 경우가 많으므로 공백 선택적 처리.
        parts = re.split(r"(?<=[.!?。…?!])\s*|\n{2,}", t)
        return [p.strip() for p in parts if p.strip()]

    if len(text) > 5000:
        return _regex_split(text)

    try:
        import kss
        return [s.strip() for s in kss.split_sentences(text) if s.strip()]
    except Exception:
        return _regex_split(text)


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
                _flush()
                if overlap_sentences > 0:
                    tail = buf[-overlap_sentences:]
                    buf = list(tail)
                    buf_tokens = sum(estimate_tokens(t) for t in buf)
                else:
                    buf, buf_tokens = [], 0

            buf.append(s)
            buf_tokens += s_tokens

        _flush()

    # 부스러기 병합 + chunk_id 재정렬
    merged = _merge_tiny_chunks(raw_chunks, soft_min, hard_max)
    for i, c in enumerate(merged):
        c.chunk_id = i
    return merged


def _split_long_sentence(sentence: str, max_tokens: int) -> list[str]:
    """hard_max 초과하는 초장문 문장을 토큰 한도 내 조각으로 분할 (어절 경계)."""
    max_chars = int(max_tokens / _TOKEN_RATIO)
    words = sentence.split(" ")
    pieces: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for w in words:
        if cur and cur_len + len(w) + 1 > max_chars:
            pieces.append(" ".join(cur))
            cur, cur_len = [], 0
        cur.append(w)
        cur_len += len(w) + 1
    if cur:
        pieces.append(" ".join(cur))
    return pieces or [sentence]


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
