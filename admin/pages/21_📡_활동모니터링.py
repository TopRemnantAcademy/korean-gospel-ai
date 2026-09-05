"""📡 활동 모니터링 — 사용자 시청/행동 로그 집계 (클라이언트 이벤트 소스)."""
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
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import get_activity_summary, get_activity_events
from admin.lib.auth import gate

st.set_page_config(page_title="활동 모니터링", page_icon="📡", layout="wide")
gate(os.getenv("APP_PASSWORD", ""))
st.title("📡 활동 모니터링 (시청/행동 로그)")

st.caption(
    "모바일/웹 클라이언트에서 수집한 활동 이벤트(시청·검색·화면이동·말씀annotate·공유·세션·에러)를 "
    "집계합니다. 읽기 전용 — 운영·콘텐츠 기획 지표로 활용."
)

days = st.slider("기간(일)", min_value=1, max_value=90, value=30, step=1)
if st.button("🔄 새로고침", use_container_width=False):
    st.rerun()

data = get_activity_summary(days=days)
if data is None:
    st.error("활동 데이터를 불러오지 못했습니다 (백엔드 연결/권한 확인).")
    st.stop()

# ── 상단 KPI ──────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 이벤트", f"{data.get('total_events', 0):,}")
c2.metric("활성 유저 DAU", f"{data.get('dau', 0):,}")
c3.metric("WAU", f"{data.get('wau', 0):,}")
c4.metric("MAU", f"{data.get('mau', 0):,}")

# ── 이벤트 타입 분포 ────────────────────────────────────────────────────
st.subheader("📊 이벤트 타입 분포")
et = data.get("events_by_type", [])
if et:
    df_et = pd.DataFrame(et).rename(columns={"event_type": "이벤트", "count": "건수"})
    st.bar_chart(df_et.set_index("이벤트")["건수"])
else:
    st.info("데이터 없음")

# ── Top 시청 콘텐츠 ─────────────────────────────────────────────────────
st.subheader("🎬 Top 시청 콘텐츠 (재생완료 기준)")
top = data.get("top_media", [])
if top:
    df_top = pd.DataFrame(top)
    df_top = df_top.rename(columns={
        "media_id": "미디어ID", "title": "제목", "category": "카테고리",
        "media_type": "유형", "watch_count": "시청수", "start_count": "시작수",
        "completion_rate": "완료율(%)",
    })
    df_top = df_top[["제목", "카테고리", "유형", "시청수", "시작수", "완료율(%)", "미디어ID"]]
    st.dataframe(df_top, use_container_width=True, height=420)
    chart_top = df_top.dropna(subset=["제목"]).head(15)
    if not chart_top.empty:
        st.bar_chart(chart_top.set_index("제목")["시청수"])
else:
    st.info("시청 기록 없음")

# ── 인기 검색어 ────────────────────────────────────────────────────────
st.subheader("🔍 인기 검색어")
sq = data.get("top_search", [])
if sq:
    df_sq = pd.DataFrame(sq).rename(columns={"query": "검색어", "count": "건수"})
    st.dataframe(df_sq, use_container_width=True, height=300)
    st.bar_chart(df_sq.head(15).set_index("검색어")["건수"])
else:
    st.info("검색 기록 없음")

# ── 이벤트 로그 (필터) ────────────────────────────────────────────────
st.subheader("📜 이벤트 로그")
with st.expander("필터", expanded=True):
    col_a, col_b, col_c = st.columns(3)
    f_type = col_a.text_input("event_type (비우면 전체)")
    f_sub = col_b.text_input("subscriber_id (비우면 전체)")
    f_media = col_c.text_input("media_id (비우면 전체)")
    col_d, col_e = st.columns(2)
    f_from = col_d.text_input("from (ISO, 예: 2026-08-01T00:00:00)")
    f_to = col_e.text_input("to (ISO)")

limit = st.slider("조회 건수", 10, 500, 100, key="ev_limit")
events = get_activity_events(
    event_type=f_type or None,
    subscriber_id=f_sub or None,
    media_id=f_media or None,
    from_=f_from or None,
    to=f_to or None,
    limit=limit,
)
if events is None:
    st.error("이벤트 조회 실패 (백엔드 연결/권한 확인).")
elif not events:
    st.info("조건에 맞는 이벤트가 없습니다.")
else:
    df_ev = pd.DataFrame(events)
    if "payload" in df_ev.columns:
        df_ev["payload"] = df_ev["payload"].apply(
            lambda p: (p if isinstance(p, dict) else {})
        )
        # 주요 payload 필드 평탄화
        for k in ("media_id", "query", "screen", "media_type", "progress_pct", "title"):
            df_ev[k] = df_ev["payload"].apply(lambda p: p.get(k) if isinstance(p, dict) else None)
    show_cols = [c for c in [
        "created_at", "event_type", "subscriber_id", "device_id", "platform",
        "screen", "media_id", "query", "media_type", "progress_pct", "title", "payload",
    ] if c in df_ev.columns]
    st.dataframe(df_ev[show_cols], use_container_width=True, height=500)
