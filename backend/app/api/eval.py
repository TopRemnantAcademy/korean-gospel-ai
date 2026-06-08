"""POST /eval/* - A/B, regression, 질문셋 생성, hybrid 튜닝."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..models.schemas import (
    EvalABRequest, EvalABResponse, EvalABItem, SourceItem,
    EvalGenerateRequest, EvalGenerateResponse,
    EvalTuneWeightsRequest, EvalTuneWeightsResponse,
)
from ..services.retriever import HybridRetriever
from ..services.eval_service import run_regression as _run_regression
from ..services.eval_set_generator import (
    generate_questions_from_documents,
    save_questions,
)
from ..services.hybrid_tuner import tune_hybrid_weights

router = APIRouter(prefix="/eval", tags=["eval"])


def _check_admin(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin token")


@router.post("/ab", response_model=EvalABResponse)
async def eval_ab(req: EvalABRequest, authorization: str | None = Header(default=None)):
    _check_admin(authorization)
    embedders = req.embedders or settings.embedders
    items: list[EvalABItem] = []
    for emb in embedders:
        retriever = HybridRetriever(embedder_name=emb)
        for q in req.queries:
            res = await retriever.retrieve(q, rerank_top_n=req.top_k)
            items.append(EvalABItem(
                embedder=emb,
                query=q,
                sources=[
                    SourceItem(id=r.id, text=r.text, score=r.score, metadata=r.metadata)
                    for r in res
                ],
            ))
    return EvalABResponse(items=items)


@router.post("/regression")
async def regression(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    return await _run_regression()


@router.post("/generate-questions", response_model=EvalGenerateResponse)
async def generate_questions(
    req: EvalGenerateRequest,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    questions = await generate_questions_from_documents(
        doc_dir=req.doc_dir,
        max_per_doc=req.max_per_doc,
    )
    if not questions:
        return EvalGenerateResponse(
            ok=False, count=0, questions=[], saved_path=None,
            reason="문서 없음 또는 LLM 생성 실패",
        )
    saved = None
    if req.save:
        path = save_questions(questions, merge=req.merge)
        saved = str(path.relative_to(settings.root_dir))
    return EvalGenerateResponse(
        ok=True,
        count=len(questions),
        questions=questions,
        saved_path=saved,
    )


@router.post("/tune-weights", response_model=EvalTuneWeightsResponse)
async def tune_weights(
    req: EvalTuneWeightsRequest,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    dense_grid = req.dense_grid if req.dense_grid else None
    sparse_grid = req.sparse_grid if req.sparse_grid else None
    result = await tune_hybrid_weights(
        embedder=req.embedder,
        top_k=req.top_k,
        dense_grid=dense_grid,
        sparse_grid=sparse_grid,
    )
    if not result.get("ok"):
        return EvalTuneWeightsResponse(ok=False, reason=result.get("reason", "unknown"))
    best = result["best"]
    env_hint = (
        f"DENSE_WEIGHT={best['dense_weight']}\nSPARSE_WEIGHT={best['sparse_weight']}"
    )
    return EvalTuneWeightsResponse(
        ok=True,
        best=best,
        current=result.get("current"),
        trials=result.get("trials", []),
        env_hint=env_hint,
    )


