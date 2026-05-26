"""한국어 친화 청킹.
- kss(한국어 문장 분리기)로 문장 경계 보존
- 문장 단위로 모아 chunk_size 토큰 근처에서 자름
- chunk_overlap 만큼 다음 청크에 이어붙임
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass
class Chunk:
    text: str
    chunk_id: int
    char_start: int
    char_end: int


def split_korean_sentences(text: str) -> list[str]:
    """kss로 한국어 문장 분리. kss 미설치/오류 시 fallback."""
    try:
        import kss
        return [s.strip() for s in kss.split_sentences(text) if s.strip()]
    except Exception:
        # fallback: 단순 마침표/줄바꿈 기준
        import re
        parts = re.split(r"(?<=[.!?。…?!])\s+|\n{2,}", text)
        return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    *,
    chunk_size: int = 500,         # 글자수 기준 (한국어는 글자수 ≈ 토큰수의 0.5~0.7배)
    chunk_overlap: int = 80,
) -> list[Chunk]:
    """문장 보존 청킹."""
    sents = split_korean_sentences(text)
    if not sents:
        return []

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_len = 0
    char_cursor = 0
    chunk_id = 0

    def flush(start_offset: int):
        nonlocal chunk_id
        if not buf:
            return
        joined = " ".join(buf)
        chunks.append(Chunk(
            text=joined,
            chunk_id=chunk_id,
            char_start=start_offset,
            char_end=start_offset + len(joined),
        ))
        chunk_id += 1

    chunk_start = 0
    for s in sents:
        if buf_len + len(s) + 1 > chunk_size and buf:
            flush(chunk_start)
            # overlap: 마지막 일부 문장을 다음 chunk 앞에 둠
            if chunk_overlap > 0:
                back = []
                acc = 0
                for prev in reversed(buf):
                    if acc + len(prev) > chunk_overlap:
                        break
                    back.append(prev); acc += len(prev) + 1
                back.reverse()
                buf = back
                buf_len = sum(len(b) for b in buf) + max(len(buf) - 1, 0)
                chunk_start = char_cursor - buf_len
            else:
                buf, buf_len = [], 0
                chunk_start = char_cursor

        buf.append(s)
        buf_len += len(s) + 1
        char_cursor += len(s) + 1

    flush(chunk_start)
    return chunks


def chunk_documents(docs: Iterable[tuple[str, dict]], **kw) -> list[tuple[Chunk, dict]]:
    """여러 문서를 한 번에 청킹. (text, metadata) → [(chunk, metadata_with_chunk_id), ...]"""
    out: list[tuple[Chunk, dict]] = []
    for text, meta in docs:
        for ch in chunk_text(text, **kw):
            m = dict(meta)
            m["chunk_id"] = ch.chunk_id
            m["char_start"] = ch.char_start
            m["char_end"] = ch.char_end
            out.append((ch, m))
    return out
