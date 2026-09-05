"""Enhanced RAG — REST API 라우터.

엔드포인트:
- POST   /rag/ingest          문서 인제스트 (다중 문서, 증분 갱신)
- POST   /rag/query           하이브리드 검색 + 선택적 리랭크 + 선택적 생성
- GET    /rag/documents       인제스트된 문서 목록
- DELETE /rag/documents/{id}  문서 삭제 (증분 갱신의 일부)
- GET    /rag/config          현재 설정 조회
- PUT    /rag/config          설정 갱신 (런타임)
- POST   /rag/evaluate        검색 정확도 + 응답 품질 평가
- GET    /rag/health          상태 확인

쓰기 엔드포인트(ingest/delete/config)는 X-API-Key == ADMIN_API_KEY 필요.
"""
from __future__ import annotations

import hmac
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..services.enhanced_rag import get_pipeline
from ..services.enhanced_rag.types import RAGDocument

logger = logging.getLogger(__name__)


def _safe_dump(obj: Any) -> Optional[dict]:
    """Pydantic 모델은 model_dump(), dataclass 는 asdict(), 그 외는 dict().
    obj.__dict__ 직접 노출을 지양(내부 필드/계산필드 누락 방지)."""
    if obj is None:
        return None
    md = getattr(obj, "model_dump", None)
    if callable(md):
        try:
            return md()
        except Exception as e:
            logger.warning("[enhanced_rag] model_dump failed, falling back: %s", e)
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.asdict(obj)
    try:
        return dict(obj)
    except Exception:
        return dict(obj.__dict__)


router = APIRouter(prefix="/rag", tags=["enhanced-rag"])


# ──────────────────────────────────────────────────────────────
# 요청/응답 모델
# ──────────────────────────────────────────────────────────────
class IngestDoc(BaseModel):
    doc_id: str
    title: str = ""
    source: str = ""
    content: str
    language: str = "ko"
    metadata: dict = Field(default_factory=dict)


class IngestRequest(BaseModel):
    documents: list[IngestDoc]


class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = None
    use_rerank: bool = True
    generate: bool = True
    filters: Optional[dict] = None


class EvaluateRequest(BaseModel):
    qa_pairs: list[dict]
    k: Optional[int] = None
    with_generation: bool = False


class ConfigUpdate(BaseModel):
    changes: dict = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# 의존성: 관리자 키
# ──────────────────────────────────────────────────────────────
def require_admin(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    # Header(default=None) 이 FastAPI 주입 없이 직접 호출될 때 Header 객체로
    # 남는 경우를 방지 — 항상 str/None 으로 정규화한다.
    x_api_key = x_api_key if isinstance(x_api_key, str) else None
    authorization = authorization if isinstance(authorization, str) else None
    expected = settings.admin_api_key
    if not expected or expected == "change-me":
        # 기본값이면 관리자 기능 비활성화 — 인증 우회 금지
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY 가 설정되지 않아 관리자 기능이 비활성화되었습니다.")
    # 관리자 클라이언트는 Authorization: Bearer 를, 외부 호출은 X-API-Key 를 보낼 수 있음.
    # 두 헤더를 모두 수용해 인증 헤더 불일치로 인한 401 을 방지 (광고/지원/RAG 관리 엔드포인트 공통).
    provided = x_api_key or ""
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    # 타이밍 공격 방지를 위한 상수 시간 비교
    if not hmac.compare_digest(provided or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ──────────────────────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────────────────────
@router.post("/ingest")
async def ingest(req: IngestRequest, _: None = Depends(require_admin)):
    pipe = get_pipeline()
    docs = [
        RAGDocument(
            doc_id=d.doc_id,
            title=d.title,
            source=d.source,
            content=d.content,
            language=d.language,
            metadata=d.metadata,
        )
        for d in req.documents
    ]
    results = pipe.add_documents(docs)
    return {
        "ingested": len(results),
        "results": [_safe_dump(r) for r in results],
    }


@router.post("/query")
async def query(req: QueryRequest, _: None = Depends(require_admin)):
    pipe = get_pipeline()
    res = await pipe.query(
        req.query,
        top_k=req.top_k,
        use_rerank=req.use_rerank,
        generate=req.generate,
        filters=req.filters,
    )
    return {
        "query": res.query,
        "retrieved": [_safe_dump(c) for c in res.retrieved],
        "answer": res.answer,
        "citations": res.citations,
        "provider": res.provider,
        "model": res.model,
        "tokens": res.tokens,
        "latency_ms": res.latency_ms,
    }


@router.get("/documents")
async def list_documents(_: None = Depends(require_admin)):
    pipe = get_pipeline()
    return {"documents": [_safe_dump(d) for d in pipe.list_documents()]}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, _: None = Depends(require_admin)):
    pipe = get_pipeline()
    ok = pipe.remove_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="document not found")
    return {"deleted": doc_id, "status": "ok"}


@router.get("/config")
async def get_config(_: None = Depends(require_admin)):
    pipe = get_pipeline()
    return pipe.config.model_dump()


@router.put("/config")
async def update_config(req: ConfigUpdate, _: None = Depends(require_admin)):
    pipe = get_pipeline()
    try:
        cfg = pipe.configure(**req.changes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid config: {e}")
    return {"config": cfg.model_dump()}


@router.post("/evaluate")
async def evaluate(req: EvaluateRequest, _: None = Depends(require_admin)):
    pipe = get_pipeline()
    try:
        result = await pipe.evaluate(
            req.qa_pairs, k=req.k, with_generation=req.with_generation
        )
    except Exception:
        logger.exception("[rag-api] evaluate 실패")
        raise HTTPException(status_code=500, detail="evaluation failed; see server logs")
    payload: dict[str, Any] = {"retrieval": _safe_dump(result.retrieval)}
    if result.generation:
        payload["generation"] = _safe_dump(result.generation)
    payload["details"] = result.details
    return payload


@router.get("/health")
async def health():
    pipe = get_pipeline()
    return {
        "status": "ok",
        "embedder": pipe.embedder.name,
        "dim": pipe.embedder.dim,
        "collection": pipe.store.collection,
        "reranker": pipe.config.reranker,
        "documents": len(pipe.list_documents()),
        "chunks": pipe.count(),
    }
