"""E-G1: 통합 자료 처리 워크플로우.

Upload → Cleanup → Glossary → Publish 를 한 화면에서.
5단계 Stepper — 어느 단계든 이어서 시작 가능.
"""
from __future__ import annotations

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.auth import gate
gate(os.getenv("APP_PASSWORD", ""))

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.ui_components import stepper, empty_state, draft_status_badge

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "local-admin-key")
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

st.set_page_config(page_title="자료 흐름", page_icon="📥", layout="wide")
st.title("📥 자료 처리 흐름 (통합)")
st.caption("Upload → 정제(Cleanup) → 용어검토(Glossary) → Publish — 한 화면에서 처리")


def _api(method: str, path: str, **kwargs):
    try:
        fn = getattr(httpx, method)
        r = fn(f"{API_BASE}{path}", headers=HEADERS, timeout=30, **kwargs)
        return r if r.status_code < 400 else None
    except Exception:
        return None


# ── 문서 선택 / 새 업로드 ────────────────────────────────────────────────────
st.sidebar.markdown("### 📄 자료 선택")

@st.cache_data(ttl=20)
def _load_docs():
    r = _api("get", "/documents")
    return r.json() if r else []

docs = _load_docs()
non_published = [d for d in docs if d.get("latest_state") not in ("published",)]
published = [d for d in docs if d.get("latest_state") == "published"]

view_mode = st.sidebar.radio("보기", ["진행 중인 자료", "발행 완료"], horizontal=True)
target_list = non_published if view_mode == "진행 중인 자료" else published

if not target_list:
    empty_state("📭", "자료가 없습니다. 먼저 업로드하세요.")
    st.stop()

options = {f"{d['title']} ({d['latest_state']})": d for d in target_list}
sel_label = st.sidebar.selectbox("자료", list(options.keys()))
sel_doc = options[sel_label]
doc_id = sel_doc["doc_id"]

if st.sidebar.button("🔄 목록 새로고침"):
    st.cache_data.clear()
    st.rerun()

# ── 버전 로드 ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def _load_detail(did: str):
    r = _api("get", f"/documents/{did}")
    return r.json() if r else None

detail = _load_detail(doc_id)
if not detail:
    st.error("문서 로드 실패")
    st.stop()

versions = detail.get("versions", [])
latest_ver = versions[0] if versions else None
if not latest_ver:
    st.error("버전 없음")
    st.stop()

ver_id = latest_ver["version_id"]
ver_state = latest_ver["state"]

# ── Stepper ──────────────────────────────────────────────────────────────────
STAGES = ["업로드", "정제", "용어검토", "검증", "발행"]
STAGE_MAP = {
    "draft": 1,
    "validated": 3,
    "published": 4,
    "superseded": 4,
    "archived": 4,
}
current_stage = STAGE_MAP.get(ver_state, 0)

st.markdown("---")
stepper(STAGES, current_stage)
st.markdown("---")

# ── 단계별 작업 패널 ──────────────────────────────────────────────────────────
tab_info, tab_cleanup, tab_glossary, tab_validate, tab_publish = st.tabs(
    ["📄 정보", "✨ 정제", "📚 용어", "✅ 검증", "🚀 발행"]
)


# Tab 1: 정보
with tab_info:
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(f"**제목**: {latest_ver['title']}")
        st.markdown(f"**상태**: `{ver_state}`")
        st.markdown(f"**버전**: v{latest_ver['version_number']}")
        if latest_ver.get("summary"):
            st.markdown(f"**요약**: {latest_ver['summary']}")
    with col_r:
        tags = latest_ver.get("topic_tags") or []
        if tags:
            st.markdown(f"**태그**: {', '.join(tags)}")
        refs = latest_ver.get("scripture_refs") or []
        if refs:
            st.markdown(f"**성경구절**: {', '.join(refs)}")
        # 임시저장 상태
        draft_r = _api("get", f"/drafts/{ver_id}")
        if draft_r:
            ddata = draft_r.json()
            draft_status_badge(ddata.get("saved_at"), ddata.get("device_id", ""))
        else:
            draft_status_badge(None)

    st.markdown("#### 본문 미리보기")
    body_preview = latest_ver.get("body_patch") or latest_ver.get("extracted_text_preview", "")
    st.text_area("", value=body_preview[:800], height=200, disabled=True)


# Tab 2: 정제
with tab_cleanup:
    if ver_state == "published":
        st.info("이미 발행된 자료입니다. 재정제하려면 새 버전을 만드세요.")
    else:
        stages_sel = st.multiselect(
            "실행 Stage",
            [1, 2, 3, 4, 5],
            default=[1, 2, 3, 4, 5],
            format_func=lambda x: {1: "정규화", 2: "오타", 3: "맥락", 4: "신학검증", 5: "용어추출"}.get(x, str(x)),
        )
        dry_run = st.checkbox("Dry-run (미리보기)", value=True)

        if st.button("▶ 정제 실행", type="primary", disabled=not stages_sel):
            with st.spinner("정제 중..."):
                r = _api("post", f"/documents/{doc_id}/versions/{ver_id}/cleanup",
                         json={"stages": sorted(stages_sel), "dry_run": dry_run})
            if r:
                data = r.json()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("원본", f"{data['original_len']:,}자")
                c2.metric("정제 후", f"{data['final_len']:,}자")
                c3.metric("경고", len(data["warnings"]))
                c4.metric("신학위반", len(data["theology_violations"]))
                if data["theology_violations"]:
                    for v in data["theology_violations"]:
                        st.warning(v)
                if not dry_run:
                    st.success("✅ body_patch 에 저장 완료")
                    st.cache_data.clear()
                else:
                    st.info("Dry-run — 저장 안됨")
            else:
                st.error("정제 실패")


# Tab 3: 용어 검토
with tab_glossary:
    st.caption("이 자료 publish 시 자동으로 용어가 추출됩니다. 아래는 현재 대기 중인 전체 용어입니다.")
    pend_r = _api("get", "/glossary/pending?limit=20")
    pending = pend_r.json() if pend_r else []
    if not pending:
        st.success("검토 대기 용어 없음 ✅")
    else:
        st.caption(f"대기 {len(pending)}개 — [용어집 페이지](14_📚_용어집)에서 전체 관리")
        for item in pending[:10]:
            cols = st.columns([3, 1, 1, 1])
            cols[0].markdown(f"**{item['term']}** ({item['frequency_count']}회)")
            if cols[1].button("✅", key=f"g_approve_{item['id']}"):
                _api("post", f"/glossary/{item['id']}/approve", json={"is_theology": False})
                st.cache_data.clear()
                st.rerun()
            if cols[2].button("🕊", key=f"g_theol_{item['id']}"):
                _api("post", f"/glossary/{item['id']}/approve", json={"is_theology": True})
                st.cache_data.clear()
                st.rerun()
            if cols[3].button("🗑", key=f"g_reject_{item['id']}"):
                _api("post", f"/glossary/{item['id']}/reject")
                st.cache_data.clear()
                st.rerun()


# Tab 4: 검증
with tab_validate:
    if st.button("🔍 검증 실행", type="primary"):
        with st.spinner("검증 중..."):
            r = _api("post", f"/documents/{doc_id}/versions/{ver_id}/validate")
        if r:
            data = r.json()
            if data.get("passed"):
                st.success(f"✅ 검증 통과 — 상태: `{data['state']}`")
            else:
                st.error("❌ 검증 실패")
            report = data.get("report", {})
            if report:
                st.json(report)
            st.cache_data.clear()
        else:
            st.error("검증 요청 실패")


# Tab 5: 발행
with tab_publish:
    if ver_state == "published":
        st.success("✅ 이미 발행된 자료입니다.")
    else:
        conditions = {
            "draft 또는 validated 상태": ver_state in ("draft", "validated"),
            "제목 존재": bool(latest_ver.get("title")),
            "본문 존재": bool(latest_ver.get("body_patch") or latest_ver.get("extracted_text_preview")),
        }
        all_ok = all(conditions.values())
        for cond, ok in conditions.items():
            st.markdown(f"{'✅' if ok else '❌'} {cond}")

        if st.button("🚀 발행하기", type="primary", disabled=not all_ok):
            with st.spinner("발행 중..."):
                r = _api("post", f"/documents/{doc_id}/versions/{ver_id}/publish")
            if r:
                data = r.json()
                st.success(f"✅ 발행 완료 — {data.get('chunks', 0)}개 청크 인덱싱")
                # 임시저장 정리
                _api("delete", f"/drafts/{ver_id}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("발행 실패")
