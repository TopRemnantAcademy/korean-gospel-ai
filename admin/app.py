"""Admin Hub - 운영 허브 (홈)."""
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

from admin.lib.api_client import get_health, list_documents, get_collections
from admin.lib.auth import gate

APP_PASSWORD = os.getenv("APP_PASSWORD", "")

st.set_page_config(
    page_title="한국어 복음 AI",
    page_icon="✝",
    layout="wide",
    initial_sidebar_state="expanded",
)
gate(APP_PASSWORD)

# ===== 사이드바 =====
with st.sidebar:
    st.title("✝ 한국어 복음 AI")
    st.caption("운영 콘솔")

    health = get_health()
    if health:
        st.success("🟢 시스템 정상")
        with st.expander("기술 정보"):
            st.caption(f"LLM: {health.get('provider')}")
            st.caption(f"임베딩: {health.get('embedder')}")
            st.caption(f"DB: {health.get('qdrant_url')}")
    else:
        st.error("🔴 API 연결 실패")
        st.caption("Gospel API 검정창 확인")

    st.divider()
    st.markdown(
        "**페이지 안내**\n\n"
        "📚 **Library** — 자료 목록·공개·아카이브\n\n"
        "📥 **Upload** — 새 자료 올리기\n\n"
        "🔎 **Search** — 질문하고 답 받기\n\n"
        "📊 **Status** — 자료/인덱스 통계, 평가 실행\n\n"
        "💭 **대화기록** — 모든 Q/A 기록\n\n"
        "📝 **프롬프트** — AI 어조 편집\n\n"
        "🏷 **분류관리** — 태그/시리즈/화자 통계"
    )

    if APP_PASSWORD and st.button("로그아웃", use_container_width=True, key="logout_btn"):
        st.session_state.auth_ok = False
        st.rerun()


# ===== 본문 =====
st.title("운영 허브")

if not health:
    st.error("⚠ API 서버에 연결할 수 없습니다.")
    st.markdown(
        "**확인할 것:**\n"
        "1. 검정창 'Gospel API'가 열려있는지\n"
        "2. 5~10초 대기 후 새로고침\n"
        "3. 그래도 안 되면 `DIAGNOSE.bat` 실행"
    )
    st.stop()

# 데이터 로드
docs = list_documents() or []
cols_info = (get_collections() or {}).get("collections", [])
total_chunks = sum(c.get("points_count", 0) or 0 for c in cols_info)
drafts = [d for d in docs if d.get("latest_state") == "draft"]
published = [d for d in docs if (d.get("published_version") or 0) > 0]

# ===== 첫 사용 안내 (자료 없을 때) =====
if not docs:
    st.info(
        "👋 **처음 오셨군요!** 아직 올린 자료가 없습니다.\n\n"
        "왼쪽 사이드바에서 다음 순서대로 진행하세요:\n\n"
        "1️⃣ **📥 Upload** → 첫 자료(PDF/TXT/DOCX) 올리기\n\n"
        "2️⃣ **📚 Library** → 자료 검토 후 **'검색에 공개하기'** 클릭\n\n"
        "3️⃣ **🔎 Search** → 한국어로 질문 → AI가 자료를 근거로 답변\n\n"
        "💡 각 버튼에 마우스를 올리면 기능 설명이 표시됩니다."
    )
    st.stop()

# ===== 지표 카드 =====
st.subheader("📊 한눈에 보기")
c1, c2, c3, c4 = st.columns(4)
c1.metric("올린 자료", len(docs), help="모든 상태 합계")
c2.metric("검색 공개된 자료", len(published), help="검색 결과에 등장 가능")
c3.metric("검토 대기", len(drafts), help="아직 공개 안 된 자료")
c4.metric("검색 청크", total_chunks, help="검색 가능한 텍스트 조각")

st.divider()

# ===== 작업함 (할 일) =====
todo = [d for d in docs if d.get("latest_state") in ("draft", "validated")]

left, right = st.columns([1, 1])

with left:
    st.subheader("📌 오늘 할 일")
    if not todo:
        st.success("✅ 처리 대기 중인 자료가 없습니다. 깨끗합니다!")
        st.caption("새 자료를 올리려면 사이드바 → 📥 Upload")
    else:
        st.caption(f"공개를 기다리는 자료 {len(todo)}건")
        for d in todo[:8]:
            st.markdown(
                f"📄 **{d['title']}** · v{d['latest_version']} · `{d['latest_state']}`"
            )
        if len(todo) > 8:
            st.caption(f"그리고 {len(todo) - 8}건 더... → 📚 Library 페이지")
        st.info("👉 왼쪽 사이드바에서 **📚 Library** 페이지로 가서 공개 처리하세요.")

with right:
    st.subheader("🟢 검색 가능한 자료")
    if not published:
        st.warning(
            "아직 검색 공개된 자료가 없습니다.\n\n"
            "📚 Library에서 자료를 열고 **'검색에 공개하기'** 버튼을 눌러야 "
            "🔎 Search 페이지에서 답변에 등장합니다."
        )
    else:
        for d in published[:8]:
            st.markdown(
                f"✅ **{d['title']}** · v{d.get('published_version') or '?'}"
            )
        if len(published) > 8:
            st.caption(f"그리고 {len(published) - 8}건 더...")
        st.success(f"👉 **🔎 Search** 페이지에서 이 자료들을 근거로 답을 받으실 수 있어요.")
