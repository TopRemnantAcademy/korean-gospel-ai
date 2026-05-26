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
    with httpx.Client(timeout=120) as c:
        r = c.post(
            f"{API_BASE}/documents/upload",
            headers=_headers(), files=files, data=form_fields,
        )
    return _handle(r)


def patch_meta(doc_id: str, version_id: str, payload: dict) -> Optional[dict]:
    with httpx.Client(timeout=30) as c:
        r = c.patch(
            f"{API_BASE}/documents/{doc_id}/versions/{version_id}",
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
    # Approximation: 모든 문서 처음 N개 묶어보지 말고, 백엔드에 별도 엔드포인트 필요.
    # 일단 빈 list로 시작 (다음 라운드에 /admin/recent-activity 추가)
    return []


# ----- Search/Chat -----
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


def get_categories(type_: str = None) -> list:
    try:
        params = {"type": type_} if type_ else None
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/categories", headers=_headers(), params=params)
        data = _handle(r)
        return data.get("categories", []) if data else []
    except httpx.ConnectError:
        return []


# ===== Agentic Admin =====
def agent_chat(query: str, history: list) -> Optional[dict]:
    with httpx.Client(timeout=180) as c:
        r = c.post(
            f"{API_BASE}/admin/agent/chat",
            headers=_headers(),
            json={"query": query, "history": history}
        )
    return _handle(r)

def get_categories(ctype: str = None) -> Optional[list]:
    # 임시 우회: agent 엔드포인트를 통해 도구를 직접 호출하는 꼼수 혹은 
    # 별도 라우터 없이 어드민 라우터에 추가된 엔드포인트 가정
    # 여기서는 /admin/subscribers/categories 로 가정하고 백엔드에 추가
    try:
        params = {"type": ctype} if ctype else None
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/categories", headers=_headers(), params=params)
        return _handle(r).get("categories", [])
    except httpx.ConnectError:
        return []
