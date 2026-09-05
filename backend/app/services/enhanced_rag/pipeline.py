"""Enhanced RAG — 파이프라인 오케스트레이션.

모든 구성요소(청킹→임베딩→스토어→검색→리랭크→조립→생성→평가)를 하나로 묶고,
설정 변경(configure) 시 영향받는 구성요소만 재생성한다.

고급 기능:
- 다중 문서 소스: add_documents() 로 여러 RAGDocument 동시 인제스트
- 증분 갱신: 같은 doc_id 재인제스트 시 기존 청크 자동 교체 (store.ingest)
- 평가: evaluate() 로 검색 지표 + 응답 품질 지표 산출
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from .chunking import DocumentChunker
from .config import RAGConfig
from ...config import settings
from .embeddings import RAGEmbedder
from .evaluation import RAGEvaluator
from .generation import ResponseGenerator
from .ingest import DocumentIngestor
from .prompt import PromptAssembler
from .reranker import ContextAwareReranker
from .retrieval import HybridRetriever
from .profile_boost import compute_profile_boost
from .types import (
    DocInfo,
    EvalResult,
    IngestResult,
    RAGDocument,
    RAGQueryResult,
    RetrievedChunk,
)
from .vector_store import RAGVectorStore

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig()
        self._build_core()
        self._build_chunking()
        self._build_retrieval_components()
        self.evaluator = RAGEvaluator()

    # ── 구성요소 빌드 ──
    def _build_core(self):
        cfg = self.config
        if cfg.bilingual.enabled:
            try:
                # 주 검색 벡터는 중국어(primary) 임베더가 생성
                primary_name = cfg.bilingual.chinese_embedder
                source_name = cfg.embedder  # 원문(한국어) 임베더 = 기존 embedder 필드
                self.embedder = RAGEmbedder(primary_name)

                # 컬렉션명은 primary 임베더 기준으로 결정 (미지정 시)
                if cfg.collection is None:
                    cfg.collection = f"enhanced_rag_{primary_name}"

                source_embedder = None
                extra_vecs = None
                if cfg.bilingual.embed_source_vector and source_name != primary_name:
                    try:
                        source_embedder = RAGEmbedder(source_name)
                        extra_vecs = self._build_source_vector_config(source_embedder)
                    except Exception as e:
                        logger.warning(
                            "[pipeline] 원문 벡터(dense_ko) 생성 실패 — 한국어 쿼리 미지원: %s", e
                        )
                        source_embedder = None

                self.store = RAGVectorStore(
                    cfg,
                    self.embedder,
                    source_embedder=source_embedder,
                    extra_vector_configs=extra_vecs,
                )
                return
            except Exception as e:
                logger.error(
                    "[pipeline] 이중 저장 활성화 실패 — 표준(단일언어) 경로로 폴백: %s", e
                )
                # 폴백: bilingual 비활성화 후 표준 경로로 진행
                cfg = cfg.model_copy(
                    update={
                        "bilingual": cfg.bilingual.model_copy(update={"enabled": False})
                    }
                )
                self.config = cfg

        # 표준(단일언어) 경로 — 항상 동작해야 함
        self.embedder = RAGEmbedder(cfg.embedder)
        self.store = RAGVectorStore(cfg, self.embedder)

    @staticmethod
    def _build_source_vector_config(source_embedder: RAGEmbedder) -> dict | None:
        """원문 언어용 명명 벡터(dense_ko) 설정 생성. qdrant 미설치 시 None."""
        try:
            from ..vector_store import qm

            if qm is None:
                return None
            return {
                "dense_ko": qm.VectorParams(
                    size=source_embedder.dim,
                    distance=qm.Distance.COSINE,
                    hnsw_config=qm.HnswConfigDiff(
                        m=16, ef_construct=128,
                        full_scan_threshold=10000, max_indexing_threads=4,
                    ),
                )
            }
        except Exception as e:
            logger.warning("[pipeline] dense_ko 벡터 설정 생성 실패: %s", e)
            return None

    def _build_chunking(self):
        self.chunker = DocumentChunker(
            strategy=self.config.chunk_strategy,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        self.ingestor = DocumentIngestor(self.chunker, self.embedder, self.store)

    def _build_retrieval_components(self):
        self.retriever = HybridRetriever(self.config, self.embedder, self.store)
        self.reranker = ContextAwareReranker(self.config.reranker)
        self.assembler = PromptAssembler(language=self.config.language)
        self.generator = ResponseGenerator(self.config)

    # ── 런타임 설정 갱신 ──
    def configure(self, **changes) -> RAGConfig:
        prev_embedder = self.config.embedder
        prev_collection = self.config.collection
        prev_chunk = (
            self.config.chunk_strategy,
            self.config.chunk_size,
            self.config.chunk_overlap,
        )
        prev_reranker = self.config.reranker
        prev_lang = self.config.language
        prev_bilingual = self.config.bilingual.model_dump()

        merged = self.config.model_dump()
        merged.update(changes)
        self.config = RAGConfig(**merged)

        # 임베더/컬렉션 변경 → 코어(스토어) 재생성 (별도 컬렉션)
        bilingual_changed = self.config.bilingual.model_dump() != prev_bilingual
        if (
            self.config.embedder != prev_embedder
            or self.config.collection != prev_collection
            or bilingual_changed
        ):
            self._build_core()

        # 청킹 변경 → 청킹/인제스트 재생성
        if (
            self.config.chunk_strategy,
            self.config.chunk_size,
            self.config.chunk_overlap,
        ) != prev_chunk:
            self._build_chunking()

        # 리랭커/언어/생성 변경 → 해당 구성요소 재생성
        if self.config.reranker != prev_reranker:
            self.reranker = ContextAwareReranker(self.config.reranker)
        if self.config.language != prev_lang:
            self.assembler = PromptAssembler(language=self.config.language)
        self.generator = ResponseGenerator(self.config)

        # retriever 는 store/embedder 를 참조하므로 항상 갱신
        self.retriever = HybridRetriever(self.config, self.embedder, self.store)
        return self.config

    # ── 인제스트 / 갱신 / 삭제 ──
    def add_document(self, doc: RAGDocument) -> IngestResult:
        return self.ingestor.ingest_document(doc)

    def add_documents(self, docs: list[RAGDocument]) -> list[IngestResult]:
        return self.ingestor.ingest_documents(docs)

    def update_document(self, doc: RAGDocument) -> IngestResult:
        """명시적 갱신: 기존 삭제 후 재인제스트 (증분 업데이트)."""
        self.store.delete_doc(doc.doc_id)
        return self.ingestor.ingest_document(doc)

    def remove_document(self, doc_id: str) -> bool:
        return self.store.delete_doc(doc_id)

    def list_documents(self) -> list[DocInfo]:
        return self.store.list_documents()

    def count(self) -> int:
        return self.store.count()

    # ── 쿼리 ──
    async def query(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        use_rerank: bool = True,
        generate: bool = True,
        filters: Optional[dict] = None,
        profile: Optional[dict] = None,
    ) -> RAGQueryResult:
        t0 = time.perf_counter()
        cfg = self.config
        top_k = top_k or cfg.top_k

        candidates = await self.retriever.retrieve(
            query, top_k=top_k, filters=filters
        )

        if use_rerank:
            ranked = self.reranker.rerank(
                query, candidates, top_n=cfg.rerank_top_n, config=cfg
            )
        else:
            candidates.sort(key=lambda c: c.rrf_score, reverse=True)
            ranked = candidates[: cfg.rerank_top_n]

        # Wave C: 프로필 기반 soft boost (개인화 재순위) — rerank 결과에 곱 적용
        # 부스트 on/off 는 전역 settings.retriever_boost_enabled 가 권위 소스(단일 제어).
        # cfg.profile_boost_enabled 은 기본값이 settings 를 따르도록 동기화되어 있으며,
        # per-request 로 명시 해제할 수 있는 게이트로도 동작한다.
        if settings.retriever_boost_enabled and cfg.profile_boost_enabled and profile:
            ranked = self._apply_profile_boost(ranked, profile, use_rerank)

        final: list[RetrievedChunk] = ranked[:top_k]
        # Wave C: 원문 순서 재정렬 (문서별 chunk_index 정렬, 문서 간 순서 유지)
        if cfg.context_reorder == "doc_then_chunk":
            final = self._reorder_doc_then_chunk(final)
        for i, c in enumerate(final):
            c.rank = i

        result = RAGQueryResult(query=query, retrieved=final)

        system_p, user_p, citations = self.assembler.assemble(
            query, final, max_tokens=cfg.context_max_tokens, top_k=cfg.context_top_k
        )
        result.citations = citations

        if generate:
            answer, provider, model, tokens = await self.generator.generate(
                query, system_p, user_p
            )
            result.answer = answer
            result.provider = provider
            result.model = model
            result.tokens = tokens

        result.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return result

    # ── Wave C: 프로필 부스트 / 재정렬 헬퍼 ──
    @staticmethod
    def _apply_profile_boost(
        ranked: list[RetrievedChunk], profile: dict, use_rerank: bool
    ) -> list[RetrievedChunk]:
        """프로필 부스트를 곱해 재정렬 (레거시 retriever 와 동일 공식/의미).

        base 는 레거시 retriever(final_score = rrf*0.3 + rerank*0.7) 와 동일하게 계산하여
        두 경로의 A/B 비교가 공정하도록 한다:
          - use_rerank=True  → base = rrf_score*0.3 + rerank_score*0.7
          - use_rerank=False → base = rrf_score
        rerank_score 가 minmax 로 0.0 이 되더라도 rrf_score(항상 >0) 가 보존되어
        부스트가 무력화되는 엣지 케이스를 방지한다. 부스트는 곱셈(1+boost) 적용.
        """
        scored: list[tuple[RetrievedChunk, float]] = []
        for c in ranked:
            if use_rerank and c.rerank_score is not None:
                base = c.rrf_score * 0.3 + c.rerank_score * 0.7
            else:
                base = c.rrf_score
            boost = compute_profile_boost(c.metadata or {}, profile)
            boosted = (base or 0.0) * (1.0 + boost)
            c.score = boosted  # 부스트 반영 점수 보관 (UI 표시/디버그 일관성)
            scored.append((c, boosted))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored]

    @staticmethod
    def _reorder_doc_then_chunk(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """문서별 원문 순서(chunk_index)로 재정렬. 문서 간 순서는 첫 등장 순으로 유지."""
        doc_order: dict[str, int] = {}
        order = 0
        for c in chunks:
            did = c.metadata.get("doc_id") if c.metadata else None
            if did not in doc_order:
                doc_order[did] = order
                order += 1
        return sorted(
            chunks,
            key=lambda c: (
                doc_order.get(c.metadata.get("doc_id") if c.metadata else None, 0),
                (c.metadata.get("chunk_index") if c.metadata else 0) or 0,
            ),
        )

    # ── 평가 ──
    async def evaluate(
        self,
        qa_pairs: list[dict],
        *,
        k: Optional[int] = None,
        with_generation: bool = False,
        profile: Optional[dict] = None,
    ) -> EvalResult:
        k = k or self.config.top_k
        retrieval_cases: list[dict] = []
        gen_pairs: list[dict] = []
        details: list[dict] = []

        for qa in qa_pairs:
            query = qa.get("query", "")
            res = await self.query(query, top_k=k, use_rerank=True, generate=with_generation, profile=profile)
            retrieval_cases.append(
                {
                    "retrieved": res.retrieved,
                    "relevant": set(qa.get("relevant", []) or []),
                    "relevant_is_doc": qa.get("relevant_is_doc", False),
                }
            )
            details.append(
                {
                    "query": query,
                    "num_retrieved": len(res.retrieved),
                    "answer": res.answer,
                }
            )
            if with_generation and qa.get("reference") is not None:
                gen_pairs.append(
                    {
                        "query": query,
                        "answer": res.answer or "",
                        "contexts": [c.text for c in res.retrieved],
                        "reference": qa.get("reference"),
                    }
                )

        retrieval_metrics = RAGEvaluator.eval_retrieval(retrieval_cases, k)
        generation_metrics = (
            self.evaluator.eval_generation(gen_pairs, self.config) if gen_pairs else None
        )

        return EvalResult(
            retrieval=retrieval_metrics,
            generation=generation_metrics,
            details=details,
        )
