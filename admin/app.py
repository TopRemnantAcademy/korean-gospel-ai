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

    get_collections, get_error_stats, get_services_health, API_BASE,

)

from admin.lib.auth import gate, logout

from admin.lib.mobile_swipe import inject_ipad_css_only



APP_PASSWORD = os.getenv("APP_PASSWORD", "")



gate(APP_PASSWORD)



# ══════════════════════════════════════════════════════════════════════════════

# Admin 전용 CSS — Premium Dark (접근성 강화)

# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""

<style>

    .stDeployButton { display: none !important; }

    #MainMenu { visibility: hidden !important; }

    [data-testid="stToolbar"] { display: none !important; }

    footer { visibility: hidden !important; }



    @import url('https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

    :root {

        --bg:#0C0A08; --surface:#14110D; --surface-2:#1B1611;

        --ink:#ECE5D6; --ink-sub:#B9AE9B; --ink-muted:#8A8071;

        --divider:#241E16; --gold:#C9A24B; --gold-soft:rgba(201,162,75,0.16);

        --emerald:#3FA46A; --err:#D9534F; --serif:'Gowun Batang','Nanum Myeongjo',serif;

    }

    html, body, [class*="css"] { font-family:'Noto Sans KR','Apple SD Gothic Neo',sans-serif; -webkit-font-smoothing:antialiased; }

    header[data-testid="stHeader"] { height: 0 !important; }



    /* 딥 다크 배경 */

    html, body, .stApp, .main { background: #0C0A08 !important; }

    .stApp { background: #0C0A08 !important; }

    [data-testid="stAppViewContainer"] { background: #0C0A08 !important; }

    [data-testid="stAppViewContainer"] > div,

    [data-testid="stMainBlockContainer"],

    section.main { background: #0C0A08 !important; }

    .block-container { padding-top: 1rem !important; max-width: 100% !important; }

    /* 주의: .stApp 에 position:relative 를 절대 주지 말 것 — Streamlit 은 .stApp 이
       position:absolute+inset 으로 전체 높이를 얻는 구조라, relative 로 덮으면 높이 0 붕괴 → 로그인 후 전체 백지 */
    .stApp { background: radial-gradient(1200px 480px at 50% -14%, var(--gold-soft), transparent 60%), var(--bg) !important; }

    .stApp::before { content:""; position:fixed; inset:0; pointer-events:none; z-index:0;

        background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");

        opacity:0.035; mix-blend-mode:screen; }

    .main { position:relative; z-index:1; }



    /* Border 제거 */

    [data-testid="stVerticalBlockBorderWrapper"],

    [data-testid="stBottomBlockContainer"],

    [data-testid="stBottomBlockContainer"] > *,

    [data-testid="stBottom"] { 

        border: none !important; 

        background: transparent !important;

        box-shadow: none !important;

    }

    div[data-testid="stVerticalBlock"] { background: transparent !important; }



    /* Metrics */

    .stMetric { background: transparent !important; }

    .stMetric label { color: #8A8071 !important; font-size: 0.8rem !important; font-weight: 500 !important; }

    .stMetric [data-testid="stMetricValue"] { color: #ECE5D6 !important; font-size: 1.7rem !important; font-weight: 600 !important; font-family: var(--serif); letter-spacing: -0.01em; }



    /* Text — WCAG AA 대비 (4.5:1 이상) */

    p, span, li, label { color: #B9AE9B !important; }

    .stCaption { color: #8A8071 !important; }

    h1, h2, h3, h4 { color: #ECE5D6 !important; font-family: var(--serif); letter-spacing: -0.01em; }



    /* Focus visible (접근성) */

    *:focus-visible {

        outline: 2px solid #C9A24B !important;

        outline-offset: 2px !important;

        border-radius: 4px !important;

    }

    button:focus-visible {

        outline: 2px solid #C9A24B !important;

        outline-offset: 3px !important;

    }



    /* Reduced motion */

    @media (prefers-reduced-motion: reduce) {

        *, *::before, *::after {

            animation-duration: 0.01ms !important;

            transition-duration: 0.01ms !important;

        }

    }



    /* Sidebar */

    [data-testid="stSidebar"] { 

        background: #100D0A !important; 

        border-right: 1px solid #241E16 !important; 

        position: relative !important;

        z-index: 10 !important;

    }

    [data-testid="stSidebar"] .stButton button {

        min-height: 36px !important;

        margin-bottom: 3px !important;

        line-height: 1.4 !important;

        border-radius: 8px !important;

        transition: background 0.2s ease;

        cursor: pointer !important;

    }

    [data-testid="stSidebar"] .stButton button:hover {

        background: #1B1611 !important;

    }



    /* Sidebar expander */

    [data-testid="stSidebar"] .stExpander { margin-bottom: 4px !important; }

    [data-testid="stSidebar"] .stExpander .stButton button {

        margin-top: 2px !important;

        margin-bottom: 2px !important;

    }



    /* Popover z-index */

    [data-testid="stSidebar"] [data-testid="stPopover"] {

        position: relative !important;

        z-index: 100 !important;

    }



    /* Status indicator cards (기능 상태) */

    .status-card {

        padding: 0.65rem 0.85rem;

        border-radius: 10px;

        border: 1px solid var(--divider);

        background: var(--surface-2);

        margin-bottom: 0.35rem;

        transition: border-color 0.2s ease;

    }

    .status-card.ok { border-left: 3px solid #3FA46A; }

    .status-card.err { border-left: 3px solid #D9534F; }



    /* Scrollbar */

    ::-webkit-scrollbar { width: 6px; }

    ::-webkit-scrollbar-track { background: transparent; }

    ::-webkit-scrollbar-thumb { background: #241E16; border-radius: 4px; transition: background 0.2s ease; }

    ::-webkit-scrollbar-thumb:hover { background: var(--gold); }



    /* XSS: 가로 오버플로우 방지 */

    html, body { overflow-x: hidden !important; }



    /* 다중 열 레이아웃 */

    [data-testid="column"] {

        min-width: 0 !important;

        overflow: hidden !important;

        text-overflow: ellipsis !important;

    }

    [data-testid="column"] .stButton button {

        white-space: nowrap !important;

        text-overflow: ellipsis !important;

    }



    /* Tabs */

    .stTabs button {

        white-space: nowrap !important;

        overflow: hidden !important;

        text-overflow: ellipsis !important;

        transition: color 0.2s ease;

    }

    .stTabs [aria-selected="true"] { color: var(--gold) !important; }



    /* Expander */

    .stExpander { border: 1px solid var(--divider) !important; border-radius: 12px !important; overflow: hidden; margin-bottom: 0.5rem; }

    .stExpander [data-testid="column"] {

        padding: 0 4px !important;

    }

    .stExpander details summary {

        min-height: 36px !important;

        border-radius: 12px !important;

    }



    /* Buttons */

    .stButton button {

        transition: all 0.2s ease !important;

        cursor: pointer !important;

        border-radius: 10px !important;

    }

    .stButton button:hover { border-color: var(--gold) !important; }



    /* Input fields */

    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {

        border-radius: 10px !important;

        border-color: var(--divider) !important;

        transition: all 0.2s ease !important;

    }

    [data-testid="stTextInput"] input:focus,

    [data-testid="stTextArea"] textarea:focus {

        border-color: var(--gold) !important;

        box-shadow: 0 0 0 3px var(--gold-soft) !important;

    }



    /* Responsive */

    @media (max-width: 480px) {

        .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }

        .stMetric [data-testid="stMetricValue"] { font-size: 1.2rem !important; }

        [data-testid="stSidebar"] .stButton button { 

            font-size: 0.82rem !important; 

            padding: 7px 10px !important;

            min-height: 32px !important;

        }

        [data-testid="stHorizontalBlock"] {

            flex-wrap: wrap !important;

            gap: 6px !important;

        }

        [data-testid="stHorizontalBlock"] > [data-testid="column"] {

            flex: 1 1 auto !important;

            min-width: 120px !important;

        }

    }



    /* ── iPad 전용 (768px ~ 1194px) ──────────────────────────────── */

    @media (min-width: 481px) and (max-width: 1194px) {

        .block-container {

            padding-left: 1.5rem !important;

            padding-right: 1.5rem !important;

            padding-bottom: 3rem !important;

        }

        .stMetric [data-testid="stMetricValue"] { font-size: 1.35rem !important; }

        .stMetric label { font-size: 0.75rem !important; }



        [data-testid="stSidebar"] {

            min-width: 260px !important;

        }

        [data-testid="stSidebar"] .stButton button {

            font-size: 0.84rem !important;

            padding: 9px 12px !important;

            min-height: 44px !important;

            border-radius: 12px !important;

        }



        [data-testid="stHorizontalBlock"] {

            flex-wrap: wrap !important;

            gap: 8px !important;

        }

        [data-testid="stHorizontalBlock"] > [data-testid="column"] {

            flex: 1 1 180px !important;

            min-width: 150px !important;

        }



        .stTabs [data-baseweb="tab-list"] {

            overflow-x: auto !important;

            -webkit-overflow-scrolling: touch !important;

        }



        .stExpander details summary {

            min-height: 44px !important;

            padding: 10px 12px !important;

        }



        [data-testid="stDataFrame"] {

            overflow-x: auto !important;

            -webkit-overflow-scrolling: touch !important;

        }



        [data-testid="stTextInput"] input,

        [data-testid="stTextArea"] textarea {

            font-size: 16px !important;

        }



        [data-baseweb="select"] {

            min-height: 44px !important;

        }

    }

</style>

""", unsafe_allow_html=True)



# ── iPad Safari 터치 최적화 CSS ──────────────────────────────────────

inject_ipad_css_only()





# ===== 사이드바 =====

with st.sidebar:

    st.title("")

    st.caption("운영 콘솔")



    health = get_health()

    if health:

        st.success("🟢 시스템 정상")

        with st.expander("시스템 정보"):

            st.caption(f"LLM: `{health.get('provider', '?')}`")

            st.caption(f"임베딩: `{health.get('embedder', '?')}`")

            st.caption(f"DB: `{health.get('qdrant_url', '?')}`")

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

        logout()

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



# ── 2.5) 기능 상태 체크 ──────────────────────────────────────────────────────

_svcs = get_services_health()

if _svcs:

    st.subheader("⚙️ 기능 상태")

    cols = st.columns(3)

    svc_items = list(_svcs.get("services", {}).items())

    for idx, (svc_name, svc_info) in enumerate(svc_items):

        with cols[idx % 3]:

            ok = svc_info.get("ok", False)

            msg = svc_info.get("message", "")

            icon = "✅" if ok else "❌"

            # 길어지면 줄임표 처리

            if len(msg) > 15:

                msg = msg[:12] + "..."

            st.markdown(f"**{icon} {svc_name}**  \n`{msg}`")



    # 전체 상태가 degraded면 경고

    overall = _svcs.get("overall", "unknown")

    ok_count = _svcs.get("ok_count", 0)

    total_count = _svcs.get("total_count", 1)



    if overall == "degraded":

        st.warning(f"⚠️ {ok_count}/{total_count}개 기능 정상 — 일부 기능에 문제가 있을 수 있습니다")

    elif overall == "unavailable":

        st.error(f"🚨 {ok_count}/{total_count}개 기능 정상 — 심각한 문제입니다")

else:

    st.caption("⚙️ 기능 상태를 불러올 수 없습니다")



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

        st.success("👉 **🔎 Search** 에서 이 자료들로 답변을 받아보세요.")

