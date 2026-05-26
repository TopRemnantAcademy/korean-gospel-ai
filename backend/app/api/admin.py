"""GET /admin/* - collections, health."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..services.vector_store import _make_client


router = APIRouter(prefix="/admin", tags=["admin"])


def _check_admin(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin token")


@router.get("/health")
def health():
    return {
        "ok": True,
        "provider": settings.llm_provider,
        "embedder": settings.embedder,
        "qdrant_url": settings.qdrant_url,
    }


@router.get("/collections")
def list_collections(authorization=Header(default=None)):
    _check_admin(authorization)
    try:
        client, _is_server = _make_client()
    except Exception as e:
        return {"collections": [], "warning": f"qdrant init failed: {type(e).__name__}: {str(e)[:200]}"}

    try:
        col_list = client.get_collections().collections
    except Exception as e:
        return {"collections": [], "warning": f"list failed: {type(e).__name__}: {str(e)[:200]}"}

    cols = []
    for c in col_list:
        try:
            info = client.get_collection(c.name)
            cols.append({
                "name": c.name,
                "points_count": getattr(info, "points_count", 0) or 0,
                "vectors_count": getattr(info, "vectors_count", 0) or 0,
                "status": str(getattr(info, "status", "ok")),
            })
        except Exception as e:
            cols.append({
                "name": c.name,
                "points_count": 0,
                "vectors_count": 0,
                "status": "error: " + str(e)[:80],
            })
    return {"collections": cols}



# ----- Taxonomy (태그/시리즈/화자 통계) -----
from collections import Counter
from ..db import get_session
from ..models.orm import Document, DocumentVersion, DocVersionState


@router.get("/taxonomy")
def taxonomy(authorization=Header(default=None)):
    _check_admin(authorization)
    tag_counter = Counter()
    series_counter = Counter()
    speaker_counter = Counter()
    type_counter = Counter()
    refs_counter = Counter()
    with get_session() as s:
        docs = s.query(Document).filter(Document.archived_at.is_(None)).all()
        for d in docs:
            type_counter[d.doc_type or "other"] += 1
            if d.series: series_counter[d.series] += 1
            if d.speaker: speaker_counter[d.speaker] += 1
            for v in d.versions:
                for t in (v.topic_tags or []):
                    tag_counter[t] += 1
                for r in (v.scripture_refs or []):
                    refs_counter[r] += 1
                break  # 최신 버전 하나만
    def topn(c, n=50):
        return [{"name": k, "count": v} for k, v in c.most_common(n)]
    return {
        "tags": topn(tag_counter),
        "series": topn(series_counter),
        "speakers": topn(speaker_counter),
        "types": topn(type_counter),
        "scripture_refs": topn(refs_counter),
    }



# ----- Usage stats (Gemini 한도 모니터링) -----
from datetime import datetime, timedelta
from ..models.orm import Interaction


GEMINI_FREE_DAILY_LIMIT = 1500   # Gemini 2.5 flash 일일 무료 한도
GEMINI_FREE_RPM_LIMIT = 15       # 분당


@router.get("/usage")
def usage(authorization=Header(default=None)):
    _check_admin(authorization)
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    last_24h = now - timedelta(hours=24)
    last_1m = now - timedelta(minutes=1)
    with get_session() as s:
        today_count = s.query(Interaction).filter(Interaction.created_at >= today_start).count()
        last24_count = s.query(Interaction).filter(Interaction.created_at >= last_24h).count()
        recent_min = s.query(Interaction).filter(Interaction.created_at >= last_1m).count()
    return {
        "today": today_count,
        "last_24h": last24_count,
        "last_1_min": recent_min,
        "daily_limit": GEMINI_FREE_DAILY_LIMIT,
        "rpm_limit": GEMINI_FREE_RPM_LIMIT,
        "daily_usage_pct": round(today_count / GEMINI_FREE_DAILY_LIMIT * 100, 1) if GEMINI_FREE_DAILY_LIMIT else 0,
        "warning": today_count >= GEMINI_FREE_DAILY_LIMIT * 0.8,
    }
