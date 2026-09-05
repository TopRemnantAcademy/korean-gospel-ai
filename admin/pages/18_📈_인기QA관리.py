"""📈 인기QA관리 — 트렌딩 질문/답변 집계 + LLM 통찰 검수·편집."""

from __future__ import annotations

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import json
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    admin_trending_dashboard,
    admin_patch_trending,
    admin_edit_history,
    admin_review_insight,
    admin_regenerate_insight,
    admin_revert_edit,
    admin_generate_short_sermon,
    admin_insight_queue,
    admin_insight_stats,
)
from admin.lib.auth import gate

# set_page_config MUST be the first Streamlit command on the page.
# gate() issues st.* commands, so it runs AFTER this call.
st.set_page_config(page_title="인기 QA 관리", page_icon="📈", layout="wide")
gate(os.getenv("APP_PASSWORD", ""))

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    .stDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    [data-testid="stToolbar"] { display: none !important; }
    footer { visibility: hidden !important; }
    header[data-testid="stHeader"] { height: 0 !important; }

    .trend-card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        background: #ffffff;
        transition: box-shadow 0.2s;
    }
    .trend-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    .trend-card.featured { border-left: 4px solid #f59e0b; }
    .trend-card.hidden { opacity: 0.5; }
    .trend-card h4 { margin: 0 0 8px 0; font-size: 1.05rem; }
    .trend-card .meta {
        font-size: 0.8rem; color: #888;
        display: flex; gap: 16px; flex-wrap: wrap;
    }
    .trend-card .meta span { white-space: nowrap; }

    .score-badge {
        display: inline-block;
        background: #eef2ff; color: #4338ca;
        border-radius: 24px;
        padding: 2px 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .score-badge.hot { background: #fef2f2; color: #dc2626; }

    .section-review {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
    }
    .section-review.approved { border-left: 3px solid #22c55e; }
    .section-review.rejected { border-left: 3px solid #ef4444; }
    .section-review.pending { border-left: 3px solid #f59e0b; }

    .edit-history-row {
        font-size: 0.82rem;
        padding: 6px 0;
        border-bottom: 1px solid #f3f4f6;
    }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

REVIEW_STATUS_LABEL = {
    "pending": "⏳ 검토 중",
    "approved": "✅ 승인",
    "rejected": "❌ 반려",
}

FIELD_LABELS = {
    "question": "질문 텍스트",
    "answer": "답변 텍스트",
    "root_cause": "근본 원인 분석",
    "ai_diagnosis": "진단",
    "best_answer": "베스트 답변",
    "best_answer_why": "베스트 답변 이유",
    "reflection": "묵상 포인트",
    "is_featured": "추천 여부",
    "is_hidden": "숨김 여부",
}

SECTION_LABELS = {
    "root_cause": "근본 원인 분석",
    "ai_diagnosis": "진단",
    "best_answer_why": "베스트 답변 이유",
    "reflection": "묵상 포인트",
}

EDITABLE_TEXT_FIELDS = [
    "canonical_text", "root_cause", "ai_diagnosis",
    "best_answer_text", "best_answer_why", "reflection",
]

# ── 세션 상태 초기화 ──
if "trend_selected" not in st.session_state:
    st.session_state.trend_selected = None
if "trend_detail_tab" not in st.session_state:
    st.session_state.trend_detail_tab = "edit"


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

st.title("📈 인기 QA 관리")
st.caption("자주 묻는 질문 집계 · LLM 통찰 생성 · 관리자 검수/편집")

period = st.selectbox("기간", ["7d", "30d", "90d", "all"],
                       index=0, format_func=lambda x: {"7d": "최근 7일", "30d": "최근 30일", "90d": "최근 90일", "all": "전체"}[x])

tab_main, tab_queue, tab_stats, tab_answers = st.tabs([
    "🏠 대시보드", "📋 검수 대기열", "📊 통계", "💬 인기 답변"
])


# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 대시보드 — 인기 질문 TOP N + 상세 편집
# ══════════════════════════════════════════════════════════════════════════════
with tab_main:
    dash = admin_trending_dashboard(period=period)

    if not dash:
        st.warning("대시보드 데이터를 불러올 수 없습니다.")
    else:
        overview = dash.get("overview", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("전체 스냅샷", overview.get("total_snapshots", 0))
        c2.metric("인기 질문", overview.get("total_questions", 0))
        c3.metric("인기 답변", overview.get("total_answers", 0))
        c4.metric("통찰 생성률", f"{overview.get('insight_coverage_pct', 0)}%")

        st.divider()

        # ── 질문 목록 (좌) + 상세 편집 (우) ──
        left, right = st.columns([1, 2])

        with left:
            st.subheader("🔥 인기 질문 TOP")
            questions = dash.get("top_questions", [])
            if not questions:
                st.info("아직 집계된 인기 질문이 없습니다.")
            else:
                for q in questions:
                    sid = q.get("snapshot_id", "")
                    text = q.get("question", q.get("canonical_text", "?"))[:80]
                    score = q.get("trend_score", 0)
                    count = q.get("total_count", 0)
                    featured = q.get("is_featured", False)
                    hidden = q.get("is_hidden", False)

                    cls = "trend-card"
                    if featured:
                        cls += " featured"
                    if hidden:
                        cls += " hidden"

                    badge_cls = "score-badge"
                    if score >= 100:
                        badge_cls += " hot"

                    st.markdown(f"""
                    <div class="{cls}" style="cursor:pointer;">
                        <div style="display:flex;justify-content:space-between;align-items:start;">
                            <h4>{'⭐ ' if featured else ''}{text}</h4>
                            <span class="{badge_cls}">{score:.1f}</span>
                        </div>
                        <div class="meta">
                            <span>📊 {count}회</span>
                            <span>👍 {q.get('positive_feedback', 0)}</span>
                            <span>📈 {q.get('fb_ratio', 0):.1%}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("📝 편집", key=f"sel_{sid}"):
                        st.session_state.trend_selected = sid
                        st.rerun()

        with right:
            selected_id = st.session_state.trend_selected

            if not selected_id:
                st.info("👈 왼쪽 목록에서 편집할 질문을 선택하세요.")
            else:
                # 선택된 항목 찾기
                selected_q = next(
                    (q for q in questions if q.get("snapshot_id") == selected_id), None
                )
                if not selected_q:
                    st.warning("선택한 항목을 찾을 수 없습니다.")
                    st.session_state.trend_selected = None
                else:
                    st.subheader(f"편집: {selected_q.get('question', selected_q.get('canonical_text', ''))[:60]}...")

                    ed_tabs = st.tabs(["✏️ 편집", "📜 이력", "🧠 통찰 검수", "🔄 재생성", "📖 단편 설교", "💬 추가 질문하기", "📋 추천 질문"])

                    # ── 편집 탭 ──
                    with ed_tabs[0]:
                        with st.form("edit_form"):
                            col_f, col_v = st.columns([1, 3])
                            with col_f:
                                field = st.selectbox(
                                    "필드", list(FIELD_LABELS.keys()),
                                    format_func=lambda f: FIELD_LABELS[f]
                                )

                            with col_v:
                                if field in ("is_featured", "is_hidden"):
                                    new_val = st.toggle(
                                        "값",
                                        value=selected_q.get(field, False),
                                        help=f"현재: {selected_q.get(field, False)}"
                                    )
                                else:
                                    current_val = selected_q.get(field, "") or ""
                                    if isinstance(current_val, dict):
                                        current_val = ""
                                    new_val = st.text_area(
                                        "새 값",
                                        value=str(current_val) if current_val else "",
                                        height=150,
                                    )

                            reason = st.text_input("편집 사유 (선택)", max_chars=200)
                            submitted = st.form_submit_button("💾 저장", type="primary")

                            if submitted:
                                result = admin_patch_trending(
                                    snapshot_id=selected_id,
                                    field=field,
                                    new_value=new_val,
                                    edit_reason=reason or None,
                                )
                                if result and result.get("ok"):
                                    st.success("✅ 저장 완료")
                                    st.rerun()
                                else:
                                    st.error("저장 실패")

                    # ── 이력 탭 ──
                    with ed_tabs[1]:
                        hist = admin_edit_history(selected_id)
                        if not hist:
                            st.info("편집 이력이 없습니다.")
                        else:
                            items = hist.get("history", [])
                            st.caption(f"총 {hist.get('total_edits', len(items))}건의 편집")
                            for h in items[:30]:
                                with st.container():
                                    dt = h.get("edited_at", "")[:19].replace("T", " ")
                                    fld = FIELD_LABELS.get(h.get("field", ""), h.get("field", ""))
                                    who = h.get("edited_by", "?")
                                    diff = h.get("diff_summary", "")
                                    revert_key = h.get("reverted", False)

                                    st.markdown(f"""
                                    <div class="edit-history-row">
                                        <strong>{fld}</strong> — {dt} by {who}
                                        {' 🔄되돌림' if revert_key else ''}<br/>
                                        <span style="color:#666;">{diff[:200]}</span>
                                    </div>
                                    """, unsafe_allow_html=True)

                                    if not revert_key:
                                        c_btn, _ = st.columns([1, 3])
                                        with c_btn:
                                            with st.popover("🔄 롤백"):
                                                rollback_reason = st.text_area(
                                                    "롤백 사유 (10자 이상)",
                                                    key=f"rb_{h.get('log_id', '')}",
                                                    max_chars=500,
                                                )
                                                if st.button("확인", key=f"rb_ok_{h.get('log_id', '')}"):
                                                    if len(rollback_reason) >= 10:
                                                        rb_res = admin_revert_edit(
                                                            selected_id,
                                                            h["field"],
                                                            h["log_id"],
                                                            rollback_reason,
                                                        )
                                                        if rb_res and rb_res.get("ok"):
                                                            st.success("롤백 완료")
                                                            st.rerun()
                                                    else:
                                                        st.error("10자 이상 입력 필요")

                    # ── 통찰 검수 탭 ──
                    with ed_tabs[2]:
                        insight_data = {
                            "root_cause": selected_q.get("root_cause_analysis"),
                            "ai_diagnosis": selected_q.get("ai_diagnosis"),
                            "best_answer_why": selected_q.get("best_answer_why"),
                            "reflection": selected_q.get("reflection_prompt"),
                        }

                        review_status = {
                            "root_cause": selected_q.get("review_status_root_cause", "pending"),
                            "ai_diagnosis": selected_q.get("review_status_ai_diagnosis", "pending"),
                            "best_answer_why": selected_q.get("review_status_best_answer_why", "pending"),
                            "reflection": selected_q.get("review_status_reflection", "pending"),
                        }

                        if not any(insight_data.values()):
                            st.info("아직 통찰이 생성되지 않았습니다. '재생성' 탭에서 생성하세요.")
                        else:
                            for section_key, label in SECTION_LABELS.items():
                                content = insight_data.get(section_key)
                                status = review_status.get(section_key, "pending")
                                status_cls = status

                                with st.container():
                                    st.markdown(f"""
                                    <div class="section-review {status_cls}">
                                        <strong>{label}</strong>
                                        <span style="margin-left:12px;">{REVIEW_STATUS_LABEL.get(status, status)}</span>
                                    </div>
                                    """, unsafe_allow_html=True)

                                    if content:
                                        st.markdown(content[:500] + ("..." if len(content) > 500 else ""))

                                    approve_col, reject_col = st.columns(2)
                                    with approve_col:
                                        if st.button(f"✅ {label} 승인", key=f"app_{selected_id}_{section_key}"):
                                            r = admin_review_insight(selected_id, section_key, True)
                                            if r and r.get("ok"):
                                                st.success("승인 완료")
                                                st.rerun()

                                    with reject_col:
                                        with st.popover(f"❌ {label} 반려"):
                                            rr = st.text_area(
                                                "반려 사유 (10자 이상)",
                                                key=f"rej_{selected_id}_{section_key}",
                                                max_chars=500,
                                            )
                                            if st.button("반려 확인", key=f"rej_ok_{selected_id}_{section_key}"):
                                                if len(rr) >= 10:
                                                    r = admin_review_insight(selected_id, section_key, False, rr)
                                                    if r and r.get("ok"):
                                                        st.success("반려 완료")
                                                        st.rerun()
                                                else:
                                                    st.error("10자 이상 입력 필요")

                    # ── 재생성 탭 ──
                    with ed_tabs[3]:
                        st.caption("LLM으로 통찰 섹션 재생성")
                        regen_sections = st.multiselect(
                            "재생성할 섹션",
                            list(SECTION_LABELS.keys()),
                            default=["root_cause", "ai_diagnosis", "best_answer_why", "reflection"],
                            format_func=lambda s: SECTION_LABELS[s],
                        )
                        extra_instruction = st.text_input("추가 지시사항 (선택)", max_chars=500)

                        if st.button("🔄 재생성 실행", type="primary"):
                            with st.spinner("LLM이 통찰을 생성 중입니다..."):
                                result = admin_regenerate_insight(
                                    selected_id,
                                    sections=regen_sections,
                                    additional_instruction=extra_instruction or None,
                                )
                            if result and result.get("ok"):
                                st.success(f"✅ 재생성 완료 (v{result.get('insight_version', '?')})")
                                st.rerun()
                            else:
                                st.error("재생성 실패")

                    # ── 단편 설교 탭 (작업 W) ──
                    with ed_tabs[4]:
                        st.caption("사용자 랭킹 상세 페이지에 노출되는 단편 설교")
                        _gen_key = f"_sermon_gen_{selected_id}"
                        _cur_title = selected_q.get("short_sermon_title") or ""
                        _cur_text = selected_q.get("short_sermon_text") or ""
                        _cur_doc = selected_q.get("short_sermon_doc_id") or ""

                        if st.button("🤖 LLM 단편 설교 생성", key="gen_sermon_btn"):
                            with st.spinner("단편 설교를 생성 중입니다..."):
                                _gres = admin_generate_short_sermon(selected_id)
                            if _gres and _gres.get("ok"):
                                st.session_state[_gen_key] = _gres.get("text", "")
                                st.success("생성 완료 — 아래 본문을 검토/수정 후 저장하세요")
                                st.rerun()
                            else:
                                st.error((_gres or {}).get("error", "단편 설교 생성 실패"))

                        _sermon_title = st.text_input("단편 설교 제목", value=_cur_title, key="sermon_title_in")
                        _sermon_text = st.text_area(
                            "단편 설교 본문",
                            value=st.session_state.get(_gen_key, _cur_text),
                            height=220,
                            key="sermon_text_in",
                        )
                        _sermon_doc = st.text_input("원문 문서 ID (선택)", value=_cur_doc, key="sermon_doc_in")

                        if st.button("💾 단편 설교 저장", key="sermon_save_btn", type="primary"):
                            _ok = True
                            for _fld, _val in [
                                ("short_sermon_title", _sermon_title),
                                ("short_sermon_text", _sermon_text),
                                ("short_sermon_doc_id", _sermon_doc),
                            ]:
                                _res = admin_patch_trending(
                                    snapshot_id=selected_id,
                                    field=_fld,
                                    new_value=_val,
                                    edit_reason="단편 설교 편집",
                                )
                                if not (_res and _res.get("ok")):
                                    _ok = False
                                    st.error(f"{_fld} 저장 실패")
                            if _ok:
                                st.session_state.pop(_gen_key, None)
                                st.success("✅ 단편 설교 저장 완료")
                                st.rerun()

                    # ── 추가 질문하기 탭 (LLM 후속 질문, 맥락 기반) ──
                    with ed_tabs[5]:
                        _q_user = selected_q.get("question", selected_q.get("canonical_text", ""))
                        _q_answer = (
                            selected_q.get("admin_edited_text")
                            or selected_q.get("best_answer_text")
                            or selected_q.get("canonical_text", "")
                        )

                        st.caption(
                            "이 인기 QA의 내용을 근거로 LLM에게 **추가 질문**을 할 수 있습니다. "
                            "단독적인 질문이 아니라, 아래 '위의 내용'을 바탕으로 이어지는 후속 질문을 입력하세요."
                        )

                        # ── 위의 내용 (근거 컨텍스트) ──
                        with st.expander("📋 근거로 삼을 내용 (위의 내용)", expanded=True):
                            st.markdown(f"**원본 질문:** {_q_user}")
                            st.markdown(f"**답변:** {(_q_answer or '(답변 없음)')[:600]}")
                            _ins = []
                            if selected_q.get("root_cause_analysis"):
                                _ins.append(("근본 원인", selected_q.get("root_cause_analysis")))
                            if selected_q.get("ai_diagnosis"):
                                _ins.append(("AI 진단", selected_q.get("ai_diagnosis")))
                            if selected_q.get("best_answer_why"):
                                _ins.append(("도움된 이유", selected_q.get("best_answer_why")))
                            if selected_q.get("reflection_prompt"):
                                _ins.append(("성찰 질문", selected_q.get("reflection_prompt")))
                            for _lbl, _val in _ins:
                                st.markdown(f"**{_lbl}:** {str(_val)[:400]}")

                        # ── 안내/가이드 ──
                        st.info(
                            "💡 **추가 질문하기** — 위의 질문과 답변을 바탕으로 이어질 후속 질문을 입력하세요. "
                            "입력하신 질문은 원본 질문·답변·통찰과 함께 LLM에 전달되어, "
                            "맥락에 맞는(근거 기반) 답변을 받습니다. 위 내용과 무관한 단독 질문은 피해주세요."
                        )

                        # ── 입력 + 제출 ──
                        _ask_q = st.text_area(
                            "추가 질문 (위의 내용을 근거로)",
                            height=120,
                            key="ask_q_in",
                            placeholder="예: 위 답변에서 '하나님의 용서' 부분을 구체적인 성경 구절과 함께 더 자세히 설명해 주세요.",
                            help="이 질문은 위의 원본 질문과 답변 맥락에 묶여 LLM에 전달됩니다.",
                        )
                        if st.button("➕ 추가 질문하기", key="ask_submit_btn", type="primary"):
                            if not _ask_q or not _ask_q.strip():
                                st.warning("질문을 입력하세요.")
                            else:
                                with st.spinner("LLM이 맥락을 바탕으로 답변하는 중..."):
                                    _res = admin_ask_trending_question(selected_id, _ask_q.strip())
                                if _res and _res.get("ok"):
                                    st.success("✅ 맥락 기반 답변")
                                    st.markdown(_res.get("answer", ""))
                                elif _res:
                                    st.error(_res.get("error", "추가 질문에 실패했습니다."))
                                else:
                                    st.error("서버 응답이 없습니다. 관리자 API 키/서버 상태를 확인하세요.")

                    # ── 추천 질문 탭 (작업 W, 사용자용) ──
                    with ed_tabs[6]:
                        st.caption("사용자가 단편 설교를 본 뒤 이어갈 추천 질문 (한 줄에 하나씩, 최대 6개)")
                        _cur_fu = selected_q.get("suggested_followups") or []
                        if not isinstance(_cur_fu, list):
                            _cur_fu = []
                        _fu_seed = "\n".join(str(x) for x in _cur_fu)
                        _fu_text = st.text_area(
                            "추천 질문 목록",
                            value=_fu_seed,
                            height=180,
                            key="followup_in",
                            help="한 줄에 하나의 질문을 입력하세요",
                        )
                        if st.button("💾 추천 질문 저장", key="followup_save_btn", type="primary"):
                            _items = [ln.strip() for ln in _fu_text.split("\n") if ln.strip()]
                            if len(_items) > 6:
                                st.error("추천 질문은 최대 6개까지 가능합니다")
                            else:
                                _res = admin_patch_trending(
                                    snapshot_id=selected_id,
                                    field="suggested_followups",
                                    new_value=json.dumps(_items, ensure_ascii=False),
                                    edit_reason="추천 질문 편집",
                                )
                                if _res and _res.get("ok"):
                                    st.success("✅ 추천 질문 저장 완료")
                                    st.rerun()
                                else:
                                    st.error("추천 질문 저장 실패")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 2: 검수 대기열
# ══════════════════════════════════════════════════════════════════════════════
with tab_queue:
    st.subheader("📋 검수 대기열")

    queue = admin_insight_queue()
    if not queue:
        st.warning("대기열 데이터를 불러올 수 없습니다.")
    else:
        pending = queue.get("pending_review", [])
        needs_fix = queue.get("needs_correction", [])

        cq1, cq2 = st.columns(2)
        cq1.metric("검토 대기", queue.get("total_pending", len(pending)))
        cq2.metric("수정 필요", queue.get("total_needs_correction", len(needs_fix)))

        st.divider()

        st.markdown("### ⏳ 검토 대기 중")
        if not pending:
            st.info("검토 대기 중인 통찰이 없습니다.")
        else:
            for p in pending:
                with st.expander(f"{p.get('question', '?')[:80]} — {p.get('pending_sections', [])}"):
                    st.write(f"**스냅샷 ID**: `{p.get('snapshot_id', '')}`")
                    st.write(f"**질문 횟수**: {p.get('total_count', 0)}회")
                    st.write(f"**트렌드 점수**: {p.get('trend_score', 0):.1f}")
                    for sec in p.get("pending_sections", []):
                        st.write(f"- {SECTION_LABELS.get(sec, sec)}")

        st.divider()

        st.markdown("### 🔧 수정 필요")
        if not needs_fix:
            st.info("수정이 필요한 통찰이 없습니다.")
        else:
            for n in needs_fix:
                with st.expander(f"{n.get('question', '?')[:80]} — {n.get('rejected_sections', [])}"):
                    st.write(f"**스냅샷 ID**: `{n.get('snapshot_id', '')}`")
                    for sec in n.get("rejected_sections", []):
                        st.write(f"- ❌ {SECTION_LABELS.get(sec, sec)}")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 통계
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    st.subheader("📊 통계")

    stats = admin_insight_stats()
    if not stats:
        st.warning("통계 데이터를 불러올 수 없습니다.")
    else:
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("전체 스냅샷", stats.get("total_snapshots", 0))

        coverage = stats.get("insight_coverage", {})
        sc2.metric("통찰 생성됨", coverage.get("with_insight", 0))
        sc3.metric("통찰 미생성", coverage.get("without_insight", 0))

        st.divider()

        # 편집 통계
        edit_stats = stats.get("edit_stats", {})
        st.markdown("### ✏️ 편집 통계")
        ec1, ec2, ec3 = st.columns(3)
        ec1.metric("전체 편집", edit_stats.get("total_edits", 0))
        ec2.metric("롤백", edit_stats.get("total_reverts", 0))
        ec3.metric("활성 편집자", edit_stats.get("unique_editors", 0))

        st.divider()

        # 모델 품질
        model_quality = stats.get("model_quality", {})
        st.markdown("### 🤖 모델 품질")
        if model_quality:
            df_mq = pd.DataFrame([
                {"모델": k, "승인률": f"{v.get('approval_rate', 0)*100:.1f}%", "생성 수": v.get("total_generated", 0)}
                for k, v in model_quality.items()
            ])
            st.dataframe(df_mq, use_container_width=True, hide_index=True)
        else:
            st.info("아직 모델 품질 데이터가 없습니다.")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 4: 인기 답변
# ══════════════════════════════════════════════════════════════════════════════
with tab_answers:
    st.subheader("💬 인기 답변")

    answers_data = dash.get("top_answers", []) if dash else []
    if not answers_data:
        st.info("인기 답변 데이터가 없습니다.")
    else:
        for ans in answers_data:
            with st.container():
                st.markdown(f"""
                <div class="trend-card">
                    <h4>{ans.get('question', '?')[:100]}</h4>
                    <p style="color:#555;font-size:0.9rem;">{ans.get('canonical_text', '')[:200]}...</p>
                    <div class="meta">
                        <span>👍 {ans.get('positive_feedback', 0)}</span>
                        <span>📊 {ans.get('total_count', 0)}회</span>
                        <span>⭐ {ans.get('trend_score', 0):.1f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.caption("인기 QA 시스템 | 트렌딩 집계 + LLM 통찰 + 관리자 검수")
