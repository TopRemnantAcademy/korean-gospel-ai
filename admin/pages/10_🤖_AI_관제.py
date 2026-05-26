"""AI 관제 - 자연어 기반 백엔드 제어판."""
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
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import agent_chat
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="AI 관제 (Agent)", page_icon="🤖", layout="wide")
st.title("🤖 AI 데이터 관제탑 (Agentic Admin)")
st.caption("자연어로 명령하여 백엔드 데이터를 조회하거나 일괄 수정할 수 있습니다.")

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create AI Agent Admin UI (Phase 5)
# Reason: 자연어로 시스템을 통제하는 인터페이스 제공
# Status: COMPLETED
# =============================================================================

st.info("💡 **활용 예시**\n- '현재 등록된 신앙 단계 카테고리 목록을 알려줘.'\n- '우울함(depressed)을 느끼는 유저들의 신앙 단계를 새신자로 일괄 수정해줘.'\n- '신앙 단계에 [방황중] 이라는 카테고리를 새로 추가해줘.'")

if "agent_history" not in st.session_state:
    st.session_state.agent_history = []

for msg in st.session_state.agent_history:
    # 필터링: 내부 시스템 로그(도구 실행결과)는 히스토리 UI에서 숨김
    if msg["role"] == "user" and msg["content"].startswith("[SYSTEM:"):
        continue
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
        st.markdown(msg["content"])

if prompt := st.chat_input("명령을 입력하세요... (예: '우울함을 느끼는 유저들을 찾아줘')"):
    st.session_state.agent_history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
        
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("AI가 데이터를 분석하고 시스템 도구를 사용 중입니다..."):
            res = agent_chat(prompt, st.session_state.agent_history[:-1])
            if res and "answer" in res:
                ans = res["answer"]
                st.markdown(ans)
                st.session_state.agent_history.append({"role": "assistant", "content": ans})
                
                if "messages" in res and len(res["messages"]) > 1:
                    with st.expander("🛠 AI 내부 작업 로그 (Tool Use)"):
                        for m in res["messages"]:
                            if m["role"] == "user" and str(m["content"]).startswith("[SYSTEM:"):
                                st.code(m["content"], language="json")
                            elif m["role"] == "assistant":
                                st.text(f"[AI] {m['content']}")
                            
                            # 히스토리에 병합하여 다음 대화 시 문맥 유지
                            if m not in st.session_state.agent_history:
                                st.session_state.agent_history.append(m)
            else:
                st.error("AI 응답을 받지 못했습니다.")
