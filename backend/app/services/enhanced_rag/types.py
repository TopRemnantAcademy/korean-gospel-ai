"""Enhanced RAG — core data types.

이 모듈은 enhanced_rag 패키지 전반에서 사용하는 순수 데이터 클래스만 정의한다.
외부 의존성(임베더/벡터DB/LLM)이 없으므로 단위 테스트에서 자유롭게 import 가능.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RAGDocument:
    """인제스트 대상 원본 문서."""

    doc_id: str
    title: str = ""
    source: str = ""          # 파일명 / URL / 컬렉션명 등 출처 식별자
    content: str = ""
    language: str = "ko"
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGChunk:
    """청킹 후 벡터화 대상 단위. chunk_id 는 전역 고유해야 함 (doc_id::index)."""

    chunk_id: str
    doc_id: str
    text: str
    chunk_index: int = 0
    section: str = ""
    language: str = "ko"
    source: str = ""
    title: str = ""
    content_hash: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    """검색/리랭킹 결과의 표준 형태."""

    chunk_id: str
    doc_id: str
    text: str
    score: float = 0.0          # 최종 점수 (리랭크 반영)
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: Optional[float] = None
    rank: int = 0
    section: str = ""
    source: str = ""
    title: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGQueryResult:
    query: str
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    answer: Optional[str] = None
    citations: list[dict] = field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens: dict = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass
class IngestResult:
    doc_id: str
    title: str
    source: str
    num_chunks: int
    language: str
    status: str = "ok"          # ok | skipped | error
    unchanged: bool = False     # 동일 해시로 인해 갱신 생략됨
    error: Optional[str] = None


@dataclass
class DocInfo:
    doc_id: str
    title: str
    source: str
    language: str
    chunk_count: int
    content_hash: str = ""


@dataclass
class RetrievalMetrics:
    queries: int
    k: int
    hit_rate: float             # Hit@k
    precision_at_k: float       # P@k
    recall_at_k: float          # R@k
    mrr: float                  # Mean Reciprocal Rank
    ndcg_at_k: float            # nDCG@k


@dataclass
class GenerationMetrics:
    samples: int
    faithfulness: float         # LLM-as-judge: 답변이 컨텍스트에 근거하는 정도
    answer_relevancy: float     # LLM-as-judge: 질문에 대한 적절성
    context_precision: float
    context_recall: float
    lexical_overlap: float      # 참조 답변 대비 토큰 중첩 (제공 시)
    avg_generation_time_ms: float


@dataclass
class EvalResult:
    retrieval: Optional[RetrievalMetrics] = None
    generation: Optional[GenerationMetrics] = None
    details: list[dict] = field(default_factory=list)
