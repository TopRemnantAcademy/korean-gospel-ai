"""Enhanced RAG — 런타임 설정.

API 로 입출력 가능한 Pydantic 모델. 모든 값은 safe 기본값을 가지며,
configure() 호출로 런타임에 갱신된다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...config import settings


class BilingualConfig(BaseModel):
    """이중 저장(한국어 원문 보존 + 중국어 번역) 설정.

    권장 구성: enabled=True, primary_lang="zh", source_lang="ko".
    - 주 검색 벡터(primary)는 중국어 번역문을 임베딩 (중국어 사용자 다수 가정)
    - 원문(한국어)은 불변 payload 로 보존 (source of truth)
    - 선택적 명명 벡터 dense_ko 로 한국어 쿼리도 지원
    """

    enabled: bool = True
    primary_lang: str = "zh"            # 주 검색 벡터 언어 (표시/검색 기준)
    source_lang: str = "ko"            # 원문 언어 (불변 보존 대상)
    translator: str = "llm"            # glossary | llm | deepl
    glossary_path: str | None = None   # None → 패키지 내 data/glossary.json (번역 용어집)
    glossary_version: str = "v1"       # 용어집 파일 version 과 일치시킬 것

    # 벡터 구성
    chinese_embedder: str = "bge_m3"   # primary(중국어) 벡터용 다국어 임베더
    embed_source_vector: bool = True   # dense_ko 명명 벡터 추가(원문 언어 쿼리 지원)

    # 번역 품질 검증
    translation_engine_label: str = "glossary-v1"
    auto_verify: bool = True
    quality_min_score: float = 0.80    # 이하 → flagged (인간 검수 큐)
    glossary_compliance_min: float = 0.90
    length_ratio_min: float = 0.30     # 번역문/원문 길이비 하한
    length_ratio_max: float = 3.00     # 길이비 상한
    context_preservation: bool = True  # 인접 청크 컨텍스트를 번역에 주입
    review_policy: str = "auto"        # auto | human_in_the_loop


class RAGConfig(BaseModel):
    # ── Embedding / Vector store ──
    embedder: str = "kure"
    collection: str | None = None   # None → f"enhanced_rag_{embedder}" 자동 결정

    # ── Retrieval (hybrid) ──
    top_k: int = 8                   # 최종 반환 청크 수
    recall_k: int = 40              # 1차 후보 recall 크기 (dense+sparse 각각)
    dense_weight: float = 0.7       # RRF 융합 가중치
    sparse_weight: float = 0.3
    rrf_k: int = 60                  # Reciprocal Rank Fusion 상수

    # ── Chunking ──
    chunk_strategy: str = "recursive"   # recursive | fixed | semantic
    chunk_size: int = 500               # fixed: 문자수 / recursive: 목표 토큰(추정)
    chunk_overlap: int = 80

    # ── Reranking ──
    reranker: str = "heuristic"     # heuristic | llm | cross_encoder | none
    rerank_top_n: int = 5           # 리랭킹 후 최종 유지 수
    mmr_lambda: float = 0.7         # 1.0=관련성 위주, 0.0=다양성 위주

    # ── Wave C: 프로필 기반 개인화 재순위 ──
    # 부스트 on/off 는 전역 settings.retriever_boost_enabled 가 권위 소스(단일 제어).
    # 기본값을 해당 전역 플래그로 자동 동기화하므로, RAGConfig 를 기본값으로 생성하는
    # 모든 경로(production retriever / enhanced_rag / 평가 하네스)가 자동으로 일치하여
    # A/B 공정 비교가 보장된다. 명시적 override 시에만 차이가 발생(의도된 per-request 게이트).
    profile_boost_enabled: bool = Field(default_factory=lambda: settings.retriever_boost_enabled)
    context_reorder: Literal["rank", "doc_then_chunk"] = "rank"  # 원문 순서 정렬 전략

    # ── Prompt assembly / Generation ──
    context_top_k: int = 5          # 프롬프트에 주입할 상위 문서 수
    context_max_tokens: int = 1200  # 프롬프트 컨텍스트 토큰 상한
    generation_provider: str | None = None   # None → settings.llm_provider
    generation_temperature: float = 0.2
    generation_max_tokens: int = 700

    # ── Misc ──
    language: str = "ko"

    # ── Bilingual dual-storage (한국어 원문 보존 + 중국어 우선) ──
    bilingual: BilingualConfig = Field(default_factory=BilingualConfig)

    def collection_name(self) -> str:
        if self.collection:
            return self.collection
        return f"enhanced_rag_{self.embedder}"
