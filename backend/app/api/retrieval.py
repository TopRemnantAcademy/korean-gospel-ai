"""POST /retrieval - Dify External Knowledge API 스펙 호환.
요구사항:
- Bearer 토큰 인증
- knowledge_id 로 어떤 임베더 collection을 쓸지 선택 가능 (예: gospel_kure)
- 응답: { records: [{ metadata, score, title, content }] }
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional

from ..config import settings
from ..models.schemas import (
    DifyRetrievalRequest, DifyRetrievalResponse, DifyRecord,
)
from ..services.retriever import HybridRetriever


router = APIRouter(prefix="", tags=["retrieval"])


def _check_bearer(authorization: Optional[str]) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail={"error_code": 1001, "error_msg": "Missing Authorization Bearer token"})
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.dify_api_key:
        raise HTTPException(status_code=403, detail={"error_code": 1002, "error_msg": "Authorization failed"})


@router.post("/retrieval", response_model=DifyRetrievalResponse)
async def retrieval(
    req: DifyRetrievalRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    knowledge_id 규칙:
      - "<embedder_name>" (예: kure, bge_m3) → 해당 임베더 collection 사용
      - 없으면 default embedder
    """
    _check_bearer(authorization)

    embedder = req.knowledge_id.strip() if req.knowledge_id else settings.embedder
    try:
        retriever = HybridRetriever(embedder_name=embedder)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error_code": 2001, "error_msg": f"unknown knowledge_id: {embedder} ({e})"})

    items = await retriever.retrieve(req.query, rerank_top_n=req.retrieval_setting.top_k)
    threshold = req.retrieval_setting.score_threshold or 0.0

    records: list[DifyRecord] = []
    for it in items:
        if it.score < threshold:
            continue
        records.append(DifyRecord(
            content=it.text,
            score=float(it.score),
            title=str(it.metadata.get("title") or it.metadata.get("file_name") or "untitled"),
            metadata={**it.metadata, "id": it.id, "rrf_score": it.rrf_score},
        ))
    return DifyRetrievalResponse(records=records)
