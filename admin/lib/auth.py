"""비밀번호 게이트 (APP_PASSWORD env 설정 시에만)."""
from __future__ import annotations

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
# admin/pages/* 면 두 단계 위로, admin/* 면 한 단계 위로
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent  # admin -> project root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


import streamlit as st


def gate(app_password: str) -> None:
    if not app_password:
        return
    if st.session_state.get("auth_ok"):
        return
    st.title("Login")
    pw = st.text_input("Password", type="password", key="login_pw")
    if st.button("Enter", type="primary", key="login_btn"):
        if pw == app_password:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()
