"""Enhanced RAG 패키지.

기존 인프라(get_embedder / QdrantStore / chat_with_fallback)를 재사용하는
자체 완결형 RAG 시스템. REST API 는 backend.app.api.enhanced_rag 에서 제공.
"""
from __future__ import annotations

import logging

from ...config import settings
from .chunking import DocumentChunker
from .config import RAGConfig
from .embeddings import RAGEmbedder
from .ingest import DocumentIngestor
from .pipeline import RAGPipeline
from .prompt import PromptAssembler
from .reranker import ContextAwareReranker
from .retrieval import HybridRetriever
from .types import (
    DocInfo,
    EvalResult,
    GenerationMetrics,
    IngestResult,
    RAGChunk,
    RAGDocument,
    RAGQueryResult,
    RetrievedChunk,
    RetrievalMetrics,
)
from .vector_store import RAGVectorStore

logger = logging.getLogger(__name__)

_pipeline: "RAGPipeline | None" = None


def get_pipeline() -> "RAGPipeline":
    """프로세스 레벨 싱글턴 파이프라인.

    rag_bilingual_enabled 설정(True 기본)이면 중국어 우선 이중 저장을 활성화한다.
    임베더(예: bge_m3) 로드 실패 등으로 활성화가 불가능하면 표준(단일언어) 경로로
    안전하게 폴백하므로 앱 기동에 영향이 없다.
    """
    global _pipeline
    if _pipeline is None:
        try:
            cfg = RAGConfig()
            # env 토글 양방향 반영: False 여도 항상 켜지던 버그 수정
            # (BilingualConfig.enabled 기본값이 True 라서 if 블록만 있으면 꺼지지 않음)
            cfg.bilingual.enabled = settings.rag_bilingual_enabled
            _pipeline = RAGPipeline(cfg)
        except Exception as e:  # 어떤 이유로든 초기화 실패 → 표준 경로 재시도
            logger.warning("[rag] 파이프라인 초기화 실패(표준 경로 재시도): %s", e)
            _pipeline = RAGPipeline()  # 기본(단일언어) 경로
    return _pipeline


__all__ = [
    "RAGPipeline",
    "RAGConfig",
    "get_pipeline",
    "RAGDocument",
    "RAGChunk",
    "RetrievedChunk",
    "RAGQueryResult",
    "IngestResult",
    "DocInfo",
    "EvalResult",
    "RetrievalMetrics",
    "GenerationMetrics",
    "DocumentChunker",
    "RAGEmbedder",
    "RAGVectorStore",
    "HybridRetriever",
    "ContextAwareReranker",
    "PromptAssembler",
    "DocumentIngestor",
]
