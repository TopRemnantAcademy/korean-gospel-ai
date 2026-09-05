"""Enhanced RAG — 문서 인제스트 오케스트레이션.

다중 문서 소스 지원 + 증분 갱신:
- 포맷 자동 감지 (소스 확장자 또는 metadata.format)
- 청킹 → 임베딩 → 스토어 적재
- 동일 content_hash 재인제스트 시 no-op (멱등, 증분 효율)
- 다른 해시일 때 스토어가 기존 청크를 교체 (증분 업데이트)
"""
from __future__ import annotations

import logging
from typing import Iterable

from ...config import settings
from .chunking import DocumentChunker
from .embeddings import RAGEmbedder
from .types import IngestResult, RAGDocument
from .vector_store import RAGVectorStore

logger = logging.getLogger(__name__)


class DocumentIngestor:
    def __init__(
        self,
        chunker: DocumentChunker,
        embedder: RAGEmbedder,
        store: RAGVectorStore,
    ):
        self.chunker = chunker
        self.embedder = embedder
        self.store = store

    @staticmethod
    def _detect_format(doc: RAGDocument) -> str:
        fmt = (doc.metadata or {}).get("format")
        if fmt:
            return str(fmt).lower()
        src = (doc.source or "").lower()
        if src.endswith(".json"):
            return "json"
        if src.endswith(".csv"):
            return "csv"
        if src.endswith((".md", ".markdown")):
            return "md"
        return "text"

    def ingest_document(self, doc: RAGDocument) -> IngestResult:
        fmt = self._detect_format(doc)
        try:
            text = DocumentChunker.load(doc.content, fmt)
        except Exception as e:
            return IngestResult(
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                num_chunks=0,
                language=doc.language,
                status="error",
                error=f"load({fmt}) failed: {e}",
            )

        # ZZ-1/ZZ-3: STT 원고 정규화 선행 (단어결합 + 마침표 추정)
        # ingest_normalize_enabled 가 켜져 있을 때만 (기본 True)
        if getattr(settings, "ingest_normalize_enabled", True):
            from ..normalizer import preprocess_for_chunking
            text = preprocess_for_chunking(text)

        try:
            chunks = self.chunker.chunk(
                text,
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                language=doc.language,
                metadata=doc.metadata,
            )
        except Exception as e:
            return IngestResult(
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                num_chunks=0,
                language=doc.language,
                status="error",
                error=f"chunk failed: {e}",
            )

        if not chunks:
            return IngestResult(
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                num_chunks=0,
                language=doc.language,
                status="error",
                error="empty document after chunking",
            )

        # 멱등 체크: 동일 해시면 갱신 생략
        existing = self.store._manifest.get(doc.doc_id)
        if existing and existing.get("content_hash") == chunks[0].content_hash:
            return IngestResult(
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                num_chunks=existing.get("chunk_count", 0),
                language=doc.language,
                status="skipped",
                unchanged=True,
            )

        try:
            self.store.ingest(chunks)
            return IngestResult(
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                num_chunks=len(chunks),
                language=doc.language,
                status="ok",
            )
        except Exception as e:
            logger.exception("[rag-ingest] %s 인제스트 실패", doc.doc_id)
            return IngestResult(
                doc_id=doc.doc_id,
                title=doc.title,
                source=doc.source,
                num_chunks=0,
                language=doc.language,
                status="error",
                error=str(e),
            )

    def ingest_documents(self, docs: Iterable[RAGDocument]) -> list[IngestResult]:
        return [self.ingest_document(d) for d in docs]
