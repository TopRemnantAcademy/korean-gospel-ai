"""E-D: 업로드 정제 검토 (5단계 파이프라인 실행 + diff 뷰).

운영자가 문서를 선택 → 정제 실행 → 단계별 변경 내용 비교 확인 → 적용.
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

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "")

st.set_page_config(page_title="정제 검토", page_icon="📝", layout="wide")
st.title("📝 업로드 정제 검토")
st.caption("E-D: 5단계 파이프라인 — Stage 1 정규화 → 2 오타 → 3 맥락 → 4 신학검증 → 5 용어추출")

HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


# ── 문서 목록 로드 ──────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def _load_docs():
    try:
        r = httpx.get(f"{API_BASE}/documents", headers=HEADERS, timeout=10)
        return r.json() if r.status_code < 400 else []
    except Exception:
        return []


docs = _load_docs()
draft_docs = [d for d in docs if d.get("latest_state") in ("draft", "validated")]

if not draft_docs:
    st.info("정제할 draft/validated 문서가 없습니다. 먼저 문서를 업로드하세요.")
    st.stop()

# ── 문서 선택 ───────────────────────────────────────────────────────────────
doc_options = {f"{d['title']} (v{d['latest_version']}, {d['latest_state']})": d for d in draft_docs}
selected_label = st.selectbox("📄 문서 선택", list(doc_options.keys()))
selected_doc = doc_options[selected_label]
doc_id = selected_doc["doc_id"]


# ── 버전 상세 로드 ─────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def _load_doc_detail(doc_id: str):
    try:
        r = httpx.get(f"{API_BASE}/documents/{doc_id}", headers=HEADERS, timeout=10)
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


detail = _load_doc_detail(doc_id)
if not detail:
    st.error("문서 상세 정보를 불러오지 못했습니다.")
    st.stop()

versions = detail.get("versions", [])
ver_options = {
    f"v{v['version_number']} — {v['state']} ({v['version_id'][:8]}...)": v
    for v in versions
    if v["state"] in ("draft", "validated")
}
if not ver_options:
    st.warning("정제 가능한 버전(draft/validated)이 없습니다.")
    st.stop()

selected_ver_label = st.selectbox("🗂 버전 선택", list(ver_options.keys()))
selected_ver = ver_options[selected_ver_label]
ver_id = selected_ver["version_id"]

# 현재 본문 미리보기
current_body = selected_ver.get("body_patch") or selected_ver.get("extracted_text_preview", "")

st.divider()

# ── 파이프라인 설정 ─────────────────────────────────────────────────────────
col_cfg, col_run = st.columns([3, 1])
with col_cfg:
    stages_sel = st.multiselect(
        "실행할 Stage 선택",
        options=[1, 2, 3, 4, 5],
        default=[1, 2, 3, 4, 5],
        format_func=lambda x: {
            1: "1 — 기계적 정규화",
            2: "2 — 오타 수정 (DeepSeek)",
            3: "3 — 맥락 분석 (Gemini)",
            4: "4 — 신학 검증",
            5: "5 — 용어 추출",
        }.get(x, str(x)),
    )
    dry_run = st.checkbox("🔍 Dry-run (DB 저장 안 함 — 미리보기 전용)", value=True)

with col_run:
    st.write("")
    st.write("")
    run_btn = st.button("▶ 정제 실행", type="primary", use_container_width=True, disabled=not stages_sel)

# ── 결과 표시 ───────────────────────────────────────────────────────────────
if run_btn and stages_sel:
    with st.spinner("정제 파이프라인 실행 중... (LLM 단계는 시간이 걸릴 수 있습니다)"):
        try:
            r = httpx.post(
                f"{API_BASE}/documents/{doc_id}/versions/{ver_id}/cleanup",
                json={"stages": sorted(stages_sel), "dry_run": dry_run},
                headers=HEADERS,
                timeout=300,
            )
        except Exception as e:
            st.error(f"요청 실패: {e}")
            st.stop()

    if r.status_code >= 400:
        st.error(f"API 오류 {r.status_code}: {r.text[:300]}")
        st.stop()

    data = r.json()
    st.session_state["last_cleanup"] = data
    st.session_state["last_cleanup_body"] = current_body
    st.session_state["last_cleanup_stages"] = sorted(stages_sel)

# 저장된 결과 표시
if "last_cleanup" in st.session_state:
    data = st.session_state["last_cleanup"]
    orig_body = st.session_state.get("last_cleanup_body", "")

    # 요약 메트릭
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("원본 길이", f"{data['original_len']:,}자")
    c2.metric("정제 후 길이", f"{data['final_len']:,}자", f"{data['final_len'] - data['original_len']:+,}자")
    c3.metric("경고", len(data["warnings"]))
    c4.metric("신학 위반", len(data["theology_violations"]))

    if data.get("dry_run"):
        st.info("ℹ Dry-run 모드 — 결과가 DB에 저장되지 않았습니다.")
    else:
        st.success("✅ 정제 완료 — body_patch에 저장되었습니다.")

    # 신학 경고
    if data["theology_violations"]:
        with st.expander(f"⚠ 신학 보존 경고 ({len(data['theology_violations'])}건)", expanded=True):
            for v in data["theology_violations"]:
                st.warning(v)

    if data["warnings"]:
        with st.expander(f"📋 일반 경고 ({len(data['warnings'])}건)"):
            for w in data["warnings"]:
                st.caption(w)

    # 3분할 diff 뷰
    st.subheader("📊 단계별 변경 비교")
    if data["diffs"]:
        for diff in data["diffs"]:
            stage_names = {1: "정규화", 2: "오타수정", 3: "맥락분석", 4: "신학검증", 5: "용어추출"}
            with st.expander(f"Stage {diff['stage']}: {stage_names.get(diff['stage'], '')} — {diff['reason']}"):
                col_a, col_sep, col_b = st.columns([5, 1, 5])
                with col_a:
                    st.caption("**이전**")
                    st.code(diff["original"], language=None)
                with col_sep:
                    st.markdown("<div style='text-align:center; font-size:1.5rem; margin-top:2rem'>→</div>",
                                unsafe_allow_html=True)
                with col_b:
                    st.caption("**이후**")
                    st.code(diff["modified"], language=None)
    else:
        st.info("변경 사항 없음 — 이미 정제된 텍스트입니다.")

    # 최종 결과 미리보기
    st.subheader("📄 최종 결과 미리보기 (처음 800자)")
    col_orig, col_final = st.columns(2)
    with col_orig:
        st.caption("원본")
        st.text_area("", value=orig_body[:800], height=300, disabled=True, key="preview_orig")
    with col_final:
        st.caption("정제 후")
        st.text_area("", value=data.get("final_text_preview", ""), height=300,
                     disabled=True, key="preview_final")

    # 용어 추출 결과
    if data.get("terms_found"):
        with st.expander(f"🔖 추출된 용어 ({len(data['terms_found'])}개)"):
            scriptures = [t for t in data["terms_found"] if t.startswith("[성경구절]")]
            theology = [t for t in data["terms_found"] if t.startswith("[신학용어]")]
            repeat = [t for t in data["terms_found"] if t.startswith("[반복용어]")]
            if scriptures:
                st.markdown("**성경 구절**")
                st.markdown("  \n".join(scriptures))
            if theology:
                st.markdown("**신학 용어**")
                st.markdown("  \n".join(theology))
            if repeat:
                st.markdown("**반복 등장 용어**")
                st.markdown("  \n".join(repeat))

    # dry_run이면 실제 저장 버튼
    if data.get("dry_run") and st.button("💾 이 결과로 저장하기", type="primary"):
        save_stages = st.session_state.get("last_cleanup_stages", [1, 2, 3, 4, 5])
        with st.spinner("저장 중..."):
            try:
                r2 = httpx.post(
                    f"{API_BASE}/documents/{doc_id}/versions/{ver_id}/cleanup",
                    json={"stages": save_stages, "dry_run": False},
                    headers=HEADERS,
                    timeout=300,
                )
            except Exception as e:
                st.error(f"저장 실패: {e}")
                st.stop()
        if r2.status_code < 400:
            st.success("✅ 저장 완료!")
            st.cache_data.clear()
        else:
            st.error(f"저장 실패 {r2.status_code}: {r2.text[:200]}")
