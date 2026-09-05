"""Enhanced RAG — 문서 청킹 (다중 포맷 로더 + 청킹 전략).

설계:
- 로더: txt/md(원문), json(리스트 또는 {"text"/"documents"}), csv(행 단위), raw
- 전략:
  - recursive : 기존 검증된 한국어 청킹(chunk_text) 재사용 — 문장/헤딩 경계 보존
  - fixed     : 문자 기준 슬라이딩 윈도우 + overlap (의존성 없이 동작)
  - semantic  : 문장 단위 누적 후 목표 토큰 도달 시 플러시
- 모든 전략은 doc_id 스코프의 content-addressed chunk_id 를 부여
  (같은 본문 → 같은 id → 재인제스트 시 안정적, 향후 부분 갱신 기반).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json

from ..chunker import (
    chunk_text as _ko_chunk_text,
    estimate_tokens,
    split_korean_sentences,
)
from ...config import settings

from .types import RAGChunk


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class DocumentChunker:
    def __init__(
        self,
        strategy: str = "recursive",
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        target_tokens: int | None = None,
    ):
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # ZZ-4: recursive 전략의 실제 목표 토큰.
        # 메인 chunker.py(ingest_pipeline)와 동일한 350 토큰을 쓰도록 한다.
        # (chunk_size 는 고정/의미 전략용 fallback 글자수로만 사용)
        self.target_tokens = (
            target_tokens if target_tokens is not None
            else settings.ingest_chunk_target_tokens
        )

    # ──────────────────────────────────────────────────────────────
    # 포맷 로더 — 외부 문서를 plain text 로 정규화
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def load(content: str, fmt: str = "text") -> str:
        fmt = (fmt or "text").lower()
        if fmt in ("text", "txt", "md", "markdown"):
            return content
        if fmt == "json":
            return _load_json(content)
        if fmt == "csv":
            return _load_csv(content)
        # 알 수 없는 포맷은 그대로 텍스트 취급
        return content

    # ──────────────────────────────────────────────────────────────
    # 청킹 진입점
    # ──────────────────────────────────────────────────────────────
    def chunk(
        self,
        text: str,
        *,
        doc_id: str,
        title: str = "",
        source: str = "",
        language: str = "ko",
        section: str = "",
        metadata: dict | None = None,
    ) -> list[RAGChunk]:
        text = (text or "").strip()
        if not text:
            return []

        if self.strategy == "fixed":
            pieces = self._chunk_fixed(text)
        elif self.strategy == "semantic":
            pieces = self._chunk_semantic(text)
        else:  # recursive (기본)
            pieces = self._chunk_recursive(text)

        chash = content_hash(text)
        # ZZ-2: 원본 문서 메타데이터(doc_type/scripture_refs/topic_tags 등)를
        # 청크 payload 로 전달 (vector_store._meta 가 **c.metadata 로 전개).
        chunk_meta = dict(metadata) if metadata else {}
        out: list[RAGChunk] = []
        for i, piece in enumerate(pieces):
            out.append(
                RAGChunk(
                    chunk_id=f"{doc_id}::{content_hash(piece)[:12]}",
                    doc_id=doc_id,
                    text=piece,
                    chunk_index=i,
                    section=section,
                    language=language,
                    source=source,
                    title=title,
                    content_hash=chash,
                    metadata=chunk_meta,
                )
            )
        return out

    # ──────────────────────────────────────────────────────────────
    # 전략 구현
    # ──────────────────────────────────────────────────────────────
    def _chunk_recursive(self, text: str) -> list[str]:
        # 기존 한국어 청킹 재사용 (문장/헤딩 경계 보존)
        # ZZ-4: target_tokens 를 명시해 메인 chunker.py 와 동일한 목표 토큰 적용.
        # 주의: chunk_size/chunk_overlap(글자수)을 함께 넘기면 chunk_text()의 하위호환
        # 분기(chunk_size → target 재계산)에 걸려 target_tokens 를 덮어쓰고,
        # chunk_overlap 은 chunk_text()가 아예 읽지 않아 무시된다.
        # → 메인 인제스트와 동일한 토큰/오버랩 설정을 명시적으로 전달한다.
        chunks = _ko_chunk_text(
            text,
            target_tokens=self.target_tokens,
            max_tokens=settings.ingest_chunk_max_tokens,
            min_tokens=settings.ingest_chunk_min_tokens,
            overlap_sentences=settings.ingest_chunk_overlap,
        )
        return [c.text for c in chunks]

    def _chunk_fixed(self, text: str) -> list[str]:
        size = max(50, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))
        step = size - overlap
        pieces: list[str] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(start + size, n)
            piece = text[start:end].strip()
            if piece:
                pieces.append(piece)
            if end == n:
                break
            start += step
        return pieces

    def _chunk_semantic(self, text: str) -> list[str]:
        # 문장 단위 누적 → 목표 토큰(추정) 도달 시 플러시, overlap 은 문장 1개
        target = max(50, self.chunk_size)
        sents = split_korean_sentences(text)
        if not sents:
            return [text]
        buf: list[str] = []
        buf_tok = 0
        pieces: list[str] = []
        for s in sents:
            st = estimate_tokens(s)
            if buf and buf_tok + st > target:
                pieces.append(" ".join(buf))
                # overlap: 마지막 1문장 유지
                tail = buf[-1:]
                buf = list(tail)
                buf_tok = estimate_tokens(" ".join(buf))
            buf.append(s)
            buf_tok += st
        if buf:
            pieces.append(" ".join(buf))
        return pieces


# ──────────────────────────────────────────────────────────────────
# 포맷별 정규화 헬퍼
# ──────────────────────────────────────────────────────────────────
def _load_json(content: str) -> str:
    try:
        data = json.loads(content)
    except Exception:
        return content

    parts: list[str] = []

    def _emit(obj):
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            title = obj.get("title") or obj.get("source") or ""
            body = (
                obj.get("text")
                or obj.get("content")
                or obj.get("body")
                or obj.get("passage")
                or ""
            )
            if title and body:
                parts.append(f"# {title}\n\n{body}")
            elif body:
                parts.append(str(body))
        elif isinstance(obj, list):
            for item in obj:
                _emit(item)

    if isinstance(data, dict):
        docs = data.get("documents") or data.get("docs") or data.get("items")
        if docs is not None:
            _emit(docs)
        else:
            _emit(data)
    else:
        _emit(data)

    return "\n\n".join(p for p in parts if p).strip()


def _load_csv(content: str) -> str:
    try:
        reader = csv.DictReader(io.StringIO(content))
        rows = []
        for r in reader:
            row = " | ".join(f"{k}: {v}" for k, v in r.items() if v)
            if row.strip():
                rows.append(row)
        return "\n".join(rows)
    except Exception:
        return content
