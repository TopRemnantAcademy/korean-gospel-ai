"""사람 - 사용자(구독자) 관리 관제탑."""
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

from admin.lib.api_client import list_subscribers, update_subscriber, get_categories
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="사람 관리", page_icon="👥", layout="wide")
st.title("👥 사람 관리 (관제탑)")
st.caption("사용자의 프로필, 신앙 단계, 상처를 파악하고 세밀하게 관리합니다.")

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create Admin UI for Subscriber management (C7)
# Reason: 사용자의 영적 여정 및 상태를 관제하고 수동으로 태그를 수정하기 위함
# Status: COMPLETED
# =============================================================================

if st.button("🔄 새로고침", key="sub_refresh"):
    st.rerun()

subs = list_subscribers()

if not subs:
    st.info("현재 등록된 사용자가 없습니다.")
    st.stop()

# 통계 차트 시각화
st.subheader("📊 사용자 분포 통계")
df = pd.DataFrame(subs)
col1, col2 = st.columns(2)
with col1:
    if "is_believer" in df.columns:
        st.write("신자 / 불신자 분포")
        st.bar_chart(df["is_believer"].value_counts())
with col2:
    if "is_darakbang_member" in df.columns:
        st.write("다락방 멤버 분포")
        st.bar_chart(df["is_darakbang_member"].value_counts())

st.divider()

# 사용자 목록 테이블
st.subheader("📋 사용자 프로필 상세 관리")
selected_sub_id = st.selectbox(
    "관리할 사용자를 선택하세요", 
    options=[s["subscriber_id"] for s in subs],
    format_func=lambda x: f"{x} (질문 횟수: {next((s['total_questions'] for s in subs if s['subscriber_id'] == x), 0)})"
)

if selected_sub_id:
    user = next(s for s in subs if s["subscriber_id"] == selected_sub_id)
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("### 사용자 정보 수정")
        with st.form("edit_user_form"):
            # DB에서 신앙 단계 목록 불러오기
            cats = get_categories("faith_stage")
            fs_options = [""] + [c["name"] for c in cats]
            
            current_fs = user.get("faith_stage") or ""
            # 만약 DB에 없는 예전 값이 있다면 추가해줌
            if current_fs and current_fs not in fs_options:
                fs_options.append(current_fs)
                
            fs_index = fs_options.index(current_fs) if current_fs in fs_options else 0
            
            faith_stage = st.selectbox("신앙 단계", fs_options, index=fs_index)
            emotional_state = st.text_input("감정 상태", value=user.get("emotional_state") or "")
            current_struggle = st.text_area("현재 상처/어려움", value=user.get("current_struggle") or "")
            is_believer = st.checkbox("명시적 신자 여부", value=user.get("is_believer", True))
            is_darakbang_member = st.checkbox("다락방 멤버 여부", value=user.get("is_darakbang_member", False))
            
            if st.form_submit_button("저장하기"):
                payload = {
                    "faith_stage": faith_stage if faith_stage else None,
                    "emotional_state": emotional_state,
                    "current_struggle": current_struggle,
                    "is_believer": is_believer,
                    "is_darakbang_member": is_darakbang_member
                }
                if update_subscriber(selected_sub_id, payload):
                    st.success("수정 완료! 새로고침 해주세요.")
                else:
                    st.error("수정 실패")
    
    with col2:
        st.write("### 최근 활동 정보")
        st.write(f"**첫 방문:** {user.get('first_seen_at')}")
        st.write(f"**최근 활동:** {user.get('last_active_at')}")
        st.write(f"**질문 횟수:** {user.get('total_questions')}")
        st.write(f"**진행된 온보딩 스텝:** {user.get('onboarding_step')}")
        
        st.info("💡 향후 업데이트: 이 유저의 프로필로 AI 반응을 테스트해볼 수 있는 '맞춤 프롬프트 시뮬레이터' 기능이 추가될 예정입니다.")
