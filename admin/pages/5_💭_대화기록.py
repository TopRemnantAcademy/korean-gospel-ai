"""💭 대화 & 재방문 — Q/A 기록 + 재방문 메시지 관리."""
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
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    list_memory, memory_stats, delete_memory,
    chat_ping, get_greeting, simulate_greeting, list_subscribers,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.title("💭 대화 & 재방문")

tab_qa, tab_sim, tab_ret = st.tabs(["📋 대화 기록", "💬 재방문 메시지", "📊 재방문 현황"])


# ─────────────────────────────────────────────────────────────────────────────
# 탭 1: 대화 기록
# ─────────────────────────────────────────────────────────────────────────────
with tab_qa:
    stats = memory_stats() or {}
    c1, c2, c3 = st.columns(3)
    c1.metric("전체 대화 수", stats.get("total", 0))
    c2.metric("최근 7일", stats.get("last_7_days", 0))
    if st.button("🔄 새로고침", key="mem_refresh"):
        st.rerun()

    sc1, sc2 = st.columns([4, 1])
    with sc1:
        search = st.text_input("🔍 검색", key="mem_search", placeholder="구원, 회개, 사랑...")
    items = list_memory(search=search if search else None, limit=200) or []

    if not items:
        st.info("대화 기록이 없습니다." if not search else f"'{search}' 검색 결과 없음")
    else:
        st.caption(f"총 **{len(items)}건**")

        for it in items:
            when = (it.get("created_at") or "")[:19].replace("T", " ")
            q = it["question"]
            a = it["answer"]
            with st.expander(f"📅 {when}  ·  {q[:80]}{'...' if len(q)>80 else ''}"):
                st.markdown(f"**🙋 질문:** {q}")
                st.markdown("**✝ 답변:**")
                st.markdown(a)
                cited = it.get("cited_versions") or []
                if cited:
                    st.markdown(f"**📎 참고 자료 {len(cited)}개**")
                    # X-Plus B/C: 출처(source_type) 필터 + 정렬 UI
                    _src_types = sorted({c.get("source_type") for c in cited if c.get("source_type")})
                    _sel_src = (
                        st.multiselect(
                            "🏷 출처 필터", _src_types, default=_src_types,
                            key=f"srcf_{it['interaction_id']}",
                        )
                        if _src_types else None
                    )
                    _sort_key = st.radio(
                        "정렬 기준", ["관련도", "신뢰도"], horizontal=True,
                        key=f"sort_{it['interaction_id']}", index=0,
                    )
                    _desc = st.checkbox("높은 순", value=True, key=f"rev_{it['interaction_id']}")
                    _shown = [c for c in cited if _sel_src is None or c.get("source_type") in _sel_src]
                    _shown.sort(
                        key=lambda c: (c.get("reliability_score") if _sort_key == "신뢰도" else c.get("score")) or 0,
                        reverse=_desc,
                    )
                    for j, c in enumerate(_shown, 1):
                        with st.container(border=True):
                            st.caption(
                                f"{j}. {c.get('title','?')} v{c.get('version_number','?')} "
                                f"· 관련도 {c.get('score',0):.2f}"
                                + (f" · 신뢰도 {c.get('reliability_score','-')}" if c.get('reliability_score') is not None else "")
                            )
                            # X-Plus A / V-3: 청크 본문 스니펫 드릴다운
                            # (주의: expander 는 expander 안에 중첩 불가 — container 로 대체)
                            if c.get("snippet"):
                                with st.container(border=True):
                                    st.caption("📄 인용 청크 본문")
                                    st.markdown(c["snippet"])
                            # 검색 설명 (왜 이 문서가 선택됐는지)
                            if c.get("explanation"):
                                st.caption(f"💡 {c['explanation']}")
                            if c.get("matched_keywords"):
                                st.caption(f"🔑 {', '.join(c['matched_keywords'])}")
                bc1, bc2, bc3 = st.columns([1, 1, 4])
                with bc1:
                    st.caption(f"⏱ {it.get('elapsed_ms', 0)} ms")
                with bc2:
                    fb = it.get("feedback")
                    st.caption("👍" if fb == 1 else "👎" if fb == -1 else "—")
                with bc3:
                    _confirm = st.checkbox("정말 삭제하시겠습니까?", key=f"delconf_{it['interaction_id']}")
                    if st.button("🗑 삭제", key=f"del_{it['interaction_id']}", disabled=not _confirm, type="primary"):
                        if delete_memory(it["interaction_id"]):
                            st.success("삭제됨")
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# 탭 2: 재방문 메시지 테스트 + 시뮬레이터
# ─────────────────────────────────────────────────────────────────────────────
with tab_sim:
    st.caption("감정 위로 ❌ · 영적 재해석 질문 ✅")

    sub_tab1, sub_tab2 = st.tabs(["🎯 사용자 테스트", "🔧 조건 시뮬레이터"])

    with sub_tab1:
        col_l, col_r = st.columns(2)
        with col_l:
            uid = st.text_input("구독자 ID (비워두면 'self')", key="t1_uid").strip() or None
            if st.button("⚡ Ping", use_container_width=True):
                result = chat_ping(uid)
                if result:
                    st.metric("기존 사용자?", "✅ 예" if result.get("is_returning") else "🆕 신규")
                    st.json(result)
                else:
                    st.error("API 연결 실패")
        with col_r:
            mode_sel = st.selectbox("mode", ["auto", "rule", "llm"], key="t1_mode")
            if st.button("💬 메시지 생성", use_container_width=True):
                res = get_greeting(uid, mode=mode_sel)
                if res:
                    st.info(res.get('greeting', ''))
                else:
                    st.error("API 연결 실패")

    with sub_tab2:
        EMOTIONAL_OPTS = {
            "(없음)": None, "anxious": "anxious", "grieving": "grieving",
            "hopeful": "hopeful", "calm": "calm", "curious": "curious",
        }
        SALVATION_OPTS = {
            "unknown": "unknown", "seeker": "seeker",
            "uncertain": "uncertain", "assured": "assured", "mature": "mature",
        }
        cs1, cs2, cs3 = st.columns(3)
        with cs1:
            emo_label = st.selectbox("감정 상태", list(EMOTIONAL_OPTS.keys()), key="sim_emo")
            sal_label = st.selectbox("구원 여정", list(SALVATION_OPTS.keys()), key="sim_sal")
        with cs2:
            use_days = st.checkbox("경과일 설정", key="sim_usedays")
            days_sim = st.slider("경과일", 0, 365, 7, key="sim_days") if use_days else None
            total_q_sim = st.number_input("총 대화 횟수", 0, 200, 5, key="sim_tq")
        with cs3:
            st.write("")

        if st.button("🎲 메시지 생성", use_container_width=True):
            res = simulate_greeting(
                emotional_state=EMOTIONAL_OPTS[emo_label],
                salvation_status=SALVATION_OPTS[sal_label],
                days_away=days_sim,
                total_questions=int(total_q_sim),
            )
            if res:
                st.success(res['message'])
            else:
                st.error("API 연결 실패")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 3: 재방문 현황
# ─────────────────────────────────────────────────────────────────────────────
with tab_ret:
    subs = list_subscribers()
    if not subs:
        st.warning("구독자 없음 또는 API 연결 실패")
        # [FIX #17] st.stop() 제거 — 전체 스크립트 중단 없이 이 탭만 조기 종료
    else:
        now = datetime.utcnow()

        def _parse_dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s).split(".")[0])
            except Exception:
                return None

        rows = []
        for sub in subs:
            last_dt = _parse_dt(sub.get("last_active_at"))
            tq = sub.get("total_questions", 0) or 0
            days_away = max(0, (now - last_dt).days) if last_dt else None
            rows.append({
                "ID": sub.get("subscriber_id", "?")[:16],
                "이름": sub.get("display_name") or "익명",
                "총 대화": tq,
                "재방문": tq > 1,
                "경과일": days_away,
                "마지막 방문": str(last_dt.date()) if last_dt else "—",
                "감정": sub.get("emotional_state") or "—",
            })

        df = pd.DataFrame(rows)
        total = len(df)
        returning = int(df["재방문"].sum())
        lapsed = int(df[df["경과일"].notna() & (df["경과일"] > 30)].shape[0])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("전체", total)
        m2.metric("재방문", returning)
        m3.metric("7일내 재방문", int(df[df["재방문"] & (df["경과일"].fillna(999) <= 7)].shape[0]))
        m4.metric("30일+ 이탈", lapsed, delta_color="inverse")

        show_f = st.radio("표시", ["전체", "재방문만", "30일+ 이탈"], horizontal=True, key="ret_f")
        if show_f == "재방문만":
            df = df[df["재방문"]]
        elif show_f == "30일+ 이탈":
            df = df[df["경과일"].notna() & (df["경과일"] > 30)]

        st.dataframe(df.drop(columns=["재방문"]).sort_values("경과일"), use_container_width=True, height=400)
