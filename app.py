"""통합 앱 — 채팅 UI + 관리 콘솔을 하나의 Streamlit 앱으로.

실행: streamlit run app.py --server.port 8501
포트 하나로 사용자 채팅 + 관리자 기능 모두 제공.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
QDRANT_URL   = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")

# ── 세션 초기화 ──────────────────────────────────────────────────────────────
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False
if "admin_auth_ok" not in st.session_state:
    st.session_state.admin_auth_ok = False


# ── 페이지 정의 ──────────────────────────────────────────────────────────────
chat_page = st.Page("user/app.py", title="복음 AI 채팅", icon="🌿", default=True)

# Admin 서브페이지들 (admin/pages/ 폴더 그대로 재사용)
admin_home   = st.Page("admin/app.py",                         title="운영 허브",   icon="🏠")
admin_lib    = st.Page("admin/pages/1_📚_Library.py",           title="자료실",      icon="📚")
admin_upload = st.Page("admin/pages/2_📥_Upload.py",            title="자료 업로드", icon="📥")
admin_search = st.Page("admin/pages/3_🔎_Search.py",            title="검색 테스트", icon="🔎")
admin_status = st.Page("admin/pages/4_📊_Status.py",            title="상태 모니터", icon="📊")
admin_conv   = st.Page("admin/pages/5_💭_대화기록.py",           title="대화 기록",   icon="💭")
admin_prompt = st.Page("admin/pages/6_📝_프롬프트.py",           title="프롬프트",    icon="📝")
admin_cat    = st.Page("admin/pages/7_🏷_분류관리.py",           title="분류 관리",   icon="🏷")
admin_people = st.Page("admin/pages/9_👥_사람.py",               title="사람",        icon="👥")
admin_config = st.Page("admin/pages/10_⚙️_설정.py",              title="설정",        icon="⚙️")
admin_gloss  = st.Page("admin/pages/14_📚_용어집.py",            title="용어집",      icon="📖")
admin_flow   = st.Page("admin/pages/15_📥_자료흐름.py",          title="자료 흐름",   icon="🔄")


def _is_admin() -> bool:
    """관리자 모드 활성화 여부."""
    if not APP_PASSWORD:
        return st.session_state.admin_mode
    return st.session_state.admin_mode and st.session_state.admin_auth_ok


def _admin_login_ui():
    """관리자 비밀번호 입력 UI."""
    st.markdown("### 관리자 인증")
    pw = st.text_input("비밀번호", type="password", key="admin_pw_input",
                       placeholder="관리자 비밀번호를 입력하세요")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("확인", type="primary", key="admin_pw_btn"):
            if pw == APP_PASSWORD:
                st.session_state.admin_auth_ok = True
                st.session_state.auth_ok = True   # admin/app.py 의 gate() 호환
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    with col2:
        if st.button("취소", key="admin_cancel_btn"):
            st.session_state.admin_mode = False
            st.rerun()


# ── 사이드바 — 관리자 토글 버튼 ──────────────────────────────────────────────
# (각 페이지 앱이 자체 사이드바를 갖지만,
#  st.navigation 사이드바 최하단에 모드 전환 버튼을 삽입)
with st.sidebar:
    st.markdown(
        "<div style='position:fixed; bottom:1.5rem; left:0; width:inherit; padding:0 1rem;'>",
        unsafe_allow_html=True,
    )
    if _is_admin():
        if st.button("👤 사용자 모드로", use_container_width=True, key="exit_admin_btn",
                     help="채팅 화면으로 돌아가기"):
            st.session_state.admin_mode = False
            st.session_state.admin_auth_ok = False
            st.session_state.auth_ok = False
            st.rerun()
        # Qdrant 대시보드 링크
        st.markdown(
            f"<div style='margin-top:0.5rem;text-align:center;"
            f"font-size:0.78rem;'>"
            f"<a href='{QDRANT_URL}/dashboard' target='_blank' "
            f"style='text-decoration:none;color:#888;'>⚡ Qdrant 대시보드</a></div>",
            unsafe_allow_html=True,
        )
    else:
        if st.button("🔧 관리자 모드", use_container_width=True, key="enter_admin_btn",
                     help="운영 콘솔 열기"):
            st.session_state.admin_mode = True
            # 비밀번호 없으면 바로 진입
            if not APP_PASSWORD:
                st.session_state.admin_auth_ok = True
                st.session_state.auth_ok = True   # admin/app.py gate() 호환
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ── 라우팅 ────────────────────────────────────────────────────────────────────
if not st.session_state.admin_mode:
    # 사용자 모드 — 채팅 페이지만
    pg = st.navigation([chat_page], position="hidden")
    pg.run()

elif APP_PASSWORD and not st.session_state.admin_auth_ok:
    # 비밀번호 입력 대기
    st.set_page_config(
        page_title="관리자 인증",
        page_icon="🔒",
        layout="centered",
    )
    _admin_login_ui()

else:
    # 관리자 모드 — Admin 페이지 네비게이션
    pg = st.navigation(
        {
            "운영": [admin_home],
            "콘텐츠": [admin_lib, admin_upload, admin_search, admin_gloss, admin_flow],
            "모니터링": [admin_status, admin_conv],
            "시스템": [admin_prompt, admin_cat, admin_people, admin_config],
        }
    )
    pg.run()
