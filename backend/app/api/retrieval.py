"""POST /retrieval - Dify External Knowledge API 스펙 호환.

주요 기능:
- MMR 다양성 랭킹
- 컨텍스트 압축
- 검색 explain 메타데이터
- 출처/저자 기반 신뢰도 점수
- 소스 타입 분류
- Query Optimizer 기반 동적 하이브리드 가중치

요구사항:
- Bearer 토큰 인증
- knowledge_id 로 어떤 임베더 collection을 쓸지 선택 가능 (예: gospel_kure)
"""

from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, HTTPException, Header
from typing import Optional

from ..config import settings
from ..models.schemas import (
    DifyRetrievalRequest,
    DifyRetrievalResponse,
    DifyRecord,
)
from ..services.retriever import get_retriever
from ..services.search_optimizer import analyze_query
from ..services.search_v4 import get_search_engine
from ..services.addiction_care import assess_addiction_query


router = APIRouter(prefix="", tags=["retrieval"])


def _check_bearer(authorization: Optional[str]) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 1001,
                "error_msg": "Missing Authorization Bearer token",
            },
        )
    token = authorization.split(" ", 1)[1].strip()
    if hmac.compare_digest(settings.dify_api_key, "change-me"):
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": 1003,
                "error_msg": "API key not configured — set DIFY_API_KEY in .env",
            },
        )
    if not hmac.compare_digest(token, settings.dify_api_key):
        raise HTTPException(
            status_code=403,
            detail={"error_code": 1002, "error_msg": "Authorization failed"},
        )


@router.post("/retrieval", response_model=DifyRetrievalResponse)
async def retrieval(
    req: DifyRetrievalRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    knowledge_id 규칙:
      - "<embedder_name>" (예: kure, bge_m3) → 해당 임베더 collection 사용
      - 없으면 default embedder

    ✅ v4 고급 옵션 (메타데이터로 제어):
      - enable_mmr: bool = True → 다양성 랭킹 사용
      - enable_compression: bool = True → 컨텍스트 압축 사용
      - enable_explain: bool = True → 검색 설명 포함
    """
    t0 = time.time()
    _check_bearer(authorization)

    knowledge_id = req.knowledge_id.strip() if req.knowledge_id else ""
    embedder = knowledge_id or settings.embedder
    prefix = f"{settings.qdrant_collection_prefix}_"
    if embedder.startswith(prefix):
        embedder = embedder[len(prefix):]

    # 비한국어 요청이면 한국어 특화 임베더(kure)를 다국어 임베더로 자동 전환
    target_lang = req.target_lang
    _KOREAN_ONLY_EMBEDDERS = {"kure"}
    _MULTILINGUAL_FALLBACK = "bge_m3"
    if target_lang != "ko" and embedder in _KOREAN_ONLY_EMBEDDERS:
        embedder = _MULTILINGUAL_FALLBACK

    try:
        retriever = get_retriever(embedder_name=embedder)
        search_engine = get_search_engine(retriever)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 2001,
                "error_msg": f"unknown knowledge_id: {embedder} ({e})",
            },
        )

    # Query Optimizer 분석
    qa = analyze_query(req.query)

    # 요청 메타데이터에서 옵션 추출
    meta = req.retrieval_setting.metadata or {}
    enable_mmr = meta.get("enable_mmr", True)
    enable_compression = meta.get("enable_compression", True)
    enable_explain = meta.get("enable_explain", True)

    # ✅ v4 고급 검색 실행
    results = await search_engine.search(
        query=req.query,
        top_k=req.retrieval_setting.top_k,
        enable_mmr=enable_mmr,
        enable_compression=enable_compression,
        enable_explain=enable_explain,
    )

    threshold = req.retrieval_setting.score_threshold or 0.0
    raw_scores = [float(it.final_score) for it in results]
    min_score = min(raw_scores) if raw_scores else 0.0
    max_score = max(raw_scores) if raw_scores else 0.0
    score_span = max_score - min_score

    records: list[DifyRecord] = []
    for it in results:
        raw_score = float(it.final_score)
        normalized_score = (
            (raw_score - min_score) / score_span
            if score_span > 1e-9
            else (1.0 if raw_scores else 0.0)
        )
        if normalized_score < threshold:
            continue

        # ✅ v4: 압축된 컨텍스트를 content로 사용 (더 정확하고 짧음)
        content = it.compressed_context.compressed_text if enable_compression and it.compressed_context else it.text

        # ✅ v4: 풍부한 메타데이터
        metadata = {
            **it.metadata,
            "id": it.id,
            "source_title": it.source_title,
            "source_type": it.source_type,
            "reliability_score": it.reliability_score,
            "raw_dense_score": it.raw_dense_score,
            "raw_sparse_score": it.raw_sparse_score,
            "rerank_score": it.rerank_score,
            "raw_final_score": raw_score,
            "normalized_score": normalized_score,
        }

        # ✅ v4: 검색 Explain 정보
        if enable_explain and it.explanation:
            metadata["explanation"] = {
                "query_match_score": it.explanation.query_match_score,
                "semantic_similarity": it.explanation.semantic_similarity,
                "relevance_keywords": it.explanation.relevance_keywords,
                "diversity_contribution": it.explanation.diversity_contribution,
                "overall_reason": it.explanation.overall_reason,
            }

        # ✅ v4: 관련 문장 정보
        if enable_compression and it.compressed_context:
            metadata["relevant_sentences"] = it.compressed_context.relevant_sentences
            metadata["compression_confidence"] = it.compressed_context.confidence

        records.append(
            DifyRecord(
                content=content,
                score=float(normalized_score),
                title=it.source_title,
                metadata=metadata,
            )
        )

    elapsed_ms = int((time.time() - t0) * 1000)

    addiction_assessment = assess_addiction_query(req.query)

    return DifyRetrievalResponse(
        records=records,
        query_analysis={
            "query_type": qa.query_type,
            "dense_weight": qa.dense_weight,
            "sparse_weight": qa.sparse_weight,
            "expanded_queries": qa.expanded_queries,
            "confidence": qa.confidence,
            "elapsed_ms": elapsed_ms,
            "v4_features": {
                "mmr_enabled": enable_mmr,
                "compression_enabled": enable_compression,
                "explain_enabled": enable_explain,
            },
            "addiction_assessment": {
                "is_addiction_related": addiction_assessment.is_addiction_related,
                "addiction_types": [t.value for t in addiction_assessment.addiction_types],
                "crisis_level": addiction_assessment.crisis_level.value,
                "has_suicidal_thought": addiction_assessment.has_suicidal_thought,
                "has_extreme_shame": addiction_assessment.has_extreme_shame,
                "has_family_damage": addiction_assessment.has_family_damage,
                "key_themes": addiction_assessment.key_themes,
                "crisis_resources": addiction_assessment.crisis_resources,
            } if (
                addiction_assessment.is_addiction_related
                or addiction_assessment.crisis_level.value != "safe"
                or addiction_assessment.has_suicidal_thought
            ) else None,
        },
    )
