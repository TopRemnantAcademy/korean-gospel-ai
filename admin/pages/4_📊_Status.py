"""📊 모니터링 — 시스템 현황 + 에러 로그 + 구독 현황."""
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
    get_collections, list_documents, run_regression,
    get_errors, get_error_stats, get_subscription_stats,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="모니터링", page_icon="📊", layout="wide")
st.title("📊 모니터링")

col_r, _ = st.columns([1, 5])
with col_r:
    if st.button("🔄 새로고침", use_container_width=True):
        st.rerun()

tab_sys, tab_err, tab_sub, tab_tier = st.tabs(["🗂 시스템 현황", "🚨 에러 로그", "💳 구독 현황", "🏗 인프라 티어"])


# ─────────────────────────────────────────────────────────────────────────────
# 탭 1: 시스템 현황
# ─────────────────────────────────────────────────────────────────────────────
with tab_sys:
    st.subheader("📚 자료 통계")
    docs = list_documents() or []
    if not docs:
        st.info("아직 올린 자료가 없습니다. 📥 Upload 페이지에서 첫 자료를 올려보세요.")
    else:
        states: dict = {}
        for d in docs:
            s = d.get("latest_state", "?")
            states[s] = states.get(s, 0) + 1
        KR = {"draft": "임시", "validated": "검증완료", "published": "공개됨",
              "superseded": "옛 버전", "archived": "보관됨"}
        chart_data = pd.DataFrame({"개수": {KR.get(k, k): v for k, v in states.items()}})
        st.bar_chart(chart_data)

    st.divider()
    st.subheader("🗂 검색 인덱스 (벡터 DB)")
    info = get_collections()
    if info is None:
        st.error("API 연결 실패")
    elif info.get("warning"):
        st.warning(f"안내: {info['warning']}")
    else:
        cols = info.get("collections", [])
        if not cols:
            st.info("아직 검색 인덱스에 등록된 자료가 없습니다.")
        else:
            df = pd.DataFrame(cols).rename(columns={
                "name": "컬렉션", "points_count": "청크 수",
                "vectors_count": "벡터 수", "status": "상태",
            })
            st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("🧪 평가셋 회귀 테스트")
    st.caption("data/eval/questions.json 의 질문들을 현재 검색 시스템으로 돌려봅니다.")
    if st.button("▶️ 평가 실행", key="run_eval"):
        with st.spinner("평가 실행 중..."):
            res = run_regression()
        if res and res.get("ok"):
            st.success(f"통과 {res['passed']}/{res['total']}건")
            rows = []
            for it in res["items"]:
                rows.append({
                    "질문": it["query"],
                    "상위3 자료": ", ".join(it["top_titles"]),
                    "top1 점수": round(it.get("top1_score", 0), 3),
                    "기대 일치": "✅" if it.get("expected_match") else ("❌" if it.get("expected_match") is False else "-"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        elif res:
            st.error(res.get("reason", "평가 실패"))


# ─────────────────────────────────────────────────────────────────────────────
# 탭 2: 에러 로그
# ─────────────────────────────────────────────────────────────────────────────
with tab_err:
    stats = get_error_stats()
    if stats is None:
        st.error("❌ API 연결 실패")
        st.stop()

    e1h  = stats.get("errors_1h", 0)
    e24h = stats.get("errors_24h", 0)
    c1h  = stats.get("critical_1h", 0)
    s24h = stats.get("slow_24h", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🔴 에러 (1시간)", e1h)
    m2.metric("🔴 에러 (24시간)", e24h)
    m3.metric("⚡ CRITICAL (1시간)", c1h)
    m4.metric("🐢 SLOW (24시간)", s24h)

    if e1h + c1h > 0:
        st.error(f"⚠️ 최근 1시간 에러 {e1h + c1h}건 — 아래 목록 확인")
    elif e24h > 0:
        st.warning(f"최근 24시간 에러 {e24h}건")
    else:
        st.success("✅ 최근 24시간 에러 없음")

    st.divider()

    # 필터
    cf1, cf2, cf3, cf4 = st.columns(4)
    with cf1:
        level_f = st.selectbox("레벨", ["전체", "ERROR", "SLOW", "CRITICAL"], key="err_lv")
    with cf2:
        hours_f = st.selectbox("기간", [1, 6, 24, 72, 168], index=2,
                               format_func=lambda h: f"최근 {h}시간" if h < 24 else f"최근 {h//24}일",
                               key="err_hr")
    with cf3:
        path_f = st.text_input("경로 포함", key="err_path", placeholder="/chat")
    with cf4:
        limit_f = st.number_input("최대 건수", 10, 500, 200, key="err_lim")

    lvl_param = None if level_f == "전체" else level_f
    rows = get_errors(limit=int(limit_f), level=lvl_param,
                     path=path_f.strip() or None, hours=int(hours_f))

    if not rows:
        st.info("조건에 맞는 에러 로그가 없습니다.")
    else:
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["시각"] = df["timestamp"].dt.strftime("%m/%d %H:%M:%S")
        EMOJI = {"ERROR": "🔴", "SLOW": "🐢", "CRITICAL": "💀"}
        df["레벨"] = df["level"].map(lambda v: f"{EMOJI.get(v,'⚪')} {v}")

        show = {
            "시각": "시각", "레벨": "레벨", "method": "메서드",
            "path": "경로", "status_code": "상태", "duration_ms": "응답(ms)",
            "error_type": "에러유형", "error_message": "메시지",
        }
        df2 = df.rename(columns={k: v for k, v in show.items() if k in df.columns})
        display = [v for k, v in show.items() if v in df2.columns]
        st.dataframe(df2[display], use_container_width=True, height=380,
                     column_config={"응답(ms)": st.column_config.NumberColumn(format="%d ms"),
                                    "상태": st.column_config.NumberColumn(format="%d")})

        # traceback 상세
        has_tb = [r for r in rows if r.get("traceback")]
        if has_tb:
            st.divider()
            st.subheader("🔍 Traceback 상세")
            for r in has_tb:
                ts = r.get("timestamp", "")
                try:
                    r["time_str"] = datetime.fromisoformat(ts).strftime("%m/%d %H:%M:%S")
                except Exception:
                    r["time_str"] = ts[:19]
            opts = {f"[{r['level']}] {r['time_str']} — {r['path']} ({r.get('error_type','?')})": r
                    for r in has_tb}
            sel_label = st.selectbox("에러 선택", list(opts.keys()), key="tb_sel")
            sel = opts[sel_label]
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.markdown(f"**레벨**: `{sel['level']}`")
                st.markdown(f"**경로**: `{sel['method']} {sel['path']}`")
                st.markdown(f"**상태코드**: `{sel['status_code']}`")
            with col_d2:
                st.markdown(f"**에러유형**: `{sel.get('error_type','—')}`")
                st.markdown(f"**응답시간**: `{sel['duration_ms']} ms`")
            st.code(sel.get("error_message", ""), language="text")
            if sel.get("traceback"):
                st.code(sel["traceback"], language="python")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 3: 구독 현황
# ─────────────────────────────────────────────────────────────────────────────
with tab_sub:
    sub_stats = get_subscription_stats()
    if not sub_stats:
        st.warning("구독 통계를 불러올 수 없습니다.")
    else:
        total = sub_stats.get("total", 0)
        by_tier = sub_stats.get("by_tier", {})
        expiring = sub_stats.get("trial_expiring_24h", 0)
        expired = sub_stats.get("trial_expired", 0)

        TIER_LABEL = {"guest": "무료체험", "member": "유료회원", "supporter": "후원회원"}

        cols_t = st.columns(len(by_tier) + 2)
        for i, (t, cnt) in enumerate(by_tier.items()):
            cols_t[i].metric(TIER_LABEL.get(t, t), cnt)
        cols_t[-2].metric("⚠️ 체험 만료 임박 (24h)", expiring, delta=None)
        cols_t[-1].metric("🔒 체험 만료됨", expired, delta_color="inverse")

        st.caption(f"전체 사용자 {total}명")

        if expiring > 0:
            st.warning(f"⚠️ 24시간 내 무료체험 만료 예정: **{expiring}명** — 👥 사람 페이지에서 개별 연장/업그레이드 가능")
        if expired > 0:
            st.info(f"🔒 현재 체험 만료로 차단된 사용자: **{expired}명**")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 4: 인프라 티어
# ─────────────────────────────────────────────────────────────────────────────
with tab_tier:
    st.subheader("🏗 인프라 티어 현황")

    import os as _os
    CURRENT_TIER = _os.getenv("CURRENT_TIER", "tier_0_5")

    TIER_INFO = {
        "tier_0":   {"name": "Tier 0",   "subtitle": "로컬 개발",      "users": "1명",    "cost": "$0/월",       "color": "#e8f5e9"},
        "tier_0_5": {"name": "Tier 0.5", "subtitle": "친구 5명 시범",  "users": "~10명",  "cost": "$0/월",       "color": "#fff9c4"},
        "tier_1":   {"name": "Tier 1",   "subtitle": "소규모 운영",    "users": "~50명",  "cost": "$0/월",       "color": "#c8e6c9",
                     "trigger": "사용자 50명 도달 또는 24/7 필요"},
        "tier_1_5": {"name": "Tier 1.5", "subtitle": "안정화 & 도메인","users": "~200명", "cost": "$10~30/월",   "color": "#a5d6a7",
                     "trigger": "사용자 100명 또는 도메인 필요"},
        "tier_2":   {"name": "Tier 2",   "subtitle": "중규모 운영",    "users": "~500명", "cost": "$100~200/월", "color": "#81c784",
                     "trigger": "사용자 500명 또는 무료 한도 100% 사용"},
    }

    cur = TIER_INFO.get(CURRENT_TIER, TIER_INFO["tier_0_5"])
    st.markdown(f"**현재 티어**: {cur['name']} — {cur['subtitle']}  |  비용: {cur['cost']}")

    st.divider()

    # 리소스 사용률 (tier_monitor 서비스 사용)
    try:
        from backend.app.services.tier_monitor import get_monitor, TIER_LIMITS
        _monitor = get_monitor()

        @st.cache_data(ttl=60)
        def _load_usage():
            try:
                u = _monitor.measure_sync()
                return {
                    "subscriber_count": u.subscriber_count,
                    "active_sessions":  u.active_sessions,
                    "db_size_mb":       u.db_size_mb,
                    "qdrant_index_mb":  u.qdrant_index_mb,
                    "daily_llm_cost":   u.daily_llm_cost_usd,
                }
            except Exception:
                return {}

        _limits = TIER_LIMITS.get(CURRENT_TIER, {})
        _raw    = _load_usage()

        if _raw:
            r1, r2 = st.columns(2)
            with r1:
                max_users = _limits.get("max_users", 10)
                cnt = _raw.get("subscriber_count", 0)
                st.metric("👥 사용자", f"{cnt} / {max_users}")
                st.progress(min(cnt / max(max_users, 1), 1.0))

                max_sess = _limits.get("max_sessions", 5)
                sess = _raw.get("active_sessions", 0)
                st.metric("🔄 동시 세션", f"{sess} / {max_sess}")
                st.progress(min(sess / max(max_sess, 1), 1.0))

            with r2:
                max_db = _limits.get("max_db_size_mb", 500)
                db_mb  = _raw.get("db_size_mb", 0)
                st.metric("💾 DB 크기", f"{db_mb:.1f} / {max_db} MB")
                st.progress(min(db_mb / max(max_db, 1), 1.0))

                max_q = _limits.get("max_qdrant_size_mb", 1000)
                q_mb  = _raw.get("qdrant_index_mb", 0)
                st.metric("🎯 Qdrant 인덱스", f"{q_mb:.1f} / {max_q} MB")
                st.progress(min(q_mb / max(max_q, 1), 1.0))

            # 업그레이드 권고
            user_pct = _raw.get("subscriber_count", 0) / max(_limits.get("max_users", 10), 1)
            if user_pct >= 0.8:
                st.warning("⏰ 사용자 80% 이상 — 다음 티어 업그레이드 검토 권장")
        else:
            st.info("리소스 사용 데이터를 불러올 수 없습니다.")
    except ImportError:
        # tier_monitor.py 제거됨 (2026-06-09 리팩터링)
        # 실시간 리소스 측정은 backend /health 또는 Langfuse 대시보드 사용
        st.info("💡 실시간 리소스 모니터링은 Langfuse 대시보드 또는 서버 로그를 확인하세요.")
    except Exception as _e:
        st.warning(f"리소스 측정 오류: {_e}")

    st.divider()
    st.subheader("📊 티어 비교")

    _comparison = []
    for tk in ["tier_0", "tier_0_5", "tier_1", "tier_1_5", "tier_2"]:
        t = TIER_INFO.get(tk, {})
        _comparison.append({
            "티어": t.get("name", ""),
            "사용자": t.get("users", ""),
            "비용": t.get("cost", ""),
            "클라우드": "❌" if tk in ("tier_0", "tier_0_5") else "✅",
            "도메인": "❌" if tk in ("tier_0", "tier_0_5", "tier_1") else "✅",
            "업그레이드 기준": t.get("trigger", "—"),
            "현재": "🌟" if tk == CURRENT_TIER else "",
        })
    st.dataframe(pd.DataFrame(_comparison), use_container_width=True, hide_index=True)
