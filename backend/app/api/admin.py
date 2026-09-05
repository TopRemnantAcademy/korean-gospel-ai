"""GET /admin/* - collections, health."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from qdrant_client import models as qm

from ..config import settings
from ..connections import connections
from ..db import get_session
from ..services.vector_store import _make_client
from ..services.embedding.factory import get_embedder


router = APIRouter(prefix="/admin", tags=["admin"])


from .auth import check_admin as _check_admin

import logging

_logger = logging.getLogger(__name__)


def _safe_err(label: str, e: Exception) -> str:
    """관리자 엔드포인트라도 내부 예외 문자열(호스트/경로/SQL)을 클라이언트에
    노출하지 않고 서버 로그에만 기록한다."""
    _logger.warning("[admin] %s 실패: %s", label, e)
    return "내부 오류가 발생했습니다 (서버 로그를 확인하세요)"


@router.get("/health")
def health():
    """기본 헬스체크 — 인증 불필요. 민감 정보 제외."""
    return {
        "ok": True,
        "version": "0.3.1",
    }


@router.get("/services-health")
def services_health(authorization=Header(default=None)):
    """각 주요 기능의 헬스 체크.

    반환: {
      "services": {
        "documents": {"ok": bool, "message": str},
        "search": {"ok": bool, "message": str},
        "memory": {"ok": bool, "message": str},
        "glossary": {"ok": bool, "message": str},
        "chat": {"ok": bool, "message": str},
        "jobs": {"ok": bool, "message": str},
      },
      "overall": "healthy" | "degraded" | "unavailable"
    }
    """
    _check_admin(authorization)
    services = {}

    # 1. Documents (DB 접근)
    try:
        from ..models.orm import Document
        with get_session() as s:
            count = s.query(Document).count()
        services["documents"] = {"ok": True, "message": f"{count}개 자료"}
    except Exception as e:
        services["documents"] = {"ok": False, "message": _safe_err("documents", e)}

    # 2. Search (Qdrant 벡터 DB)
    try:
        client, _is_server = _make_client()
        if client:
            cols = client.get_collections().collections
            col_count = len(cols) if cols else 0
            services["search"] = {"ok": True, "message": f"{col_count}개 인덱스"}
        else:
            services["search"] = {"ok": False, "message": "Qdrant 연결 불가"}
    except Exception as e:
        services["search"] = {"ok": False, "message": _safe_err("search", e)}

    # 3. Memory/Interactions (DB 접근)
    try:
        with get_session() as s:
            from ..models.orm import Interaction
            count = s.query(Interaction).count()
        services["memory"] = {"ok": True, "message": f"{count}개 기록"}
    except Exception as e:
        services["memory"] = {"ok": False, "message": _safe_err("memory", e)}

    # 4. 번역 용어집 (JSON 단일 진실공급원)
    try:
        from ..services.enhanced_rag.glossary_manager import term_count
        count = term_count()
        services["glossary"] = {
            "ok": True,
            "message": f"번역 용어집 {count}개 (KO→ZH+EN)",
        }
    except Exception as e:
        services["glossary"] = {"ok": False, "message": _safe_err("glossary", e)}

    # 5. Chat (LLM 연결 상태 체크)
    try:
        conn_status = connections.status()
        active_llm = conn_status.get("active_llm", "unknown")
        llm_state = conn_status.get(active_llm.lower() if active_llm else "unknown", "missing")
        if llm_state in ("ok", "active"):
            services["chat"] = {"ok": True, "message": f"LLM: {active_llm}"}
        else:
            services["chat"] = {"ok": False, "message": f"LLM 미설정 또는 오류: {active_llm}"}
    except Exception as e:
        services["chat"] = {"ok": False, "message": _safe_err("chat", e)}

    # 6. Jobs (백그라운드 작업 큐)
    try:
        with get_session() as s:
            from ..models.orm import BackgroundJob
            pending = s.query(BackgroundJob).filter(BackgroundJob.status == "pending").count()
            running = s.query(BackgroundJob).filter(BackgroundJob.status == "running").count()
        services["jobs"] = {"ok": True, "message": f"대기중 {pending}, 실행중 {running}"}
    except Exception as e:
        services["jobs"] = {"ok": False, "message": _safe_err("jobs", e)}

    # Overall 상태 판정
    ok_count = sum(1 for s in services.values() if s["ok"])
    total_count = len(services)
    if ok_count == total_count:
        overall = "healthy"
    elif ok_count >= total_count * 0.5:
        overall = "degraded"
    else:
        overall = "unavailable"

    return {
        "services": services,
        "overall": overall,
        "ok_count": ok_count,
        "total_count": total_count,
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
        return {"collections": [], "warning": _safe_err("qdrant_init", e)}

    try:
        col_list = client.get_collections().collections
    except Exception as e:
        return {"collections": [], "warning": _safe_err("qdrant_list", e)}

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





@router.get("/chunks")
def list_chunks(
    authorization=Header(default=None),
    collection: str | None = None,
    limit: int = 25,
    offset: str | None = None,
):
    """Qdrant 청크 브라우저 (임베디드/서버 모드 통합, 읽기 전용).

    임베디드(local:) 모드에서도 백엔드 프로세스가 보유한 동일 Qdrant 인스턴스를
    재사용하므로 잠금 충돌 없이 청크를 직접 조회할 수 있다. 벡터는 제외하고
    페이로드(text·메타)만 반환한다. 관리자 전용.
    """
    _check_admin(authorization)
    try:
        client, _is_server = _make_client()
    except Exception as e:
        return {"points": [], "collections": [], "total": 0,
                "warning": _safe_err("qdrant_init", e)}

    try:
        col_list = client.get_collections().collections
    except Exception as e:
        return {"points": [], "collections": [], "total": 0,
                "warning": _safe_err("qdrant_list", e)}

    collections = [c.name for c in col_list]
    if not collections:
        return {"points": [], "collections": [], "total": 0,
                "warning": "Qdrant에 컬렉션이 없습니다."}

    # 대상 컬렉션: 명시 지정 우선, 없으면 포인트가 가장 많은 컬렉션
    if collection and collection in collections:
        target = collection
    else:
        target = None
        best = -1
        for name in collections:
            try:
                cnt = client.count(collection_name=name).count
            except Exception:
                cnt = 0
            if cnt > best:
                best = cnt
                target = name

    limit = max(1, min(int(limit), 200))

    # offset 은 Qdrant scroll 의 PointId 커서(int 또는 UUID 문자열) — 정수
    # 인덱스(0,25,50...)가 아니다. "0" 또는 미제공 시 첫 페이지(None)로 처리.
    scroll_offset = None
    if offset not in (None, "", "0"):
        scroll_offset = _coerce_point_id(offset)

    try:
        points, next_offset = client.scroll(
            collection_name=target,
            limit=limit,
            offset=scroll_offset,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        return {"points": [], "collections": collections, "total": 0,
                "collection": target, "warning": _safe_err("qdrant_scroll", e)}

    total = 0
    try:
        total = client.count(collection_name=target).count
    except Exception:
        total = len(points)

    out = []
    for p in points:
        payload = p.payload or {}
        out.append({
            "id": str(p.id),
            "text": str(payload.get("text", "")),
            "payload": payload,
        })

    return {
        "collection": target,
        "collections": collections,
        "total": total,
        "points": out,
        "limit": limit,
        "offset": scroll_offset,
        "next_offset": next_offset,
    }


# ----- 청크 관리 전문 도구 (작업 CC): search / delete / patch / stats -----

def _coerce_point_id(s: str):
    """Qdrant point id 는 int 또는 UUID 문자열. Qdrant Client 는 str/int 만 허용하므로
    UUID 도 문자열로 반환한다 (uuid.UUID 객체 전달 시 검증 오류)."""
    try:
        return int(s)
    except (ValueError, TypeError):
        return s


def _resolve_target_collection(client, collection):
    """list_chunks 와 동일 로직: 명시 지정 우선, 없으면 포인트 최다 컬렉션."""
    try:
        col_list = client.get_collections().collections
    except Exception as e:
        raise RuntimeError(_safe_err("qdrant_list", e))
    collections = [c.name for c in col_list]
    if not collections:
        raise RuntimeError("Qdrant에 컬렉션이 없습니다.")
    if collection and collection in collections:
        return collection, collections
    target = None
    best = -1
    for name in collections:
        try:
            cnt = client.count(collection_name=name).count
        except Exception:
            cnt = 0
        if cnt > best:
            best = cnt
            target = name
    return target, collections


def _embedder_name_for_collection(collection: str) -> str:
    """{prefix}_{embedder_name} 규칙에서 임베더 이름 추출 (prefix 무관)."""
    try:
        probe = settings.collection_name("__probe__")
        prefix = probe.replace("__probe__", "")
    except Exception:
        prefix = ""
    if prefix and collection.startswith(prefix):
        return collection[len(prefix):]
    return settings.embedder


class _VecList:
    @staticmethod
    def to_list(vec):
        return vec.tolist() if hasattr(vec, "tolist") else list(vec)


class ChunkSearchRequest(BaseModel):
    query: str
    collection: str | None = None
    limit: int = 10
    with_vectors: bool = False


class ChunkPatchRequest(BaseModel):
    text: str | None = None
    payload: dict | None = None   # 추가/수정할 메타 필드
    reembed: bool = True          # text 변경 시 dense 벡터 재계산


@router.post("/chunks/search")
def search_chunks(body: ChunkSearchRequest, authorization=Header(default=None)):
    """시맨틱 검색: 쿼리를 임베딩해 RAG가 실제로 반환하는 청크/점수 확인 (RAG 디버깅)."""
    _check_admin(authorization)
    if not body.query or not body.query.strip():
        return {"points": [], "warning": "query가 비어있습니다."}
    try:
        client, _is_server = _make_client()
    except Exception as e:
        return {"points": [], "warning": _safe_err("qdrant_init", e)}
    try:
        target, collections = _resolve_target_collection(client, body.collection)
    except Exception as e:
        return {"points": [], "collections": [], "warning": str(e)}
    embedder_name = _embedder_name_for_collection(target)
    try:
        emb = get_embedder(embedder_name)
        vec = emb.embed_query(body.query.strip())
    except Exception as e:
        return {"points": [], "collections": collections, "collection": target,
                "warning": _safe_err("embed", e)}
    limit = max(1, min(int(body.limit), 50))
    try:
        resp = client.query_points(
            collection_name=target,
            query=_VecList.to_list(vec),
            using="dense",
            limit=limit,
            with_payload=True,
            with_vectors=bool(body.with_vectors),
        )
    except Exception as e:
        return {"points": [], "collections": collections, "collection": target,
                "warning": _safe_err("qdrant_search", e)}
    out = []
    for p in resp.points:
        payload = p.payload or {}
        out.append({
            "id": str(p.id),
            "score": float(getattr(p, "score", 0.0) or 0.0),
            "text": str(payload.get("text", "")),
            "payload": payload,
        })
    return {"collection": target, "collections": collections,
            "query": body.query, "points": out}


@router.delete("/chunks/{chunk_id}")
def delete_chunk(
    chunk_id: str,
    authorization=Header(default=None),
    collection: str | None = None,
):
    """청크 삭제 — 품질 불량(공백 오염 등) 청크 즉시 제거."""
    _check_admin(authorization)
    try:
        client, _is_server = _make_client()
    except Exception as e:
        return {"ok": False, "warning": _safe_err("qdrant_init", e)}
    try:
        target, collections = _resolve_target_collection(client, collection)
    except Exception as e:
        return {"ok": False, "warning": str(e)}
    pid = _coerce_point_id(chunk_id)
    try:
        client.delete(collection_name=target,
                      points_selector=qm.PointIdsList(points=[pid]))
    except KeyError:
        # 임베디드 Qdrant 는 존재하지 않는 point id 삭제 시 KeyError 발생
        _logger.warning("[admin] chunks delete: 존재하지 않는 ID %s (col=%s)",
                       chunk_id, target)
        return {"ok": False, "collection": target, "id": chunk_id,
                "not_found": True,
                "warning": "해당 ID의 청크를 찾을 수 없습니다 (존재하지 않는 ID)."}
    except Exception as e:
        return {"ok": False, "collection": target, "id": chunk_id,
                "warning": _safe_err("qdrant_delete", e)}
    return {"ok": True, "collection": target, "id": chunk_id}


@router.patch("/chunks/{chunk_id}")
def patch_chunk(
    chunk_id: str,
    body: ChunkPatchRequest,
    authorization=Header(default=None),
    collection: str | None = None,
):
    """청크 수정 — 텍스트/메타 갱신. text 변경 시 dense 벡터 재계산(sparse 보존)."""
    _check_admin(authorization)
    try:
        client, _is_server = _make_client()
    except Exception as e:
        return {"ok": False, "warning": _safe_err("qdrant_init", e)}
    try:
        target, collections = _resolve_target_collection(client, collection)
    except Exception as e:
        return {"ok": False, "warning": str(e)}
    pid = _coerce_point_id(chunk_id)

    new_payload = {}
    if body.text is not None:
        new_payload["text"] = body.text
    if body.payload:
        new_payload.update(body.payload)

    result = {"ok": True, "collection": target, "id": chunk_id, "updated": []}

    if new_payload:
        try:
            client.set_payload(collection_name=target,
                              payload=new_payload,
                              points=[pid])
            result["updated"].append("payload")
        except KeyError:
            # 임베디드 Qdrant 는 존재하지 않는 point id 수정 시 KeyError 발생
            _logger.warning("[admin] chunks patch: 존재하지 않는 ID %s (col=%s)",
                           chunk_id, target)
            return {"ok": False, "collection": target, "id": chunk_id,
                    "not_found": True,
                    "warning": "해당 ID의 청크를 찾을 수 없습니다 (존재하지 않는 ID)."}
        except Exception as e:
            return {"ok": False, "collection": target, "id": chunk_id,
                    "warning": _safe_err("qdrant_set_payload", e)}

    if body.text is not None and body.reembed:
        embedder_name = _embedder_name_for_collection(target)
        try:
            emb = get_embedder(embedder_name)
            vec = emb.embed_query(body.text)
            client.update_vectors(
                collection_name=target,
                points=[qm.PointVectors(
                    id=pid,
                    vector={"dense": _VecList.to_list(vec)},
                )],
            )
            result["updated"].append("vector")
        except KeyError:
            return {"ok": False, "collection": target, "id": chunk_id,
                    "not_found": True,
                    "warning": "해당 ID의 청크를 찾을 수 없습니다 (존재하지 않는 ID)."}
        except Exception as e:
            result["warning"] = _safe_err("reembed", e)

    return result


@router.get("/chunks/stats")
def chunk_stats(
    authorization=Header(default=None),
    collection: str | None = None,
    sample_limit: int = 20000,
):
    """청크 품질 통계 — 빈 텍스트/공백 오염율 등 운영 지표 집계."""
    _check_admin(authorization)
    try:
        client, _is_server = _make_client()
    except Exception as e:
        return {"warning": _safe_err("qdrant_init", e)}
    try:
        target, collections = _resolve_target_collection(client, collection)
    except Exception as e:
        return {"warning": str(e)}
    total = 0
    try:
        total = client.count(collection_name=target).count
    except Exception:
        pass

    sample_limit = max(1, min(int(sample_limit), 50000))
    empties = 0
    short = 0
    high_space = 0
    multispaces = 0
    by_source: dict = {}
    examined = 0
    offset = None
    while examined < sample_limit:
        try:
            pts, offset = client.scroll(
                collection_name=target, limit=500, offset=offset,
                with_payload=True, with_vectors=False,
            )
        except Exception as e:
            return {"collection": target, "total": total,
                    "warning": _safe_err("qdrant_scroll", e)}
        if not pts:
            break
        for p in pts:
            examined += 1
            payload = p.payload or {}
            text = str(payload.get("text", ""))
            if not text.strip():
                empties += 1
            elif len(text) < 5:
                short += 1
            if text:
                if (text.count(" ") / len(text)) >= 0.35:
                    high_space += 1
                if ("  " in text) or ("\t" in text):
                    multispaces += 1
            src = (payload.get("source") or payload.get("doc_id")
                   or payload.get("file") or "unknown")
            by_source[src] = by_source.get(src, 0) + 1
        if offset is None:
            break

    return {
        "collection": target,
        "collections": collections,
        "total": total,
        "examined": examined,
        "empty_text": empties,
        "very_short_lt5": short,
        "high_space_ratio_ge0_35": high_space,
        "multi_space_or_tab": multispaces,
        "top_sources": dict(sorted(by_source.items(),
                                   key=lambda x: -x[1])[:15]),
    }


# ----- Usage stats (Gemini 한도 모니터링) -----
from datetime import datetime, timedelta, timezone
from ..models.orm import Interaction


GEMINI_FREE_DAILY_LIMIT = 1500   # Gemini 2.5 flash 일일 무료 한도
GEMINI_FREE_RPM_LIMIT = 15       # 분당


@router.get("/usage")
def usage(authorization=Header(default=None)):
    _check_admin(authorization)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
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
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

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



@router.get("/error-stats")
def error_stats(authorization=Header(default=None)):
    """에러 요약 통계 — 사이드바 뱃지 및 대시보드 지표용."""
    _check_admin(authorization)
    now = datetime.now(timezone.utc)
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
        },
        "quota": {
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


# ----- 백데이터 분석 (interaction 소스 분석) -----
import re
from collections import Counter


@router.get("/analytics/interactions")
def analytics_interactions(limit: int = 200, authorization=Header(default=None)):
    """질문 트렌드 / 문서 인용 랭킹 / 키워드 트렌드 / 피드백 통계 (읽기 전용).

    콜라보 파일 V-1 지시 구현. V-1 원안의 `GROUP BY target_lang`(언어별 분포)은
    `interaction` 테이블에 해당 컬럼이 없어 제외했다 — 할루시네이션 보정.
    """
    _check_admin(authorization)
    limit = max(1, min(int(limit), 1000))

    from ..models.orm import Document

    with get_session() as s:
        rows = (
            s.query(
                Interaction.question,
                Interaction.cited_versions,
                Interaction.feedback,
                Interaction.low_coverage,
            )
            .order_by(Interaction.created_at.desc())
            .limit(limit * 5)  # 충분한 표본
            .all()
        )
        total_docs = s.query(Document).count()

    question_counter: Counter = Counter()
    doc_counter: Counter = Counter()
    keyword_counter: Counter = Counter()
    feedback = {"positive": 0, "negative": 0, "none": 0}
    low_coverage_count = 0
    total = 0

    for q, cvs, fb, lc in rows:
        total += 1
        if lc:
            low_coverage_count += 1
        q = (q or "").strip()
        if q:
            question_counter[q] += 1
            for tok in re.findall(r"[가-힣A-Za-z0-9]+", q):
                if len(tok) >= 2:
                    keyword_counter[tok] += 1
        if isinstance(cvs, list):
            for c in cvs:
                if isinstance(c, dict) and c.get("doc_id"):
                    doc_counter[c.get("doc_id")] += 1
        if fb == 1:
            feedback["positive"] += 1
        elif fb == -1:
            feedback["negative"] += 1
        else:
            feedback["none"] += 1

    cited_doc_count = len(doc_counter)
    return {
        "total_interactions": total,
        "sampled": len(rows),
        "question_trends": [
            {"question": k, "count": v} for k, v in question_counter.most_common(limit)
        ],
        "doc_citation_ranking": [
            {"doc_id": k, "citations": v} for k, v in doc_counter.most_common(limit)
        ],
        "keyword_trends": [
            {"keyword": k, "count": v} for k, v in keyword_counter.most_common(limit)
        ],
        "feedback": feedback,
        "low_coverage": {
            "count": low_coverage_count,
            "pct": round(low_coverage_count / total * 100, 1) if total else 0.0,
        },
        "coverage": {
            "total_documents": total_docs,
            "cited_documents": cited_doc_count,
            "uncited_documents": max(total_docs - cited_doc_count, 0),
        },
        "language_distribution": {
            "available": False,
            "reason": "interaction 테이블에 target_lang 컬럼이 없어 언어별 분포 제공 불가",
        },
    }


# ── 계정 차단/해제 관리 (2026-08-18) ──────────────────────────────
class _BanReq(BaseModel):
    reason: str = ""


@router.post("/subscribers/{subscriber_id}/ban")
def admin_ban_subscriber(
    subscriber_id: str,
    req: _BanReq | None = None,
    authorization: str = Header(default=""),
):
    """계정 차단: flagged_as_bot=True 설정. 차단된 계정은 로그인/재가입 불가.

    인증: check_admin (X-Admin-Key 또는 회원 인증).
    """
    _check_admin(authorization or "")
    reason = req.reason if req else ""
    from ..models.orm import Subscriber
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == subscriber_id).first()
        if not sub:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        sub.flagged_as_bot = True
        s.add(sub)
        s.flush()
    return {"ok": True, "subscriber_id": subscriber_id, "banned": True, "reason": reason}


@router.post("/subscribers/{subscriber_id}/unban")
def admin_unban_subscriber(
    subscriber_id: str,
    authorization: str = Header(default=""),
):
    """계정 차단 해제: flagged_as_bot=False."""
    _check_admin(authorization or "")
    from ..models.orm import Subscriber
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == subscriber_id).first()
        if not sub:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        sub.flagged_as_bot = False
        s.add(sub)
        s.flush()
    return {"ok": True, "subscriber_id": subscriber_id, "banned": False}
