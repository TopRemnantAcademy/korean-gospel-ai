"""D-C20: 영적 상태 대시보드 — 구원 여정 현황 + 다락방 매트릭스."""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: D-C20 — Admin 영적 상태 대시보드 (4탭)
# Reason: ORDERS.md EPIC D-C20
# Status: COMPLETED
# =============================================================================
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

from admin.lib.api_client import (
    spiritual_stats, spiritual_journey, spiritual_stagnant,
    darakbang_matrix, toggle_assume_saved,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="영적 상태 대시보드", page_icon="⛪", layout="wide")
st.title("⛪ 영적 상태 대시보드")
st.caption("사용자 구원 여정 현황 · 다락방 분포 · 정체 알림 · 사역 KPI")

if st.button("🔄 새로고침"):
    st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["📊 전체 분포", "🔀 여정 흐름", "⏰ 정체된 사람", "⛪ 다락방 매트릭스"])


# ─── 탭 1: 전체 분포 ───────────────────────────────────────
with tab1:
    st.subheader("구원 상태 분포")
    stats = spiritual_stats()
    if not stats:
        st.warning("API 연결 실패 — 백엔드 서버가 실행 중인지 확인하세요.")
        st.stop()

    total = stats.get("total", 0)
    dist = stats.get("salvation_status_dist", {})
    darakbang_v = stats.get("darakbang_verified", 0)
    assume_saved_n = stats.get("assume_saved_count", 0)

    # KPI 행
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("전체 사용자", total)
    col2.metric("다락방 검증 멤버", darakbang_v)
    col3.metric("assume_saved 활성", assume_saved_n)
    col4.metric("uncertain 비율",
                f"{round(dist.get('uncertain', 0) / max(total, 1) * 100, 1)}%",
                help="98% 가설 실제 검증 — 이 수치가 높을수록 확신 도움이 핵심")

    st.divider()

    # Salvation status 파이/바 차트
    if dist:
        _STATUS_ORDER = ["unknown", "seeker", "uncertain", "assured", "mature"]
        _STATUS_LABEL = {
            "unknown": "🔘 unknown (미상)",
            "seeker": "🔍 seeker (탐구)",
            "uncertain": "❓ uncertain (확신없음)",
            "assured": "✅ assured (확신)",
            "mature": "🌳 mature (성숙)",
        }
        ordered = {_STATUS_LABEL.get(k, k): dist.get(k, 0) for k in _STATUS_ORDER}
        df_dist = pd.DataFrame({"단계": list(ordered.keys()), "인원": list(ordered.values())})
        st.bar_chart(df_dist.set_index("단계"))

        # 수치 테이블
        st.dataframe(df_dist, use_container_width=True, hide_index=True)
    else:
        st.info("아직 사용자 데이터가 없습니다.")


# ─── 탭 2: 여정 흐름 ───────────────────────────────────────
with tab2:
    st.subheader("구원 여정 전환 흐름")
    days = st.slider("조회 기간 (일)", 7, 90, 30, key="journey_days")
    journey = spiritual_journey(days=days)

    if not journey:
        st.warning("API 연결 실패.")
    else:
        total_t = journey.get("total_transitions", 0)
        flows = journey.get("flows", {})

        c1, c2 = st.columns(2)
        c1.metric(f"최근 {days}일 전환 건수", total_t)

        # KPI: 사역의 핵심 지표
        assured_count = flows.get("uncertain→assured", 0) + flows.get("seeker→assured", 0)
        c2.metric("✨ 확신으로 전환 (사역 KPI)", assured_count,
                  help="이번 기간 구원의 확신을 갖게 된 사람 수 — 가장 중요한 지표")

        if flows:
            df_flow = pd.DataFrame([
                {"전환": k, "건수": v}
                for k, v in sorted(flows.items(), key=lambda x: -x[1])
            ])
            st.dataframe(df_flow, use_container_width=True, hide_index=True)
            st.bar_chart(df_flow.set_index("전환"))
        else:
            st.info(f"최근 {days}일 전환 기록이 없습니다.")


# ─── 탭 3: 정체된 사람 ─────────────────────────────────────
with tab3:
    st.subheader("관심 필요 — 정체된 사용자")
    stagnant_days = st.slider("정체 기준 (일)", 7, 60, 30, key="stagnant_days")
    stagnant = spiritual_stagnant(stagnant_days=stagnant_days)

    if not stagnant:
        st.warning("API 연결 실패.")
    else:
        users = stagnant.get("users", [])
        st.metric(f"{stagnant_days}일+ 정체 사용자", stagnant.get("count", 0))

        if users:
            df_stagnant = pd.DataFrame(users)
            # assume_saved 토글 UI
            st.dataframe(df_stagnant, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("수동 개입")
            selected_id = st.selectbox(
                "사용자 선택",
                options=[u["subscriber_id"] for u in users],
                format_func=lambda x: f"{x} ({next((u['salvation_status'] for u in users if u['subscriber_id'] == x), '?')})",
                key="stagnant_select",
            )
            if selected_id:
                col_a, col_b = st.columns(2)
                with col_a:
                    new_status = st.selectbox(
                        "salvation_status 변경",
                        ["(변경안함)", "unknown", "seeker", "uncertain", "assured", "mature"],
                        key="stagnant_new_status",
                    )
                with col_b:
                    assume = st.toggle("assume_saved 활성화", key="stagnant_assume")
                reason = st.text_input("변경 사유 (감사 로그)", key="stagnant_reason")

                if st.button("💾 저장", key="stagnant_save"):
                    also = new_status if new_status != "(변경안함)" else None
                    result = toggle_assume_saved(selected_id, assume, reason=reason, also_set_status=also)
                    if result:
                        st.success(f"✅ {selected_id} 업데이트 완료")
                    else:
                        st.error("저장 실패")
        else:
            st.success(f"🎉 {stagnant_days}일 이상 정체된 사용자가 없습니다!")


# ─── 탭 4: 다락방 매트릭스 ─────────────────────────────────
with tab4:
    st.subheader("다락방 역할 × 구원 상태 매트릭스")
    matrix_data = darakbang_matrix()

    if not matrix_data:
        st.warning("API 연결 실패.")
    else:
        matrix = matrix_data.get("matrix", {})
        urgent = matrix_data.get("urgent", [])
        urgent_count = matrix_data.get("urgent_count", 0)

        if urgent_count:
            st.error(f"🚨 긴급: 인도자/사역자 중 구원 확신 없는 사람 {urgent_count}명")
            df_urgent = pd.DataFrame(urgent)
            st.dataframe(df_urgent, use_container_width=True, hide_index=True)
            st.caption("인도자가 흔들리면 인도를 받는 식구들도 영향을 받습니다. 즉시 목양 연결을 권장합니다.")
            st.divider()

        if matrix:
            # 역할 × 구원상태 매트릭스 테이블
            _STATUS_ORDER = ["unknown", "seeker", "uncertain", "assured", "mature"]
            rows = []
            for role, status_dist in matrix.items():
                row = {"역할": role}
                for st_key in _STATUS_ORDER:
                    row[st_key] = status_dist.get(st_key, 0)
                rows.append(row)
            df_matrix = pd.DataFrame(rows)
            st.dataframe(df_matrix, use_container_width=True, hide_index=True)
        else:
            st.info("다락방 멤버 데이터가 없습니다.")
