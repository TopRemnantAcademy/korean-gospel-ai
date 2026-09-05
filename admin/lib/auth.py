"""비밀번호 게이트 (APP_PASSWORD env 설정 시에만 동작).

근본 해결 (2026-07-24):
- 로그인 폼은 반드시 `st.form` + `st.form_submit_button` 로 구성한다.
  일반 `st.button` 을 `if not auth_ok:` 조건 블록 안에 넣으면, Streamlit 위젯 트리가
  session_state 에 따라 바뀌면서 클릭 rerun 에서 버튼이 False 를 반환하는 발판이 있어
  "로그인 버튼을 눌러도 아무 일도 안 일어나는" 증상이 발생한다. (AppTest 로는 재현 안 돼
  브라우저에서만 나타나는 버그였음 — 실제 브라우저로 검증해야 함.)
- 인증 상태는 (1) st.session_state (현재 탭 세션) + (2) URL 쿼리 파라미터 `?a=<토큰>`
  (F5 후에도 로그인 유지) 로 보관.
  ※ 과거에 쓰던 extra_streamlit_components.CookieManager 는 컴포넌트가 "마운트 시점에만"
  쿠키를 읽어 Python 으로 보고하므로, F5 직후 비동기 복원이 불안정(간헐적 실패)했다.
    그래서 동기적이고 브라우저가 리로드 시 URL 을 그대로 보존하는 st.query_params 를 쓴다.
- 토큰은 APP_PASSWORD 기반 HMAC 해시라 URL 에 비밀번호가 노출되지 않고,
  비밀번호를 바꾸면 토큰도 바뀌어 기존 URL 이 자동 무효화된다.
- 인증 성공 시 `st.rerun()` 로 본문을 렌더(폼 제출은 자동 rerun 아님).
"""
from __future__ import annotations

import hmac
import os
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


_TOKEN_PARAM = "a"
_TOKEN_LEN = 32


def _expected_token(app_password: str) -> str:
    return hmac.new(
        b"kg_admin_gate", app_password.encode("utf-8"), "sha256"
    ).hexdigest()[:_TOKEN_LEN]


# 미인증 시 네이티브 페이지 내비게이션(왼쪽 패널)을 숨겨
# 내부 페이지 목록이 익명 사용자에게 노출되지 않도록 한다.
# 인증 후에는 이 CSS를 주입하지 않으므로 내비게이션이 정상 노출된다.
_HIDE_NAV_CSS = """
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
"""


def gate(app_password: str) -> None:
    # DD-2: KRAI.com 공개 모드에서는 관리자 페이지 직접 접근도 차단.
    # 운영자 허브(8502)는 이 env 를 설정하지 않아(또는 false) 정상 동작한다.
    if os.getenv("KRAI_PUBLIC_MODE", "").lower() == "true":
        st.error("이 페이지는 접근할 수 없습니다.")
        st.stop()
        return
    if not app_password or app_password == "change-me":
        st.error(
            "보안 위험: 관리자 비밀번호가 설정되지 않았거나 기본값('change-me')입니다. "
            ".env 파일에 올바른 APP_PASSWORD를 설정하세요."
        )
        st.stop()
        return

    expected = _expected_token(app_password)

    # 1) URL 쿼리 파라미터 토큰으로 인증 복원 (F5/새 탭에서도 유지 — 동기적이라 안정적).
    #    st.session_state 는 같은 탭에서 F5 시 보존되지만, 새 탭/세션 만료 시 사라지므로
    #    URL 토큰으로 보강한다.
    if not st.session_state.get("auth_ok"):
        token = st.query_params.get(_TOKEN_PARAM)
        if hmac.compare_digest(str(token or ""), expected):
            st.session_state.auth_ok = True

    # 2) 인증됨 → 본문 직접 렌더 (nav 정상 노출). 게이트 종료.
    if st.session_state.get("auth_ok"):
        # F5/새 탭 복원 후에도 URL 토큰이 없으면 보강 (idempotent — 한 번만 세팅되어 수렴).
        if st.query_params.get(_TOKEN_PARAM) != expected:
            st.query_params[_TOKEN_PARAM] = expected
        return

    # 3) 미인증 → 로그인 폼 (st.form 필수 — 조건 블록 안 일반 버튼은 클릭이 누락됨).
    st.markdown(_HIDE_NAV_CSS, unsafe_allow_html=True)
    st.title("🔐 관리자 로그인")
    st.caption("관리 콘솔에 접근하려면 비밀번호를 입력하세요.")
    with st.form("admin_login", border=False):
        pw_val = st.text_input("비밀번호", type="password", key="login_pw")
        submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
    if submitted:
        if hmac.compare_digest(pw_val, app_password):
            st.session_state.auth_ok = True
            st.query_params[_TOKEN_PARAM] = expected  # F5 후 유지용 토큰 (URL 에 기록)
            st.rerun()  # 인증 분기로 즉시 진입 (st.stop() 대신 rerun — 토큰 기록 후 재실행)
        else:
            st.error("❌ 비밀번호가 올바르지 않습니다.")
    st.stop()


def logout() -> None:
    """로그아웃: session_state 와 URL 토큰을 모두 제거한다."""
    st.session_state.auth_ok = False
    st.session_state.admin_auth_ok = False  # 통합 앱 호환
    st.session_state.admin_mode = False      # 통합 앱 호환 — 채팅으로 복귀
    # del 대신 clear() 사용: 이 버전 Streamlit 에서 del 은 URL(address bar) 갱신이
    # 누락되어 F5 시 토큰이 남아 재로그인되는 버그가 있음. clear() 는 URL 에서 ?a= 를 확실히 제거.
    try:
        st.query_params.clear()
    except Exception:
        try:
            st.query_params[_TOKEN_PARAM] = ""
        except Exception:
            pass
