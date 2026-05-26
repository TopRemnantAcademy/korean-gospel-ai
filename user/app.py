"""사용자용 단순 채팅 UI.

실행: streamlit run user/app.py --server.port 8502 --server.address 127.0.0.1
- 큰 글씨, 따뜻한 톤
- 익명 subscriber 자동 (session_state UUID)
- 출처/디버그는 작게 숨김 (옵션으로 표시)
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import httpx
import streamlit as st
from dotenv import load_dotenv
from invite_code import validate_invite_code, log_access, get_invite_code_stats

load_dotenv(_ROOT / ".env")


API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
REQUIRE_INVITE_CODE = os.getenv("REQUIRE_INVITE_CODE", "false").lower() == "true"


# ===== Page config (사용자 화면이라 더 따뜻하게) =====
st.set_page_config(
    page_title="복음 AI",
    page_icon="🌿",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# 큰 글씨 + 따뜻한 색감 CSS
st.markdown("""
<style>
.stChatMessage { font-size: 1.05rem; line-height: 1.7; }
.stChatMessage p { margin-bottom: 0.5em; }
h1, h2, h3 { color: #2d5016; }
.stButton button { border-radius: 24px; padding: 0.6rem 1.2rem; }
</style>
""", unsafe_allow_html=True)


# ===== 초대 코드 검증 (시범 운영 Tier 0.5) =====
if "invite_validated" not in st.session_state:
    st.session_state.invite_validated = False

if REQUIRE_INVITE_CODE and not st.session_state.invite_validated:
    st.title("🌿 복음 AI — 베타 시범")
    st.markdown(
        "<p style='color:#666; font-size:1.05rem;'>"
        "친구 초대로 베타 시험 중입니다. 초대 코드를 입력해주세요."
        "</p>",
        unsafe_allow_html=True,
    )
    
    with st.form("invite_code_form"):
        code = st.text_input(
            "🔑 초대 코드",
            placeholder="BETA-GOSPEL-XXXXXX",
            help="운영자로부터 받은 초대 코드를 입력하세요."
        )
        submitted = st.form_submit_button("확인", use_container_width=True)
    
    if submitted and code:
        try:
            # 클라이언트 IP 추출 (Cloudflare Tunnel 은 CF-Connecting-IP 헤더 사용)
            ip = st.session_state.get("client_ip", "unknown")
            
            result = validate_invite_code(code, ip_address=ip, user_agent="streamlit-user-app")
            
            if result['valid']:
                st.session_state.invite_validated = True
                st.session_state.invite_code = code
                log_access(ip_address=ip, code_used=code)
                st.success("✅ 코드가 확인되었습니다! 앱을 다시 로드합니다.")
                st.rerun()
            else:
                st.error(f"❌ {result['reason']}")
        except Exception as e:
            st.error(f"❌ 오류 발생: {str(e)}")
    
    st.stop()


# ===== 익명 subscriber ID =====
if "subscriber_id" not in st.session_state:
    st.session_state.subscriber_id = "anon_" + uuid.uuid4().hex[:12]


# ===== E-A3: 토큰 잔량 사이드바 표시 =====
def _fetch_quota(sub_id: str) -> dict | None:
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{API_BASE}/subscribers/me/quota", params={"user_id": sub_id})
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None

with st.sidebar:
    st.markdown("### 🌿 복음 AI")
    quota = _fetch_quota(st.session_state.get("subscriber_id", ""))
    if quota and not quota.get("unlimited"):
        tier = quota.get("subscription_tier", "guest")
        if tier == "guest":
            daily_rem = quota.get("tokens_daily", 0)
            approx_turns = max(0, daily_rem // 2000)
            st.caption(f"오늘 남은 무료 응답 약 **{approx_turns}건**")
            if approx_turns == 0:
                st.warning("오늘의 무료 풀이 다 되었어요.\n가입하시면 월 10만 토큰 + 선물 2만 토큰이 지급돼요.")
                if st.button("✨ 가입하기"):
                    st.info("준비 중입니다. 운영자에게 문의해주세요.")
        else:
            monthly_rem = quota.get("tokens_monthly", 0)
            bonus_rem = quota.get("tokens_bonus", 0)
            st.caption(f"월간 잔여: **{monthly_rem:,}** 토큰")
            if bonus_rem > 0:
                st.caption(f"보너스: **{bonus_rem:,}** 토큰")


# ===== 첫 화면 =====
st.title("🌿 복음 AI")
st.markdown(
    "<p style='color:#666; font-size:1.05rem;'>"
    "마음의 짐을 내려놓으세요. 성경 말씀을 근거로 함께 이야기 나눕니다."
    "</p>",
    unsafe_allow_html=True,
)

# ===== 대화 영역 =====
if "msgs" not in st.session_state:
    st.session_state.msgs = []

# 첫 진입 안내
if not st.session_state.msgs:
    st.markdown("##### 💭 어떤 도움이 필요하신가요?")
    starter_buttons = [
        ("💬 마음을 나누고 싶어요", "마음이 무겁고 힘듭니다. 어떻게 해야 할까요?"),
        ("📖 말씀이 듣고 싶어요", "오늘 저에게 위로가 될 말씀을 들려주세요."),
        ("🙏 기도가 필요해요", "지금 기도가 필요한 마음입니다. 어떻게 기도하면 좋을까요?"),
    ]
    cols = st.columns(3)
    for i, (label, q) in enumerate(starter_buttons):
        with cols[i]:
            if st.button(label, key=f"start_{i}", use_container_width=True):
                st.session_state._pending = q
                st.rerun()

def _send_feedback(interaction_id: str, value: int) -> bool:
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{API_BASE}/feedback", json={
                "interaction_id": interaction_id,
                "value": value,
                "user_id": st.session_state.subscriber_id,
            })
        return r.status_code < 400
    except Exception:
        return False


# 기존 대화 표시
for idx, m in enumerate(st.session_state.msgs):
    with st.chat_message(m["role"], avatar="🌿" if m["role"] == "assistant" else "🙋"):
        st.markdown(m["content"])
        if m.get("sources") and st.session_state.get("show_sources", False):
            with st.expander(f"📎 참고한 말씀 ({len(m['sources'])}개)"):
                for j, s in enumerate(m["sources"], 1):
                    title = s.get("metadata", {}).get("title", "?")
                    st.markdown(f"**{j}. {title}**\n\n> {s['text'][:200]}...")
        iid = m.get("interaction_id")
        if m["role"] == "assistant" and iid and m.get("feedback") is None:
            fb1, fb2, _ = st.columns([1, 1, 4])
            with fb1:
                if st.button("👍 도움됐어요", key=f"fb_up_{idx}"):
                    if _send_feedback(iid, 1):
                        m["feedback"] = 1
                        st.rerun()
            with fb2:
                if st.button("👎 아쉬워요", key=f"fb_dn_{idx}"):
                    if _send_feedback(iid, -1):
                        m["feedback"] = -1
                        st.rerun()


# 입력
pending = st.session_state.pop("_pending", None)
prompt = pending or st.chat_input("마음에 있는 질문을 자유롭게...")

if prompt:
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🙋"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🌿"):
        full_text = ""
        sources = []
        interaction_id = None
        placeholder = st.empty()
        with st.spinner("말씀을 찾고 있습니다…"):
            try:
                with httpx.Client(timeout=180) as c:
                    r = c.post(f"{API_BASE}/chat", json={
                        "query": prompt,
                        "history": [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.msgs[:-1]
                        ],
                        "user_id": st.session_state.subscriber_id,
                    })
                if r.status_code < 400:
                    data = r.json()
                    full_text = data.get("answer", "")
                    sources = data.get("sources", [])
                    interaction_id = data.get("interaction_id")
                    placeholder.markdown(full_text)
                else:
                    st.error("죄송합니다. 잠시 후 다시 시도해 주세요.")
            except Exception:
                st.error("죄송합니다. 잠시 후 다시 시도해 주세요.")

        if full_text:
            st.session_state.msgs.append({
                "role": "assistant",
                "content": full_text,
                "sources": sources,
                "interaction_id": interaction_id,
                "feedback": None,
            })
            st.rerun()


# ===== 작은 옵션 (하단) =====
with st.expander("⚙ 설정"):
    st.checkbox("참고 자료 보기", key="show_sources", value=False)
    if st.button("🗑 대화 새로 시작"):
        st.session_state.msgs = []
        st.rerun()
    st.caption(f"세션 ID: {st.session_state.subscriber_id}")
    st.caption("⚠ 응급 상황은 한국생명의전화 1588-9191 / 정신건강 1577-0199")


# ===== E-C: 가입/로그인 (사이드바 하단) =====
with st.sidebar:
    st.divider()
    _logged_in = st.session_state.get("auth_token") is not None
    if not _logged_in:
        with st.expander("✨ 가입하기 / 로그인"):
            _auth_tab = st.radio("", ["가입", "로그인"], horizontal=True, key="auth_tab")

            if _auth_tab == "가입":
                _email = st.text_input("이메일", key="signup_email", placeholder="your@email.com")
                _pw = st.text_input("비밀번호 (6자+)", key="signup_pw", type="password")
                _name = st.text_input("이름 (선택)", key="signup_name")
                if st.button("✨ 가입하기", key="btn_signup"):
                    if _email and _pw:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/signup", json={
                                    "email": _email,
                                    "password": _pw,
                                    "display_name": _name or None,
                                    "guest_sub_id": st.session_state.subscriber_id,
                                })
                            if r.status_code < 400:
                                data = r.json()
                                st.session_state.auth_token = data["token"]
                                st.session_state.subscriber_id = data["sub_id"]
                                st.success(
                                    f"환영합니다! 🎁 보너스 {data.get('tokens_bonus', 0):,}토큰이 지급되었어요."
                                )
                                st.rerun()
                            else:
                                st.error(r.json().get("detail", "가입 실패"))
                        except Exception as e:
                            st.error(f"오류: {e}")
                    else:
                        st.warning("이메일과 비밀번호를 입력하세요.")
            else:
                _login_email = st.text_input("이메일", key="login_email")
                _login_pw = st.text_input("비밀번호", key="login_pw", type="password")
                if st.button("로그인", key="btn_login"):
                    if _login_email and _login_pw:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/login", json={
                                    "email": _login_email,
                                    "password": _login_pw,
                                })
                            if r.status_code < 400:
                                data = r.json()
                                st.session_state.auth_token = data["token"]
                                st.session_state.subscriber_id = data["sub_id"]
                                st.success("로그인 성공!")
                                st.rerun()
                            else:
                                st.error("이메일 또는 비밀번호가 올바르지 않습니다.")
                        except Exception as e:
                            st.error(f"오류: {e}")
    else:
        if st.button("로그아웃", key="btn_logout"):
            st.session_state.auth_token = None
            st.rerun()
