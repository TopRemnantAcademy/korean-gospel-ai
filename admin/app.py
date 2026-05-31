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
import time
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    get_health, check_backend_health, list_documents,
    get_collections, get_error_stats, API_BASE,
)
from admin.lib.auth import gate

APP_PASSWORD = os.getenv("APP_PASSWORD", "")

st.set_page_config(
    page_title="한국어 복음 AI",
    page_icon="✝",
    layout="wide",
    initial_sidebar_state="expanded",
)
gate(APP_PASSWORD)

# Streamlit 기본 UI 요소 숨김 (Deploy 버튼, 3점 메뉴)
st.markdown("""
<style>
    .stDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    [data-testid="stToolbar"] { display: none !important; }
    footer { visibility: hidden !important; }
</style>
""", unsafe_allow_html=True)


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
        st.caption(f"서버: `{API_BASE}`")

    # 에러 뱃지
    if health:
        _err_stats = get_error_stats()
        if _err_stats:
            _e1h = _err_stats.get("errors_1h", 0)
            _c1h = _err_stats.get("critical_1h", 0)
            _s24h = _err_stats.get("slow_24h", 0) + _err_stats.get("slow_critical_24h", 0)
            if _e1h + _c1h > 0:
                st.error(f"🚨 최근 1h 에러 **{_e1h + _c1h}건** → 에러 모니터링 확인")
            elif _s24h > 0:
                st.warning(f"🐢 최근 24h 슬로우 **{_s24h}건**")
            else:
                st.caption("🚨 에러: 없음")

    st.divider()
    if APP_PASSWORD and st.button("로그아웃", use_container_width=True, key="logout_btn"):
        st.session_state.auth_ok = False
        st.rerun()


# ===== 본문 =====
st.title("운영 허브")

# ── 1) API 연결 상태 배너 (항상 최상단) ──────────────────────────────────────
t0 = time.time()
_hc = check_backend_health()
_latency = _hc.get("latency_ms", 0)

if _hc["ok"]:
    _hdata = _hc.get("data") or {}
    _provider = _hdata.get("provider", "?")
    _embedder = _hdata.get("embedder", "?")
    st.success(
        f"✅ **백엔드 연결됨** — `{API_BASE}` | 응답 {_latency}ms | "
        f"LLM: `{_provider}` | 임베딩: `{_embedder}`"
    )
else:
    _err_type = _hc.get("error_type", "unknown")
    _err_msg  = _hc.get("message", "")
    if _err_type == "timeout":
        st.error(
            f"⏱ **서버 응답 없음** — `{API_BASE}` ({_latency}ms 초과)  \n"
            "서버가 hang 상태일 수 있어요. 터미널에서 재시작하세요."
        )
        st.code(
            "uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload",
            language="bash",
        )
    elif _err_type == "connection":
        st.error(
            f"🔌 **서버 미실행** — `{API_BASE}` 에 연결할 수 없어요.  \n"
            "터미널에서 서버를 시작하세요."
        )
        st.code(
            "uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload",
            language="bash",
        )
    else:
        st.error(f"🔴 **백엔드 오류** — {_err_msg}")
    st.stop()   # 서버 없으면 아래 내용 로드 불필요

# ── 2) 에러 현황 배너 ─────────────────────────────────────────────────────────
_err_stats = get_error_stats() or {}
_e1h  = _err_stats.get("errors_1h", 0)
_c1h  = _err_stats.get("critical_1h", 0)
_s24h = _err_stats.get("slow_24h", 0) + _err_stats.get("slow_critical_24h", 0)

if _c1h > 0:
    st.error(f"🚨 최근 1시간 CRITICAL **{_c1h}건** + ERROR **{_e1h}건** — [📊 Status] 페이지에서 확인")
elif _e1h > 0:
    st.warning(f"⚠️ 최근 1시간 에러 **{_e1h}건** — [📊 Status] 페이지에서 확인")
elif _s24h > 0:
    st.info(f"🐢 최근 24시간 슬로우 리퀘스트 **{_s24h}건**")

# ── 3) 지표 카드 ─────────────────────────────────────────────────────────────
docs = list_documents() or []
cols_info = (get_collections() or {}).get("collections", [])
total_chunks = sum(c.get("points_count", 0) or 0 for c in cols_info)
drafts    = [d for d in docs if d.get("latest_state") == "draft"]
published = [d for d in docs if (d.get("published_version") or 0) > 0]

st.subheader("📊 한눈에 보기")
c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 자료", len(docs))
c2.metric("검색 공개됨", len(published))
c3.metric("검토 대기", len(drafts))
c4.metric("검색 청크", total_chunks)

st.divider()

# ── 4) 할 일 + 공개 자료 ─────────────────────────────────────────────────────
todo = [d for d in docs if d.get("latest_state") in ("draft", "validated")]
left, right = st.columns([1, 1])

with left:
    st.subheader("📌 오늘 할 일")
    if not todo:
        if not docs:
            st.info(
                "📥 아직 올린 자료가 없어요.  \n"
                "사이드바 **📥 Upload** 에서 첫 자료를 올려보세요."
            )
        else:
            st.success("✅ 처리 대기 중인 자료 없음")
            st.caption("새 자료 → 사이드바 📥 Upload")
    else:
        st.caption(f"공개 대기 중인 자료 {len(todo)}건")
        for d in todo[:8]:
            st.markdown(f"📄 **{d['title']}** · v{d['latest_version']} · `{d['latest_state']}`")
        if len(todo) > 8:
            st.caption(f"그리고 {len(todo) - 8}건 더... → 📚 Library")
        st.info("👉 **📚 Library** 에서 검증 후 공개하세요.")

with right:
    st.subheader("🟢 검색 가능한 자료")
    if not published:
        st.warning(
            "아직 공개된 자료가 없어요.  \n"
            "📚 Library → 자료 선택 → **'검색에 공개하기'** 버튼"
        )
    else:
        for d in published[:8]:
            st.markdown(f"✅ **{d['title']}** · v{d.get('published_version') or '?'}")
        if len(published) > 8:
            st.caption(f"그리고 {len(published) - 8}건 더...")
        st.success(f"👉 **🔎 Search** 에서 이 자료들로 답변을 받아보세요.")
