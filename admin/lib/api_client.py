"""FastAPI 백엔드 호출 헬퍼. 모든 페이지에서 공유."""
from __future__ import annotations

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
# admin/pages/* 면 두 단계 위로, admin/* 면 한 단계 위로
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent  # admin -> project root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


import os
from typing import Optional

import httpx
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "change-me")

import functools

def safe_api_call(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            st.error(f"백엔드 API 호출 실패: {e}")
            return None
    return wrapper


def _headers(admin=True) -> dict:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"} if admin else {}


def _handle(r: httpx.Response):
    if r.status_code >= 400:
        st.error(f"[{r.status_code}] {r.text[:600]}")
        return None
    return r.json()


def get_health() -> Optional[dict]:
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/health", headers=_headers())
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# ----- 백데이터 분석 (interaction 소스 분석) -----
@safe_api_call
def get_interaction_analytics(limit: int = 200) -> Optional[dict]:
    """콜라보 파일 V-1 구현 — 질문/인용/키워드 트렌드 + 피드백 통계."""
    with httpx.Client(timeout=60) as c:
        r = c.get(
            f"{API_BASE}/admin/analytics/interactions",
            headers=_headers(),
            params={"limit": limit},
        )
    return _handle(r)


# ----- 활동 모니터링 (클라이언트 시청/행동 로그) -----
@safe_api_call
def get_activity_summary(days: int = 30) -> Optional[dict]:
    """기간 집계 — DAU/WAU/MAU, 이벤트 분포, Top 시청/검색."""
    with httpx.Client(timeout=60) as c:
        r = c.get(
            f"{API_BASE}/admin/activity/summary",
            headers=_headers(),
            params={"days": days},
        )
    return _handle(r)


@safe_api_call
def get_activity_events(
    event_type: Optional[str] = None,
    subscriber_id: Optional[str] = None,
    media_id: Optional[str] = None,
    from_: Optional[str] = None,
    to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Optional[list]:
    """필터 기반 이벤트 목록 조회."""
    params = {"limit": limit, "offset": offset}
    if event_type:
        params["event_type"] = event_type
    if subscriber_id:
        params["subscriber_id"] = subscriber_id
    if media_id:
        params["media_id"] = media_id
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    with httpx.Client(timeout=60) as c:
        r = c.get(
            f"{API_BASE}/admin/activity/events",
            headers=_headers(),
            params=params,
        )
    return _handle(r)


# ----- Documents -----
def list_documents(state: Optional[str] = None) -> Optional[list]:
    params = {"state": state} if state else None
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/documents", headers=_headers(), params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        st.error("Cannot connect to API.")
        return None


@safe_api_call
def get_document(doc_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/documents/{doc_id}", headers=_headers())
    return _handle(r)


@safe_api_call
def upload_document(file_name: str, file_bytes: bytes, **form_fields) -> Optional[dict]:
    files = {"file": (file_name, file_bytes)}
    # 대용량 PDF/DOCX 추출은 최대 5분 소요 가능 — 타임아웃 300s 로 상향
    with httpx.Client(timeout=300) as c:
        r = c.post(
            f"{API_BASE}/documents/upload",
            headers=_headers(), files=files, data=form_fields,
        )
    return _handle(r)


def ingest_text_async(
    title: str,
    content: str,
    doc_type: str = "sermon",
    series: str = "",
    speaker: str = "",
    topic_tags: str = "",
    scripture_refs: str = "",
    summary: str = "",
) -> Optional[dict]:
    """텍스트 직접 입력 → 비동기 처리. {job_id} 즉시 반환."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(
                f"{API_BASE}/documents/ingest-text",
                headers=_headers(),
                data={
                    "title": title, "content": content, "doc_type": doc_type,
                    "series": series, "speaker": speaker,
                    "topic_tags": topic_tags, "scripture_refs": scripture_refs,
                    "summary": summary,
                },
            )
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        st.error("Cannot connect to API.")
        return None



@safe_api_call
def ingest_clean_chunks(file_name: str, file_bytes: bytes) -> Optional[dict]:
    """정제 데이터 직행(Fast-Track): JSON/JSONL 파일을 번역 없이 바로 적재.

    반환 예: {"status":"ok","collection":"enhanced_rag_bge_m3",
              "ingested":{"doc_id":12},"total_chunks":12}
    """
    files = {"file": (file_name, file_bytes, "application/json")}
    with httpx.Client(timeout=300) as c:
        r = c.post(
            f"{API_BASE}/documents/ingest-clean-chunks",
            headers=_headers(),
            files=files,
        )
    return _handle(r)


def upload_document_async(file_name: str, file_bytes: bytes, **form_fields) -> Optional[dict]:
    """비동기 업로드 — {job_id} 즉시 반환. 폴링: get_job(job_id)."""
    files = {"file": (file_name, file_bytes)}
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(
                f"{API_BASE}/documents/upload-async",
                headers=_headers(), files=files, data=form_fields,
            )
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        st.error("Cannot connect to API.")
        return None


def publish_version_async(doc_id: str, version_id: str) -> Optional[dict]:
    """비동기 공개 — {job_id} 즉시 반환."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(
                f"{API_BASE}/documents/{doc_id}/versions/{version_id}/publish-async",
                headers=_headers(),
            )
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def get_job(job_id: str) -> dict:
    """백그라운드 작업 상태 폴링. GET /jobs/{job_id}

    반환 규칙 (None 절대 반환 안 함 — 호출자가 유형별 처리 가능):
      정상 진행  → {"status": "...", "progress_pct": ..., ...}
      404 없음   → {"__not_found__": True, "job_id": job_id}
      서버 오류  → {"__error__": True, "error_type": "server_error",
                    "status_code": int, "message": str}
      타임아웃   → {"__error__": True, "error_type": "timeout", ...}
      연결 불가  → {"__error__": True, "error_type": "connection", ...}
      기타 예외  → {"__error__": True, "error_type": "unknown", ...}
    """
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/jobs/{job_id}", headers=_headers())
        if r.status_code == 404:
            return {"__not_found__": True, "job_id": job_id}
        if r.status_code >= 400:
            return {
                "__error__": True,
                "error_type": "server_error",
                "status_code": r.status_code,
                "message": f"HTTP {r.status_code}: {r.text[:300]}",
                "job_id": job_id,
            }
        return r.json()
    except httpx.TimeoutException:
        return {
            "__error__": True,
            "error_type": "timeout",
            "status_code": None,
            "message": f"서버 응답 없음 (5초 초과) — {API_BASE} 서버가 멈춘 것 같아요",
            "job_id": job_id,
        }
    except (httpx.HTTPError, ValueError):
        return {
            "__error__": True,
            "error_type": "connection",
            "status_code": None,
            "message": f"연결 거부 — {API_BASE} 서버가 실행 중이 아닌 것 같아요",
            "job_id": job_id,
        }
    except Exception as exc:
        return {
            "__error__": True,
            "error_type": "unknown",
            "status_code": None,
            "message": f"{type(exc).__name__}: {str(exc)[:200]}",
            "job_id": job_id,
        }


def check_backend_health() -> dict:
    """백엔드 서버 상태 상세 진단.

    반환: {ok: bool, latency_ms: int, url: str, error_type?: str, message?: str, data?: dict}
    """
    import time as _time
    t0 = _time.time()
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/admin/health", headers=_headers())
        latency_ms = int((_time.time() - t0) * 1000)
        if r.status_code < 400:
            return {"ok": True, "latency_ms": latency_ms, "url": API_BASE, "data": r.json()}
        return {
            "ok": False, "error_type": "server_error",
            "status_code": r.status_code, "latency_ms": latency_ms,
            "url": API_BASE, "message": f"HTTP {r.status_code}: {r.text[:200]}",
        }
    except httpx.TimeoutException:
        latency_ms = int((_time.time() - t0) * 1000)
        return {
            "ok": False, "error_type": "timeout", "latency_ms": latency_ms,
            "url": API_BASE,
            "message": f"서버가 {latency_ms}ms 동안 응답 없음 → 재시작 필요",
        }
    except (httpx.HTTPError, ValueError):
        latency_ms = int((_time.time() - t0) * 1000)
        return {
            "ok": False, "error_type": "connection", "latency_ms": latency_ms,
            "url": API_BASE, "message": "연결 거부 — 서버가 실행 중이 아님",
        }
    except Exception as exc:
        latency_ms = int((_time.time() - t0) * 1000)
        return {
            "ok": False, "error_type": "unknown", "latency_ms": latency_ms,
            "url": API_BASE, "message": f"{type(exc).__name__}: {str(exc)[:200]}",
        }


@safe_api_call
def patch_meta(doc_id: str, version_id: str, payload: dict) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}",
            headers=_headers(), json=payload,
        )
    return _handle(r)


@safe_api_call
def patch_doc_meta(doc_id: str, payload: dict) -> Optional[dict]:
    """document 레벨 필드 수정 — speaker / series / doc_type."""
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}",
            headers=_headers(), json=payload,
        )
    return _handle(r)


@safe_api_call
def patch_body(doc_id: str, version_id: str, body: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/body",
            headers=_headers(), json={"body": body},
        )
    return _handle(r)


@safe_api_call
def validate_version(doc_id: str, version_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/validate",
            headers=_headers(),
        )
    return _handle(r)


@safe_api_call
def publish_version(doc_id: str, version_id: str) -> Optional[dict]:
    with httpx.Client(timeout=180) as c:
        r = c.post(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/publish",
            headers=_headers(),
        )
    return _handle(r)


@safe_api_call
def archive_document(doc_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.delete(f"{API_BASE}/documents/{doc_id}", headers=_headers())
    return _handle(r)


@safe_api_call
def preview_chunks(doc_id: str, version_id: str) -> Optional[dict]:
    """특정 버전의 청크 미리보기 (텍스트 + 품질 점수).

    백엔드 GET /documents/{doc_id}/versions/{version_id}/preview
    반환: {full_text, quality_score, warnings, chunk_preview[], total_chunks_estimate, ...}
    """
    with httpx.Client(timeout=30) as c:
        r = c.get(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/preview",
            headers=_headers(),
        )
    return _handle(r)


@safe_api_call
def qdrant_scroll(collection: str, limit: int = 20, offset: int = 0) -> Optional[dict]:
    """Qdrant 컬렉션의 포인트를 scroll로 직접 조회 (payload 포함, vector 제외).

    embedded(local:) 모드에서는 REST API가 없으므로 None 반환 (청크뷰어 탭1 비활성).
    서버 모드(QDRANT_URL=http://...)에서는 실제 포인트를 조회한다.
    """
    qdrant_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    if qdrant_url.startswith("local:"):
        return None
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{qdrant_url}/collections/{collection}/points/scroll",
                headers={"Content-Type": "application/json"},
                json={
                    "limit": limit,
                    "offset": offset,
                    "with_payload": True,
                    "with_vector": False,
                },
            )
        if r.status_code < 400:
            return r.json()
        return {"error": f"[{r.status_code}] {r.text[:300]}"}
    except Exception as e:
        return {"error": str(e)[:300]}


@safe_api_call
def list_chunks(collection: Optional[str] = None, limit: int = 25, offset: Optional[str] = None) -> Optional[dict]:
    """Qdrant 청크 브라우저 (임베디드/서버 모드 통합). GET /admin/chunks

    offset 는 Qdrant scroll 의 PointId 커서 (int 또는 UUID 문자열) — 정수 인덱스가
    아니다. 미제공 시 첫 페이지. 반환의 next_offset 을 그대로 다음 호출 offset 으로
    전달해야 한다. 페이로드(text·메타)만 반환.
    반환: {collection, collections, total, points:[{id,text,payload}], limit, offset, next_offset}
    """
    params: dict = {"limit": limit}
    if collection:
        params["collection"] = collection
    if offset not in (None, ""):
        params["offset"] = offset
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/chunks", headers=_headers(), params=params)
    return _handle(r)


# ----- 청크 관리 전문 도구 (작업 CC): search / delete / patch / stats -----

@safe_api_call
def search_chunks(query: str, collection: Optional[str] = None,
                 limit: int = 10, with_vectors: bool = False) -> Optional[dict]:
    """시맨틱 검색 — RAG가 실제로 반환하는 청크/점수 확인. POST /admin/chunks/search"""
    body = {"query": query, "limit": limit, "with_vectors": with_vectors}
    if collection:
        body["collection"] = collection
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{API_BASE}/admin/chunks/search", headers=_headers(), json=body)
    return _handle(r)


@safe_api_call
def delete_chunk(chunk_id: str, collection: Optional[str] = None) -> Optional[dict]:
    """청크 삭제. DELETE /admin/chunks/{chunk_id}"""
    params = {"collection": collection} if collection else None
    with httpx.Client(timeout=30) as c:
        r = c.delete(f"{API_BASE}/admin/chunks/{chunk_id}",
                     headers=_headers(), params=params)
    return _handle(r)


@safe_api_call
def patch_chunk(chunk_id: str, text: Optional[str] = None,
                payload: Optional[dict] = None, reembed: bool = True,
                collection: Optional[str] = None) -> Optional[dict]:
    """청크 수정 — 텍스트/메타 갱신. PATCH /admin/chunks/{chunk_id}"""
    body = {"reembed": reembed}
    if text is not None:
        body["text"] = text
    if payload is not None:
        body["payload"] = payload
    params = {"collection": collection} if collection else None
    with httpx.Client(timeout=60) as c:
        r = c.patch(f"{API_BASE}/admin/chunks/{chunk_id}",
                    headers=_headers(), json=body, params=params)
    return _handle(r)


@safe_api_call
def chunk_stats(collection: Optional[str] = None,
                sample_limit: int = 20000) -> Optional[dict]:
    """청크 품질 통계 — 빈 텍스트/공백 오염율 등. GET /admin/chunks/stats"""
    params: dict = {"sample_limit": sample_limit}
    if collection:
        params["collection"] = collection
    with httpx.Client(timeout=120) as c:
        r = c.get(f"{API_BASE}/admin/chunks/stats", headers=_headers(), params=params)
    return _handle(r)


@safe_api_call
def new_version(doc_id: str, file_name: str, file_bytes: bytes, title: Optional[str] = None) -> Optional[dict]:
    files = {"file": (file_name, file_bytes)}
    data = {"title": title} if title else {}
    with httpx.Client(timeout=120) as c:
        r = c.post(
            f"{API_BASE}/documents/{doc_id}/new-version",
            headers=_headers(), files=files, data=data,
        )
    return _handle(r)


@safe_api_call
def get_audit(doc_id: str) -> Optional[list]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/documents/{doc_id}/audit", headers=_headers())
    return _handle(r)


def recent_audit(limit: int = 20) -> Optional[list]:
    """최근 N개 감사 로그 — 전체 자료에 걸쳐 최신순. GET /admin/recent-activity"""
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(
                f"{API_BASE}/admin/recent-activity",
                headers=_headers(),
                params={"limit": limit},
            )
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


# ----- Search/Chat -----
def chat_ping(user_id: Optional[str] = None) -> Optional[dict]:
    """초경량 기존 사용자 판별. {is_returning, days_away, hint, subscriber_id}
    앱 시작 시 즉시 호출 → is_returning 으로 UI 분기.
    """
    params: dict = {}
    if user_id:
        params["user_id"] = user_id
    try:
        with httpx.Client(timeout=5) as c:          # 타임아웃 5s — 빠른 응답 보장
            r = c.get(f"{API_BASE}/chat/ping", params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def simulate_greeting(
    emotional_state: Optional[str] = None,
    journey_stage: Optional[str] = None,
    salvation_status: str = "unknown",
    days_away: Optional[int] = None,
    total_questions: int = 5,
) -> Optional[dict]:
    """관리자용 메시지 시뮬레이터 — 조건 입력 → 예상 메시지 반환."""
    params: dict = {"salvation_status": salvation_status, "total_questions": total_questions}
    if emotional_state:  params["emotional_state"]  = emotional_state
    if journey_stage:    params["journey_stage"]    = journey_stage
    if days_away is not None: params["days_away"]   = days_away
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/chat/greeting/simulate", params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def get_greeting(user_id: Optional[str] = None, mode: str = "auto", target_lang: str = "ko") -> Optional[dict]:
    """재방문 영적 재해석 메시지. chat_ping() 이 is_returning=True 일 때 호출."""
    params: dict = {"mode": mode, "target_lang": target_lang}
    if user_id:
        params["user_id"] = user_id
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{API_BASE}/chat/greeting", params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


@safe_api_call
def chat(
    query: str,
    history: list,
    llm_provider: Optional[str] = None,
    embedder: Optional[str] = None,
    debug: bool = False,
    target_lang: str = "ko",
    user_id: Optional[str] = None,
    user_context: Optional[str] = None,
) -> Optional[dict]:
    """BUG-07 수정: target_lang / user_id / user_context 를 백엔드 /chat 에 전달.

    - target_lang: 응답 언어 (ko/zh/en/ja). 기본 ko.
    - user_id: sub_id. 미지정 시 백엔드 DEFAULT_USER 사용.
    - user_context: 사용자가 기억시킨 정보 (Gemini 스타일).
    """
    body: dict = {
        "query": query,
        "history": history,
        "llm_provider": llm_provider or None,
        "embedder": embedder or None,
        "debug": debug,
        "target_lang": target_lang,
    }
    if user_id:
        body["user_id"] = user_id
    if user_context:
        body["user_context"] = user_context
    with httpx.Client(timeout=180) as c:
        r = c.post(f"{API_BASE}/chat", json=body)
    return _handle(r)


def chat_stream(
    query: str,
    history: list,
    target_lang: str = "ko",
    user_id: Optional[str] = None,
    user_context: Optional[str] = None,
    on_meta=None,
):
    """SSE 스트리밍 채팅 — 답변 청크를 순차적으로 yield.

    /chat/stream 을 사용해 첫 토큰을 즉시 표시(비스트리밍 /chat 의 57s 블랭크 대기 제거).
    - 텍스트 청크: 그대로 yield (st.write_stream 이 라이브 렌더).
    - 메타데이터(interaction_id/sources/elapsed_ms): on_meta 콜백으로 1회 전달.
    웹/모바일과 동일한 SSE 규약: `data:` 라인 누적 → 공백줄에서 이벤트 확정,
    JSON(dict) 이면 메타, 그 외는 청크, `done` 이벤트에서 종료.
    """
    import json as _json

    body: dict = {"query": query, "history": history, "target_lang": target_lang}
    if user_id:
        body["user_id"] = user_id
    if user_context:
        body["user_context"] = user_context

    try:
        with httpx.Client(timeout=180) as c:
            with c.stream("POST", f"{API_BASE}/chat/stream", json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    yield f"[{r.status_code}] {r.text[:300]}"
                    return
                data_lines: list[str] = []
                for raw in r.iter_lines():
                    if raw == "":                       # 이벤트 경계(공백줄)
                        if not data_lines:
                            continue
                        payload = "\n".join(data_lines)
                        data_lines = []
                        if payload == "done":
                            break
                        meta = None
                        try:
                            obj = _json.loads(payload)
                            if isinstance(obj, dict) and (
                                "interaction_id" in obj or "sources" in obj
                            ):
                                meta = obj
                        except (ValueError, TypeError):
                            meta = None
                        if meta is not None:
                            if on_meta:
                                on_meta(meta)
                        else:
                            yield payload
                        continue
                    if raw.startswith("data:"):
                        line = raw[5:]
                        if line.startswith(" "):
                            line = line[1:]
                        data_lines.append(line)
                    # event: 라인은 무시(종료는 data: done 으로 처리)
    except httpx.HTTPError as e:
        yield f"[연결 오류] {e}"


@safe_api_call
def get_collections() -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/collections", headers=_headers())
    return _handle(r)



# ===== Memory =====
def list_memory(search=None, limit=200, subscriber_id=None):
    params = {"limit": limit}
    if search: params["search"] = search
    if subscriber_id: params["subscriber_id"] = subscriber_id
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/memory/list", headers=_headers(), params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def memory_stats(subscriber_id=None):
    params = {"subscriber_id": subscriber_id} if subscriber_id else None
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/memory/stats", headers=_headers(), params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


@safe_api_call
def delete_memory(interaction_id):
    with httpx.Client(timeout=10) as c:
        r = c.delete(f"{API_BASE}/memory/{interaction_id}", headers=_headers())
    return _handle(r)



# ===== Prompts =====
def get_prompt():
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/prompts/current", headers=_headers())
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


@safe_api_call
def save_prompt(content, note=None):
    with httpx.Client(timeout=10) as c:
        r = c.put(f"{API_BASE}/prompts/current", headers=_headers(),
                  json={"content": content, "note": note})
    return _handle(r)


@safe_api_call
def reset_prompt():
    with httpx.Client(timeout=10) as c:
        r = c.post(f"{API_BASE}/prompts/reset", headers=_headers())
    return _handle(r)


@safe_api_call
def prompt_history():
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{API_BASE}/prompts/history", headers=_headers())
    return _handle(r)



@safe_api_call
def set_feedback(interaction_id, value):
    with httpx.Client(timeout=10) as c:
        r = c.patch(f"{API_BASE}/memory/{interaction_id}/feedback",
                    headers=_headers(), json={"value": value})
    return _handle(r)



@safe_api_call
def bulk_action(doc_ids, action):
    with httpx.Client(timeout=300) as c:
        r = c.post(f"{API_BASE}/documents/bulk-action", headers=_headers(),
                    json={"doc_ids": doc_ids, "action": action})
    return _handle(r)



def get_usage():
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/usage", headers=_headers())
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None

@safe_api_call
def list_subscribers(limit: int = 200, offset: int = 0) -> Optional[list]:
    """구독자 목록 조회 — GET /admin/subscribers/list"""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(
                f"{API_BASE}/admin/subscribers/list",
                headers=_headers(),
                params={"limit": limit, "offset": offset},
            )
        data = _handle(r)
        if isinstance(data, dict):
            return data.get("subscribers", [])
        return data
    except (httpx.HTTPError, ValueError):
        return None


@safe_api_call
def update_subscriber(sub_id: str, payload: dict) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(f"{API_BASE}/admin/subscribers/{sub_id}", headers=_headers(), json=payload)
    return _handle(r)


# ── 이메일 인증 / 티어 관리 (2026-07-23) ──
def resend_verification(sub_id: str) -> Optional[dict]:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{API_BASE}/admin/subscribers/{sub_id}/resend-verification", headers=_headers())
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def verify_override(sub_id: str) -> Optional[dict]:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{API_BASE}/admin/subscribers/{sub_id}/verify", headers=_headers())
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def set_tier(sub_id: str, tier: str, expires_at: str | None = None) -> Optional[dict]:
    try:
        payload = {"tier": tier}
        if expires_at:
            payload["expires_at"] = expires_at
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{API_BASE}/admin/subscribers/{sub_id}/set-tier", headers=_headers(), json=payload)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def get_app_settings() -> Optional[list]:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/settings/app", headers=_headers())
        data = _handle(r)
        if isinstance(data, dict):
            return data.get("settings", [])
        return data
    except (httpx.HTTPError, ValueError):
        return None


def set_app_setting(key: str, value) -> Optional[dict]:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{API_BASE}/admin/settings/app", headers=_headers(), json={"key": key, "value": value})
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def toggle_assume_saved(sub_id: str, value: bool, reason: str = "", also_set_status: Optional[str] = None) -> Optional[dict]:
    """D-C22: assume_saved 토글."""
    payload: dict = {"value": value, "reason": reason}
    if also_set_status:
        payload["also_set_status"] = also_set_status
    try:
        with httpx.Client(timeout=30) as c:
            r = c.patch(f"{API_BASE}/admin/subscribers/{sub_id}/assume-saved", headers=_headers(), json=payload)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def spiritual_stats() -> Optional[dict]:
    """D-C20: 영적 상태 분포 통계."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/spiritual/stats", headers=_headers())
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def get_errors(limit: int = 100, level: str = None, path: str = None, hours: int = 24) -> Optional[list]:
    """런타임 에러 + 슬로우 리퀘스트 로그. GET /admin/errors"""
    params: dict = {"limit": limit, "hours": hours}
    if level: params["level"] = level
    if path:  params["path"] = path
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{API_BASE}/admin/errors", headers=_headers(), params=params)
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None


def get_error_stats() -> Optional[dict]:
    """에러 요약 통계 — 사이드바 뱃지용. GET /admin/error-stats"""
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/admin/error-stats", headers=_headers())
        return _handle(r)
    except (httpx.HTTPError, ValueError):
        return None

def get_categories(category_type: str = None) -> list:
    try:
        params = {"type": category_type} if category_type else None
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/categories", headers=_headers(), params=params)
        data = _handle(r)
        return data.get("categories", []) if data else []
    except (httpx.HTTPError, ValueError):
        return []


def get_services_health() -> Optional[dict]:
    """각 주요 기능의 헬스 체크. GET /admin/services-health"""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/services-health", headers=_headers())
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# ----- Content Links (영성훈련 콘텐츠) -----
@safe_api_call
def list_content_links(category: Optional[str] = None, active_only: bool = False) -> Optional[dict]:
    params = {}
    if category:
        params["category"] = category
    if active_only:
        params["active_only"] = "true"
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/content/links", headers=_headers(), params=params or None)
    return _handle(r)


@safe_api_call
def create_content_link(
    title: str, url: str, source: Optional[str] = None, category: str = "lecture",
    description: str = "", tags: Optional[list] = None,
    target_salvation_stage: Optional[list] = None, lang: str = "ko",
    order_index: int = 0, active: bool = True,
) -> Optional[dict]:
    body = {
        "title": title, "url": url, "category": category, "lang": lang,
        "description": description or None,
        "tags": tags, "target_salvation_stage": target_salvation_stage,
        "order_index": order_index, "active": active,
    }
    if source:
        body["source"] = source
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{API_BASE}/admin/content/links", headers=_headers(), json=body)
    return _handle(r)


@safe_api_call
def update_content_link(link_id: str, **fields) -> Optional[dict]:
    body = {k: v for k, v in fields.items() if v is not None}
    with httpx.Client(timeout=30) as c:
        r = c.patch(f"{API_BASE}/admin/content/links/{link_id}", headers=_headers(), json=body)
    return _handle(r)


@safe_api_call
def delete_content_link(link_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.delete(f"{API_BASE}/admin/content/links/{link_id}", headers=_headers())
    return _handle(r)


# ===== Media (찬양/설교음성 오디오) =====
@safe_api_call
def admin_upload_media(
    file_name: str,
    file_bytes: bytes,
    title: str,
    category: str = "worship",
    artist: str = "",
    description: str = "",
    scripture_refs: str = "",
    order_index: int = 0,
    active: bool = True,
    publish_at: Optional[str] = None,
    notify_mode: str = "immediate",
) -> Optional[dict]:
    """오디오 파일 업로드 (찬양/설교음성).

    publish_at : 발행 예약 시각(ISO 문자열, KST). 미래 시각이면 예약 발행.
    notify_mode : "immediate"(지금 알림) | "batch"(저녁 배치) | "none"(알림 안함).
    """
    files = {"file": (file_name, file_bytes)}
    data = {
        "title": title,
        "category": category,
        "artist": artist or "",
        "description": description or "",
        "scripture_refs": scripture_refs or "",
        "order_index": order_index,
        "active": str(active).lower(),
        "notify_mode": notify_mode,
    }
    if publish_at:
        data["publish_at"] = publish_at
    with httpx.Client(timeout=120) as c:
        r = c.post(
            f"{API_BASE}/admin/media", headers=_headers(), files=files, data=data
        )
    return _handle(r)


@safe_api_call
def admin_list_media(category: Optional[str] = None) -> Optional[dict]:
    params = {"category": category} if category else None
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/media", headers=_headers(), params=params)
    return _handle(r)


@safe_api_call
def admin_update_media(asset_id: str, **fields) -> Optional[dict]:
    body = {k: v for k, v in fields.items() if v is not None}
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/admin/media/{asset_id}", headers=_headers(), json=body
        )
    return _handle(r)


@safe_api_call
def admin_delete_media(asset_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.delete(f"{API_BASE}/admin/media/{asset_id}", headers=_headers())
    return _handle(r)


# ===== Bible (성경 본문 업로드/관리) =====
@safe_api_call
def admin_upload_bible(file_name: str, file_bytes: bytes) -> Optional[dict]:
    """성경 책 텍스트 파일 업로드 (파일명 = 책명)."""
    files = {"file": (file_name, file_bytes)}
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{API_BASE}/admin/bible/upload", headers=_headers(), files=files)
    return _handle(r)


@safe_api_call
def admin_list_bible_books() -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/bible/books", headers=_headers())
    return _handle(r)


@safe_api_call
def admin_delete_bible_book(book: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.delete(
            f"{API_BASE}/admin/bible/books/{book}", headers=_headers()
        )
    return _handle(r)


def get_bible_books() -> Optional[dict]:
    """공개: 색인된 책 목록 + 구조."""
    try:
        with httpx.Client(timeout=20) as c:
            r = c.get(f"{API_BASE}/mobile/bible/books", headers=_headers(admin=False))
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


def get_bible_passage(
    book: str,
    chapter: int,
    verse_start: Optional[int] = None,
    verse_end: Optional[int] = None,
) -> Optional[dict]:
    """공개: 성경 본문 조회 (절 범위 선택)."""
    params = {"book": book, "chapter": chapter}
    if verse_start is not None:
        params["verse_start"] = verse_start
    if verse_end is not None:
        params["verse_end"] = verse_end
    try:
        with httpx.Client(timeout=20) as c:
            r = c.get(
                f"{API_BASE}/mobile/bible/read",
                headers=_headers(admin=False),
                params=params,
            )
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: CodeBuddy
# Timestamp: 2026-07-16
# Task: 인기 Q&A 집계 & 통찰 시스템 — Admin API Client
# Reason: 설계 문서 docs/design-popular-qa-system.md 기반 구현
# =============================================================================


# ── 관리자 대시보드 ──
@safe_api_call
def admin_trending_dashboard(period: str = "7d") -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(
            f"{API_BASE}/admin/trending/dashboard",
            headers=_headers(),
            params={"period": period},
        )
    return _handle(r)


# ── 관리자 편집 ──
def admin_patch_trending(
    snapshot_id: str,
    field: str,
    new_value: str | bool,
    edit_reason: Optional[str] = None,
    save_draft: bool = False,
    force: bool = False,
) -> Optional[dict]:
    body = {
        "field": field,
        "new_value": new_value,
        "save_draft": save_draft,
        "force": force,
    }
    if edit_reason:
        body["edit_reason"] = edit_reason
    try:
        with httpx.Client(timeout=30) as c:
            r = c.patch(
                f"{API_BASE}/admin/trending/{snapshot_id}",
                headers=_headers(),
                json=body,
            )
        return _handle(r)
    except Exception:
        return None


# ── 편집 이력 ──
@safe_api_call
def admin_edit_history(
    snapshot_id: str, field: Optional[str] = None, limit: int = 50, offset: int = 0
) -> Optional[dict]:
    params = {"limit": limit, "offset": offset}
    if field:
        params["field"] = field
    with httpx.Client(timeout=30) as c:
        r = c.get(
            f"{API_BASE}/admin/trending/{snapshot_id}/history",
            headers=_headers(),
            params=params,
        )
    return _handle(r)


# ── 통찰 검수 ──
def admin_review_insight(
    snapshot_id: str, section: str, approved: bool, rejection_reason: Optional[str] = None
) -> Optional[dict]:
    body = {"section": section, "approved": approved}
    if rejection_reason:
        body["rejection_reason"] = rejection_reason
    try:
        with httpx.Client(timeout=30) as c:
            r = c.patch(
                f"{API_BASE}/admin/insight/{snapshot_id}/review",
                headers=_headers(),
                json=body,
            )
        return _handle(r)
    except Exception:
        return None


# ── 통찰 재생성 ──
def admin_regenerate_insight(
    snapshot_id: str,
    sections: Optional[list[str]] = None,
    regenerate_all: bool = False,
    model_override: Optional[str] = None,
    additional_instruction: Optional[str] = None,
) -> Optional[dict]:
    body: dict = {"regenerate_all": regenerate_all}
    if sections:
        body["sections"] = sections
    if model_override:
        body["model_override"] = model_override
    if additional_instruction:
        body["additional_instruction"] = additional_instruction
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(
                f"{API_BASE}/admin/insight/{snapshot_id}/regenerate",
                headers=_headers(),
                json=body,
            )
        return _handle(r)
    except Exception:
        return None


# ── 단편 설교 LLM 생성 (작업 W) ──
def admin_generate_short_sermon(snapshot_id: str) -> Optional[dict]:
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(
                f"{API_BASE}/admin/insight/{snapshot_id}/generate-short-sermon",
                headers=_headers(),
            )
        return _handle(r)
    except Exception:
        return None


# ── 추가 질문하기 (작업: 인기QA 후속 질문) ──
def admin_ask_trending_question(snapshot_id: str, question: str) -> Optional[dict]:
    """인기 QA 스냅샷에 대해 유저 질문 + 위의 내용을 근거로 한 후속 질문을 LLM에 전달.

    question 은 단독적인 질문이 아니라, 해당 QA의 맥락에 이어지는 후속 질문이어야 한다.
    응답은 항상 원본 질문·답변·통찰 컨텍스트에 묶여 생성된다.
    """
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(
                f"{API_BASE}/admin/insight/{snapshot_id}/ask",
                headers=_headers(),
                json={"question": question},
            )
        return _handle(r)
    except Exception:
        return None


# ── 롤백 ──
def admin_revert_edit(
    snapshot_id: str, field: str, target_log_id: str, reason: str
) -> Optional[dict]:
    body = {"field": field, "target_log_id": target_log_id, "reason": reason}
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(
                f"{API_BASE}/admin/trending/{snapshot_id}/revert",
                headers=_headers(),
                json=body,
            )
        return _handle(r)
    except Exception:
        return None


# ── 통찰 대기열 ──
@safe_api_call
def admin_insight_queue() -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/insight/queue", headers=_headers())
    return _handle(r)


# ── 통찰 통계 ──
@safe_api_call
def admin_insight_stats() -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/insight/stats", headers=_headers())
    return _handle(r)


# ── 사용자용 트렌딩 카드 ──
def get_trending_cards(period: str = "7d", category: Optional[str] = None, limit: int = 10) -> Optional[dict]:
    params = {"period": period, "limit": limit}
    if category:
        params["category"] = category
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/trending/cards", params=params)
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# ── 통찰 상세 ──
def get_insight(snapshot_id: str) -> Optional[dict]:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/insight/{snapshot_id}")
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# ── 인기 답변 ──
def get_trending_answers(period: str = "7d", limit: int = 10) -> Optional[dict]:
    params = {"period": period, "limit": limit}
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/trending/answers", params=params)
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None




# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: CodeBuddy
# Timestamp: 2026-07-17
# Task: 봇 관리 Admin API Client
# Reason: Subscriber ORM에 flagged_as_bot/bot_score 필드 노출 + 봇 관리 UI 지원
# =============================================================================


def bot_stats() -> Optional[dict]:
    """봇 관리 통계 — GET /admin/bot/stats"""
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{API_BASE}/admin/bot/stats", headers=_headers())
        return _handle(r)
    except Exception:
        return None


def bot_list(filter_type: Optional[str] = None, limit: int = 200, offset: int = 0) -> Optional[dict]:
    """봇 관리 사용자 목록 — GET /admin/bot/list"""
    params = {"limit": limit, "offset": offset}
    if filter_type:
        params["filter_type"] = filter_type
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/bot/list", headers=_headers(), params=params)
        return _handle(r)
    except Exception:
        return None


def bot_toggle_flag(sub_id: str, flagged: bool, bot_score: Optional[float] = None) -> Optional[dict]:
    """봇 플래그 토글 + bot_score 설정 — PATCH /admin/subscribers/{sub_id}"""
    payload: dict = {"flagged_as_bot": flagged}
    if bot_score is not None:
        payload["bot_score"] = bot_score
    try:
        with httpx.Client(timeout=30) as c:
            r = c.patch(
                f"{API_BASE}/admin/subscribers/{sub_id}",
                headers=_headers(),
                json=payload,
            )
        return _handle(r)
    except Exception:
        return None


# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: CodeBuddy
# Timestamp: 2026-07-25
# Task: 광고 관리 Admin API Client
# Reason: admin 19_📣_광고관리 페이지에서 백엔드 ads API 호출
# =============================================================================

# ── 광고 목록 (관리자용) ──
@safe_api_call
def admin_list_ads() -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/ads/list", headers=_headers())
    return _handle(r)


# ── 광고 생성 ──
@safe_api_call
def admin_create_ad(
    title: str,
    slot: str = "qa_top",
    subtitle: str = "",
    link_url: str = "",
    active: bool = True,
    image_data: Optional[str] = None,
) -> Optional[dict]:
    body = {
        "title": title,
        "slot": slot,
        "subtitle": subtitle,
        "link_url": link_url,
        "active": active,
    }
    if image_data:
        body["image_data"] = image_data
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{API_BASE}/admin/ads/create", headers=_headers(), json=body)
    return _handle(r)


# ── 광고 수정 ──
@safe_api_call
def admin_update_ad(ad_id: str, **fields) -> Optional[dict]:
    body = {k: v for k, v in fields.items() if v is not None}
    with httpx.Client(timeout=60) as c:
        r = c.put(f"{API_BASE}/admin/ads/{ad_id}", headers=_headers(), json=body)
    return _handle(r)


# ── 광고 삭제 ──
@safe_api_call
def admin_delete_ad(ad_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.delete(f"{API_BASE}/admin/ads/{ad_id}", headers=_headers())
    return _handle(r)


# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: CodeBuddy
# Timestamp: 2026-08-03
# Task: CCP 원가 단가(rate card) 관리 Admin API Client
# Reason: ① 실제 LLM 단가 + 환율 기준일을 터미널 아닌 Admin Hub UI 에서 직접 입력
# =============================================================================


@safe_api_call
def list_ccp_rates() -> Optional[list]:
    """현재 유효한(종료 시각이 NULL 인) 단가 목록 조회. GET /admin/ccp/rates"""
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/admin/ccp/rates", headers=_headers())
    return _handle(r)


@safe_api_call
def create_ccp_rate(
    provider: str,
    model: str,
    input_price_per_1k: float,
    output_price_per_1k: float,
    source_note: str,
    currency: str = "KRW",
    effective_from: Optional[str] = None,
) -> Optional[dict]:
    """신규 단가 추가 (SCD Type 2 — 기존 유효 구간 종료 + 신규 구간 개시).

    effective_from: ISO 8601 문자열(비우면 서버 현재 시각 UTC). None → 미제공.
    source_note: 공급자 가격표 URL·환율 기준일 등 출처 소명 근거 (필수).
    """
    body: dict = {
        "provider": provider,
        "model": model,
        "input_price_per_1k": input_price_per_1k,
        "output_price_per_1k": output_price_per_1k,
        "source_note": source_note,
        "currency": currency,
    }
    if effective_from:
        body["effective_from"] = effective_from
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{API_BASE}/admin/ccp/rates", headers=_headers(), json=body)
    return _handle(r)
