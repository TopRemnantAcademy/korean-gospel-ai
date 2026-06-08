"""GET /admin/* - collections, health."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..connections import connections
from ..services.vector_store import _make_client


router = APIRouter(prefix="/admin", tags=["admin"])


def _check_admin(authorization):
    if settings.admin_api_key == "change-me":
        raise HTTPException(
            status_code=503,
            detail="관리자 API 비활성화됨 — .env 파일에 ADMIN_API_KEY 를 설정하고 서버를 재시작하세요.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin token")


@router.get("/health")
def health():
    """기본 헬스체크 — 인증 불필요. 민감 정보 제외."""
    return {
        "ok": True,
        "version": "0.3.1",
    }


@router.get("/connections")
def connection_status(authorization=Header(default=None)):
    """모든 외부 API 연결 상태 — connections.py 레지스트리 기반."""
    _check_admin(authorization)
    return connections.status()


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
    now = datetime.now(datetime.UTC)
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


# ----- Recent activity (최근 감사 로그) -----
from ..models.orm import AuditLog


@router.get("/recent-activity")
def recent_activity(limit: int = 20, authorization=Header(default=None)):
    """최근 N개 감사 로그 — 전체 자료에 걸쳐 최신순."""
    _check_admin(authorization)
    limit = max(1, min(limit, 100))
    with get_session() as s:
        rows = (
            s.query(AuditLog)
            .order_by(AuditLog.when.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "log_id": r.log_id,
                "who": r.who,
                "when": r.when.isoformat() if r.when else None,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "from_state": r.from_state,
                "to_state": r.to_state,
                "note": r.note,
            }
            for r in rows
        ]


# ----- App Error Log (런타임 에러 + 슬로우 리퀘스트 조회) -----
from ..models.orm import AppErrorLog


@router.get("/errors")
def list_errors(
    limit: int = 100,
    level: str = None,        # ERROR|SLOW|CRITICAL (None=전체)
    path: str = None,         # URL 경로 필터 (부분 일치)
    hours: int = 24,          # 최근 N시간
    authorization=Header(default=None),
):
    """런타임 에러 + 슬로우 리퀘스트 로그 조회."""
    _check_admin(authorization)
    limit = max(1, min(limit, 500))
    hours = max(1, min(hours, 720))  # 최대 30일
    since = datetime.now(datetime.UTC) - timedelta(hours=hours)

    with get_session() as s:
        q = (
            s.query(AppErrorLog)
            .filter(AppErrorLog.timestamp >= since)
            .order_by(AppErrorLog.timestamp.desc())
        )
        if level:
            q = q.filter(AppErrorLog.level == level.upper())
        if path:
            q = q.filter(AppErrorLog.path.contains(path))
        rows = q.limit(limit).all()
        return [
            {
                "error_id":      r.error_id,
                "timestamp":     r.timestamp.isoformat() if r.timestamp else None,
                "level":         r.level,
                "method":        r.method,
                "path":          r.path,
                "status_code":   r.status_code,
                "error_type":    r.error_type,
                "error_message": r.error_message,
                "traceback":     r.traceback,
                "duration_ms":   r.duration_ms,
                "request_id":    r.request_id,
                "client_ip":     r.client_ip,
            }
            for r in rows
        ]


# ----- 구독 업그레이드 (관리자 수동 처리) -----
from pydantic import BaseModel as _BM

class SubscriptionUpgradeIn(_BM):
    tier: str           # member | supporter | guest
    extend_trial_days: int = 0   # 체험 연장 (0=무시)


@router.patch("/subscribers/{sub_id}/subscription")
def upgrade_subscription(
    sub_id: str,
    payload: SubscriptionUpgradeIn,
    authorization=Header(default=None),
):
    """구독 티어 변경 + 체험 연장. 관리자 전용."""
    _check_admin(authorization)
    allowed = {"guest", "member", "supporter"}
    if payload.tier not in allowed:
        from fastapi import HTTPException
        raise HTTPException(400, f"tier must be one of {allowed}")

    with get_session() as s:
        from ..models.orm import Subscriber
        row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(404, "subscriber not found")

        old_tier = row.subscription_tier
        row.subscription_tier = payload.tier

        if payload.tier in ("member", "supporter"):
            row.subscribed_at = datetime.now(datetime.UTC)
            row.trial_expires_at = None   # 유료 전환 시 만료 제거
        elif payload.extend_trial_days > 0:
            base = max(row.trial_expires_at or datetime.now(datetime.UTC), datetime.now(datetime.UTC))
            row.trial_expires_at = base + timedelta(days=payload.extend_trial_days)

        # 캐시 무효화
        try:
            from ..middleware.rate_limit import invalidate_sub_cache
            invalidate_sub_cache(sub_id)
        except Exception:
            pass

        return {
            "ok": True,
            "sub_id": sub_id,
            "old_tier": old_tier,
            "new_tier": row.subscription_tier,
            "trial_expires_at": row.trial_expires_at.isoformat() if row.trial_expires_at else None,
        }


# ----- 구독 현황 통계 -----
@router.get("/subscription-stats")
def subscription_stats(authorization=Header(default=None)):
    """구독 티어별 사용자 수 + 체험 만료 임박자 수."""
    _check_admin(authorization)
    from ..models.orm import Subscriber
    now = datetime.now(datetime.UTC)
    tomorrow = now + timedelta(days=1)
    with get_session() as s:
        total = s.query(Subscriber).count()
        by_tier = {}
        for row in s.query(Subscriber).all():
            t = row.subscription_tier or "guest"
            by_tier[t] = by_tier.get(t, 0) + 1
        # 체험 만료 임박 (24시간 내)
        expiring_soon = s.query(Subscriber).filter(
            Subscriber.subscription_tier == "guest",
            Subscriber.trial_expires_at != None,
            Subscriber.trial_expires_at > now,
            Subscriber.trial_expires_at <= tomorrow,
        ).count()
        # 이미 만료
        already_expired = s.query(Subscriber).filter(
            Subscriber.subscription_tier == "guest",
            Subscriber.trial_expires_at != None,
            Subscriber.trial_expires_at <= now,
        ).count()
    return {
        "total": total,
        "by_tier": by_tier,
        "trial_expiring_24h": expiring_soon,
        "trial_expired": already_expired,
    }


@router.get("/error-stats")
def error_stats(authorization=Header(default=None)):
    """에러 요약 통계 — 사이드바 뱃지 및 대시보드 지표용."""
    _check_admin(authorization)
    now = datetime.now(datetime.UTC)
    h1   = now - timedelta(hours=1)
    h24  = now - timedelta(hours=24)
    d7   = now - timedelta(days=7)

    with get_session() as s:
        def _count(since, lvl=None):
            q = s.query(AppErrorLog).filter(AppErrorLog.timestamp >= since)
            if lvl:
                q = q.filter(AppErrorLog.level == lvl)
            return q.count()

        return {
            "errors_1h":       _count(h1,  "ERROR"),
            "errors_24h":      _count(h24, "ERROR"),
            "errors_7d":       _count(d7,  "ERROR"),
            "critical_1h":     _count(h1,  "CRITICAL"),
            "critical_24h":    _count(h24, "CRITICAL"),
            "slow_24h":        _count(h24, "SLOW"),
            "slow_critical_24h": _count(h24, "CRITICAL"),
            "total_24h":       _count(h24),
        }


# ----- 설정 조회 (현재 로드된 값 반환, 민감 값은 마스킹) -----
@router.get("/settings")
def get_settings(authorization=Header(default=None)):
    """현재 백엔드에 로드된 설정 반환. 민감한 키는 마스킹 처리."""
    _check_admin(authorization)

    def _mask(val: str | None, show_last: int = 4) -> str | None:
        if not val:
            return None
        if len(val) <= show_last + 2:
            return "****"
        return f"****{val[-show_last:]}"

    return {
        "llm": {
            "provider":          settings.llm_provider,
            "fallback_enabled":  settings.llm_fallback_enabled,
            "fallback_chain":    settings.llm_fallback_chain,
            "gemini_model":      settings.gemini_model,
            "openai_model":      settings.openai_model,
            "claude_model":      settings.claude_model,
            "ollama_host":       settings.ollama_host,
            "ollama_model":      settings.ollama_model,
            "deepseek_model":    settings.deepseek_model,
            "deepseek_base_url": settings.deepseek_base_url,
            # 마스킹
            "google_api_key":    _mask(settings.google_api_key),
            "openai_api_key":    _mask(settings.openai_api_key),
            "anthropic_api_key": _mask(settings.anthropic_api_key),
            "deepseek_api_key":  _mask(settings.deepseek_api_key),
        },
        "embedding": {
            "embedder":       settings.embedder,
            "embedder_list":  settings.embedder_list,
            "reranker":       settings.reranker,
            "hf_token":       _mask(settings.hf_token),
            "voyage_api_key": _mask(settings.voyage_api_key),
            "cohere_api_key": _mask(settings.cohere_api_key),
        },
        "retrieval": {
            "top_k":        settings.retrieval_top_k,
            "rerank_top_n": settings.rerank_top_n,
            "dense_weight": settings.dense_weight,
            "sparse_weight": settings.sparse_weight,
        },
        "vector_store": {
            "qdrant_url":               settings.qdrant_url,
            "qdrant_collection_prefix": settings.qdrant_collection_prefix,
            "qdrant_sparse_enabled":    settings.qdrant_sparse_enabled,
            "qdrant_api_key":           _mask(settings.qdrant_api_key),
        },
        "auth": {
            "admin_api_key": _mask(settings.admin_api_key),
            "dify_api_key":  _mask(settings.dify_api_key),
            "cors_origins":  settings.cors_origins,
            "app_password":  "****" if settings.app_password else "(없음)",
        },
        "features": {
            "policy_enabled":               settings.policy_enabled,
            "salvation_detection_enabled":  settings.salvation_detection_enabled,
            "salvation_prompt_enabled":     settings.salvation_prompt_enabled,
            "retriever_boost_enabled":      settings.retriever_boost_enabled,
            "legalism_check_enabled":       settings.legalism_check_enabled,
            "gospel_core_fallback_enabled": settings.gospel_core_fallback_enabled,
            "token_quota_enabled":          settings.token_quota_enabled,
            "rate_limit_enabled":           settings.rate_limit_enabled,
        },
        "quota": {
            "tokens_daily_guest":        settings.tokens_daily_guest,
            "tokens_monthly_member":     settings.tokens_monthly_member,
            "tokens_monthly_supporter":  settings.tokens_monthly_supporter,
            "token_estimate_per_request": settings.token_estimate_per_request,
        },
        "langfuse": {
            "enabled":     settings.langfuse_enabled,
            "host":        settings.langfuse_host,
            "public_key":  _mask(settings.langfuse_public_key),
            "secret_key":  _mask(settings.langfuse_secret_key),
        },
        "misc": {
            "log_level": settings.log_level,
            "data_dir":  settings.data_dir,
        },
    }
