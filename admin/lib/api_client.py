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
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "local-admin-key")


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


# ----- Documents -----
def list_documents(state: Optional[str] = None) -> Optional[list]:
    params = {"state": state} if state else None
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/documents", headers=_headers(), params=params)
        return _handle(r)
    except httpx.ConnectError:
        st.error("Cannot connect to API.")
        return None


def get_document(doc_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API_BASE}/documents/{doc_id}", headers=_headers())
    return _handle(r)


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
    except httpx.ConnectError:
        st.error("Cannot connect to API.")
        return None


def list_inbox() -> Optional[dict]:
    """inbox 폴더 파일 목록. GET /documents/inbox"""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/documents/inbox", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
        return None


def ingest_inbox_async(filenames: list[str], doc_type: str = "sermon") -> Optional[dict]:
    """inbox 선택 파일 일괄 처리. POST /documents/ingest-inbox"""
    import json
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(
                f"{API_BASE}/documents/ingest-inbox",
                headers=_headers(),
                data={"filenames": json.dumps(filenames), "doc_type": doc_type},
            )
        return _handle(r)
    except httpx.ConnectError:
        return None


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
    except httpx.ConnectError:
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
    except httpx.ConnectError:
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
    except httpx.ConnectError:
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
    except httpx.ConnectError:
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


def patch_meta(doc_id: str, version_id: str, payload: dict) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}",
            headers=_headers(), json=payload,
        )
    return _handle(r)


def patch_doc_meta(doc_id: str, payload: dict) -> Optional[dict]:
    """document 레벨 필드 수정 — speaker / series / doc_type."""
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}",
            headers=_headers(), json=payload,
        )
    return _handle(r)


def patch_body(doc_id: str, version_id: str, body: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/body",
            headers=_headers(), json={"body": body},
        )
    return _handle(r)


def validate_version(doc_id: str, version_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/validate",
            headers=_headers(),
        )
    return _handle(r)


def publish_version(doc_id: str, version_id: str) -> Optional[dict]:
    with httpx.Client(timeout=180) as c:
        r = c.post(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}/publish",
            headers=_headers(),
        )
    return _handle(r)


def archive_document(doc_id: str) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.delete(f"{API_BASE}/documents/{doc_id}", headers=_headers())
    return _handle(r)


def new_version(doc_id: str, file_name: str, file_bytes: bytes, title: Optional[str] = None) -> Optional[dict]:
    files = {"file": (file_name, file_bytes)}
    data = {"title": title} if title else {}
    with httpx.Client(timeout=120) as c:
        r = c.post(
            f"{API_BASE}/documents/{doc_id}/new-version",
            headers=_headers(), files=files, data=data,
        )
    return _handle(r)


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
    except httpx.ConnectError:
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
    except httpx.ConnectError:
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
    except httpx.ConnectError:
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
    except httpx.ConnectError:
        return None


def chat(query: str, history: list, llm_provider: Optional[str] = None, embedder: Optional[str] = None, debug: bool = False) -> Optional[dict]:
    with httpx.Client(timeout=180) as c:
        r = c.post(
            f"{API_BASE}/chat",
            json={
                "query": query, "history": history,
                "llm_provider": llm_provider or None,
                "embedder": embedder or None,
                "debug": debug,
            },
        )
    return _handle(r)


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
    except httpx.ConnectError:
        return None


def memory_stats(subscriber_id=None):
    params = {"subscriber_id": subscriber_id} if subscriber_id else None
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/memory/stats", headers=_headers(), params=params)
        return _handle(r)
    except httpx.ConnectError:
        return None


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
    except httpx.ConnectError:
        return None


def save_prompt(content, note=None):
    with httpx.Client(timeout=10) as c:
        r = c.put(f"{API_BASE}/prompts/current", headers=_headers(),
                  json={"content": content, "note": note})
    return _handle(r)


def reset_prompt():
    with httpx.Client(timeout=10) as c:
        r = c.post(f"{API_BASE}/prompts/reset", headers=_headers())
    return _handle(r)


def prompt_history():
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{API_BASE}/prompts/history", headers=_headers())
    return _handle(r)



def set_feedback(interaction_id, value):
    with httpx.Client(timeout=10) as c:
        r = c.patch(f"{API_BASE}/memory/{interaction_id}/feedback",
                    headers=_headers(), json={"value": value})
    return _handle(r)



def bulk_action(doc_ids, action):
    with httpx.Client(timeout=300) as c:
        r = c.post(f"{API_BASE}/documents/bulk-action", headers=_headers(),
                    json={"doc_ids": doc_ids, "action": action})
    return _handle(r)


def get_taxonomy():
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/taxonomy", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
        return None



def get_usage():
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/usage", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
        return None



def run_regression():
    with httpx.Client(timeout=300) as c:
        r = c.post(f"{API_BASE}/eval/regression", headers=_headers())
    return _handle(r)


# ===== Subscriber (사람) =====
def list_subscribers() -> Optional[list]:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/list", headers=_headers())
        data = _handle(r)
        return data.get("subscribers", []) if data else None
    except httpx.ConnectError:
        return None

def update_subscriber(sub_id: str, payload: dict) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(f"{API_BASE}/admin/subscribers/{sub_id}", headers=_headers(), json=payload)
    return _handle(r)


def toggle_assume_saved(sub_id: str, value: bool, reason: str = "", also_set_status: Optional[str] = None) -> Optional[dict]:
    """D-C22: assume_saved 토글."""
    payload: dict = {"value": value, "reason": reason}
    if also_set_status:
        payload["also_set_status"] = also_set_status
    try:
        with httpx.Client(timeout=30) as c:
            r = c.patch(f"{API_BASE}/admin/subscribers/{sub_id}/assume-saved", headers=_headers(), json=payload)
        return _handle(r)
    except httpx.ConnectError:
        return None


def spiritual_stats() -> Optional[dict]:
    """D-C20: 영적 상태 분포 통계."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/spiritual/stats", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
        return None


def spiritual_journey(days: int = 30) -> Optional[dict]:
    """D-C20: 구원 여정 전환 흐름."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/spiritual/journey", headers=_headers(), params={"days": days})
        return _handle(r)
    except httpx.ConnectError:
        return None


def spiritual_stagnant(stagnant_days: int = 30) -> Optional[dict]:
    """D-C20: 정체 사용자 목록."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/spiritual/stagnant", headers=_headers(), params={"stagnant_days": stagnant_days})
        return _handle(r)
    except httpx.ConnectError:
        return None


def darakbang_matrix() -> Optional[dict]:
    """D-C20: 다락방 역할 × 구원 상태 매트릭스."""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/spiritual/darakbang-matrix", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
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
    except httpx.ConnectError:
        return None


def get_error_stats() -> Optional[dict]:
    """에러 요약 통계 — 사이드바 뱃지용. GET /admin/error-stats"""
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/admin/error-stats", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
        return None


def upgrade_subscription(sub_id: str, tier: str, extend_trial_days: int = 0) -> Optional[dict]:
    """구독 티어 변경. tier: member | supporter | guest"""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.patch(
                f"{API_BASE}/admin/subscribers/{sub_id}/subscription",
                headers=_headers(),
                json={"tier": tier, "extend_trial_days": extend_trial_days},
            )
        return _handle(r)
    except httpx.ConnectError:
        return None


def get_subscription_stats() -> Optional[dict]:
    """구독 현황 통계."""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/subscription-stats", headers=_headers())
        return _handle(r)
    except httpx.ConnectError:
        return None


def get_categories(category_type: str = None) -> list:
    try:
        params = {"type": category_type} if category_type else None
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/categories", headers=_headers(), params=params)
        data = _handle(r)
        return data.get("categories", []) if data else []
    except httpx.ConnectError:
        return []
