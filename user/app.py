"""🌿 복음 AI — Google Gemini 스타일 채팅 UI

실행: streamlit run user/app.py --server.port 8502
"""
from __future__ import annotations

import sys, uuid
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

# ════════════════════════════════════════════════════════
# 테마 (라이트 / 다크)
# ════════════════════════════════════════════════════════
THEMES = {
    "light": {
        "app_bg":        "#FFFFFF",
        "sidebar_bg":    "#F0F4F9",
        "sidebar_hover": "#E3EAF4",
        "sidebar_text":  "#1F1F1F",
        "input_bg":      "#F0F4F9",
        "input_border":  "#C4C7C5",
        "input_focus":   "#1A7340",
        "text":          "#1F1F1F",
        "text_sub":      "#444746",
        "text_muted":    "#72777A",
        "divider":       "#E3E3E3",
        "user_msg_bg":   "#E8F5E9",
        "chip_bg":       "#F0F4F9",
        "chip_border":   "#C4C7C5",
        "chip_text":     "#1F1F1F",
        "accent":        "#1A7340",
        "btn_bg":        "#1A7340",
        "btn_text":      "#FFFFFF",
        "popup_bg":      "#FFFFFF",
        "dark":          False,
    },
    "dark": {
        "app_bg":        "#131314",
        "sidebar_bg":    "#1E1F20",
        "sidebar_hover": "#2A2B2C",
        "sidebar_text":  "#E3E3E3",
        "input_bg":      "#1E1F20",
        "input_border":  "#444746",
        "input_focus":   "#4CAF50",
        "text":          "#E3E3E3",
        "text_sub":      "#C4C7C5",
        "text_muted":    "#8E918F",
        "divider":       "#2A2B2C",
        "user_msg_bg":   "#1A2E1F",
        "chip_bg":       "#1E1F20",
        "chip_border":   "#444746",
        "chip_text":     "#E3E3E3",
        "accent":        "#4CAF50",
        "btn_bg":        "#2E7D32",
        "btn_text":      "#FFFFFF",
        "popup_bg":      "#2A2B2C",
        "dark":          True,
    },
}


def _css(t: dict) -> str:
    dark_extra = ""
    if t["dark"]:
        dark_extra = f"""
.stApp, .stApp p, .stApp span, .stApp li,
[data-testid="stMarkdownContainer"],
[data-testid="stChatMessageContent"] {{ color: {t['text']} !important; }}
textarea, [data-testid="stTextArea"] textarea {{
    background: {t['input_bg']} !important;
    color: {t['text']} !important;
}}
[data-testid="stTextInput"] input {{
    background: {t['input_bg']} !important;
    color: {t['text']} !important;
    border-color: {t['input_border']} !important;
}}
[data-testid="stRadio"] label {{ color: {t['text']} !important; }}
.stCaption {{ color: {t['text_muted']} !important; }}
[data-testid="stPopover"] {{ background: {t['popup_bg']} !important; }}
"""
    return f"""
<style>
/* ── Streamlit chrome 숨김 ──────────────────────────── */
#MainMenu, header[data-testid="stHeader"],
.stDeployButton, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"]
{{ display:none !important; visibility:hidden !important; }}
header[data-testid="stHeader"] {{ height:0 !important; }}

/* ── 전체 배경 ──────────────────────────────────────── */
.stApp {{ background:{t['app_bg']} !important; }}
[data-testid="stSidebar"] {{
    background:{t['sidebar_bg']} !important;
    border-right:1px solid {t['divider']} !important;
}}

/* ── 폰트 ──────────────────────────────────────────── */
html, body, [class*="css"] {{
    font-family: 'Google Sans', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
}}

/* ── 메인 컨테이너 ──────────────────────────────────── */
.block-container {{
    padding-top: 0 !important;
    padding-bottom: 0.5rem !important;
    max-width: 780px;
}}

/* ════════════════════════════════════════════════════
   사이드바 (Gemini 스타일)
════════════════════════════════════════════════════ */
[data-testid="stSidebarContent"] {{ padding: 1rem 0.75rem 1.5rem; }}

/* 새 채팅 버튼 */
.new-chat-btn button {{
    background: transparent !important;
    border: 1px solid {t['divider']} !important;
    border-radius: 24px !important;
    color: {t['sidebar_text']} !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    gap: 8px !important;
    transition: background 0.15s !important;
    margin-bottom: 0.5rem !important;
}}
.new-chat-btn button:hover {{
    background: {t['sidebar_hover']} !important;
}}

/* 히스토리 아이템 버튼 */
[data-testid="stSidebar"] .stButton button {{
    background: transparent !important;
    border: none !important;
    border-radius: 8px !important;
    color: {t['sidebar_text']} !important;
    font-size: 0.87rem !important;
    padding: 0.45rem 0.75rem !important;
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    margin-bottom: 1px !important;
    transition: background 0.15s !important;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background: {t['sidebar_hover']} !important;
}}

/* ════════════════════════════════════════════════════
   상단 바
════════════════════════════════════════════════════ */
.topbar {{
    display: flex;
    justify-content: flex-end;
    align-items: center;
    padding: 0.6rem 0 0.4rem 0;
    gap: 6px;
}}
.topbar [data-testid="stHorizontalBlock"] {{
    align-items: center !important;
    gap: 4px !important;
}}
.topbar [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    padding: 0 !important;
}}
/* 테마 토글 */
.topbar .stButton button {{
    height: 34px !important;
    padding: 0 0.8rem !important;
    border-radius: 20px !important;
    border: 1px solid {t['divider']} !important;
    background: transparent !important;
    color: {t['text_sub']} !important;
    font-size: 1rem !important;
    line-height: 1 !important;
}}
.topbar .stButton button:hover {{
    background: {t['sidebar_bg']} !important;
    color: {t['text']} !important;
}}
/* 로그인 팝오버 버튼 */
.topbar [data-testid="stPopover"] > button {{
    height: 34px !important;
    padding: 0 0.9rem !important;
    border-radius: 20px !important;
    border: 1px solid {t['divider']} !important;
    background: transparent !important;
    color: {t['text_sub']} !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
}}
.topbar [data-testid="stPopover"] > button:hover {{
    background: {t['sidebar_bg']} !important;
    color: {t['text']} !important;
}}

/* ════════════════════════════════════════════════════
   빈 화면 — Gemini 그리팅
════════════════════════════════════════════════════ */
.gemini-greeting {{
    text-align: center;
    padding: 3rem 1rem 2rem;
}}
.gemini-greeting .icon {{
    font-size: 3rem;
    margin-bottom: 0.5rem;
}}
.gemini-greeting h2 {{
    font-size: 2rem !important;
    font-weight: 400 !important;
    color: {t['text']} !important;
    margin: 0 0 0.4rem !important;
    letter-spacing: -0.01em;
    background: linear-gradient(135deg, {t['accent']} 0%, #2E7D32 50%, #558B2F 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.gemini-greeting .sub {{
    font-size: 1rem;
    color: {t['text_sub']};
    margin: 0;
}}

/* ════════════════════════════════════════════════════
   채팅 메시지 (Gemini 스타일)
════════════════════════════════════════════════════ */
.stChatMessage {{ font-size: 1.0rem; line-height: 1.8; }}
[data-testid="stChatMessageContent"] p {{ margin-bottom: 0.6em; }}

/* 사용자 메시지 — 오른쪽 정렬, 연한 배경 */
[data-testid="stChatMessage"][data-testid*="user"] {{
    flex-direction: row-reverse !important;
}}

/* AI 메시지 — 아이콘 왼쪽 */
[data-testid="stChatMessageAvatarAssistant"] {{
    background: {t['accent']} !important;
    border-radius: 50% !important;
}}

/* ════════════════════════════════════════════════════
   채팅 입력창 (Gemini 스타일 pill)
════════════════════════════════════════════════════ */
[data-testid="stChatInput"] {{
    border-radius: 24px !important;
    background: {t['input_bg']} !important;
    border: 1px solid {t['input_border']} !important;
    padding: 0.2rem 0.5rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}}
[data-testid="stChatInput"]:focus-within {{
    border-color: {t['input_focus']} !important;
    box-shadow: 0 1px 6px rgba(26,115,64,0.2) !important;
}}
[data-testid="stChatInputTextArea"] {{
    font-size: 1rem !important;
    background: transparent !important;
    color: {t['text']} !important;
}}

.stApp {{ transition: background 0.3s; }}
[data-testid="stSidebar"] {{ transition: background 0.3s; }}

{dark_extra}
</style>
"""


# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="복음 AI", page_icon="🌿",
    layout="centered", initial_sidebar_state="auto",
)

# ════════════════════════════════════════════════════════
# Session State 초기화
# ════════════════════════════════════════════════════════
for _k, _v in {
    "subscriber_id":     "anon_" + uuid.uuid4().hex[:12],
    "msgs":              [],
    "conversations":     [],
    "auth_token":        None,
    "user_display_name": None,
    "theme":             "light",
    "streaming_mode":    False,  # G-6: 스트리밍 모드 토글
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

_TK = "dark" if st.session_state.theme == "dark" else "light"
_T  = THEMES[_TK]
st.markdown(_css(_T), unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# 헬퍼 함수
# ════════════════════════════════════════════════════════
def _fetch_quota(sub_id: str) -> dict | None:
    try:
        with httpx.Client(timeout=4) as c:
            r = c.get(f"{API_BASE}/subscribers/me/quota", params={"user_id": sub_id})
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None

def _send_feedback(iid: str, val: int) -> bool:
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(f"{API_BASE}/feedback",
                       json={"interaction_id": iid, "value": val,
                             "user_id": st.session_state.subscriber_id})
        return r.status_code < 400
    except Exception:
        return False

def _save_history():
    if not st.session_state.msgs:
        return
    first = next((m["content"] for m in st.session_state.msgs if m["role"] == "user"), "")
    if not first:
        return
    st.session_state.conversations.insert(0, {
        "id":         uuid.uuid4().hex,
        "title":      first[:35] + ("…" if len(first) > 35 else ""),
        "messages":   list(st.session_state.msgs),
        "created_at": datetime.now().strftime("%m/%d %H:%M"),
    })

def _new_conv():
    _save_history()
    st.session_state.msgs = []
    st.rerun()

def _load_conv(conv: dict):
    _save_history()
    st.session_state.msgs = list(conv["messages"])
    st.session_state.conversations = [c for c in st.session_state.conversations if c["id"] != conv["id"]]
    st.rerun()


# ════════════════════════════════════════════════════════
# 사이드바 (Gemini 스타일)
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🌿")

    st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
    if st.button("✏️  새 대화", key="btn_new", use_container_width=True):
        _new_conv()
    st.markdown('</div>', unsafe_allow_html=True)

    convs = st.session_state.conversations
    if convs:
        st.markdown(
            f"<div style='font-size:0.75rem; color:{_T['text_muted']}; "
            f"padding:0.5rem 0.25rem 0.25rem; font-weight:500;'>최근 대화</div>",
            unsafe_allow_html=True,
        )
        for conv in convs[:30]:
            if st.button(conv["title"], key=f"h_{conv['id']}", use_container_width=True):
                _load_conv(conv)

    # 요약 버튼
    if len(st.session_state.msgs) >= 4:
        st.markdown("---")
        if st.button("📋 대화 요약", key="btn_sum", use_container_width=True):
            with st.spinner("요약 중…"):
                excerpt = "\n".join(
                    f"{'나' if m['role']=='user' else 'AI'}: {m['content'][:120]}"
                    for m in st.session_state.msgs[-8:]
                )
                try:
                    with httpx.Client(timeout=60) as c:
                        r = c.post(f"{API_BASE}/chat", json={
                            "query": f"다음 대화를 2~3줄로 핵심만 요약해 주세요:\n\n{excerpt}",
                            "history": [], "user_id": st.session_state.subscriber_id,
                        })
                    st.info(r.json().get("answer", "요약 실패") if r.status_code < 400 else "요약 실패")
                except Exception:
                    st.warning("요약 중 오류가 발생했어요.")

    # 쿼터
    st.markdown("---")
    quota = _fetch_quota(st.session_state.subscriber_id)
    if quota and not quota.get("unlimited"):
        tier = quota.get("subscription_tier", "guest")
        if tier == "guest":
            approx = max(0, quota.get("tokens_daily", 0) // 2000)
            if approx > 0:
                st.caption(f"오늘 남은 응답: **{approx}건**")
            else:
                st.warning("오늘 무료 응답이 모두 사용되었어요.")
        else:
            st.caption(f"월간 잔여: **{quota.get('tokens_monthly',0):,}** 토큰")

    st.markdown(
        "<div style='margin-top:auto;padding-top:2rem;font-size:0.72rem;color:#9E9E9E;"
        "line-height:1.7'>⚠️ 응급: 한국생명의전화 1588-9191</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════
# 메인 영역
# ════════════════════════════════════════════════════════

# ── 상단 바: 테마 + 로그인 ──────────────────────────────────────────────────
_logged_in = bool(st.session_state.auth_token)
_uname     = st.session_state.get("user_display_name") or ""
_is_dark   = (_TK == "dark")

st.markdown('<div class="topbar">', unsafe_allow_html=True)
_, c_theme, c_stream, c_login = st.columns([5.4, 0.6, 0.6, 1.8])

with c_theme:
    if st.button("☀️" if _is_dark else "🌙", key="btn_theme",
                 help="라이트" if _is_dark else "다크"):
        st.session_state.theme = "light" if _is_dark else "dark"
        st.rerun()

with c_stream:
    _sm = st.session_state.streaming_mode
    if st.button("🟢" if _sm else "⚪", key="btn_stream",
                 help="스트리밍 켜기" if not _sm else "스트리밍 끄기"):
        st.session_state.streaming_mode = not _sm
        st.rerun()

with c_login:
    _plabel = f"👤 {_uname}" if (_logged_in and _uname) else "👤 로그인"
    with st.popover(_plabel, use_container_width=True):
        if not _logged_in:
            _t = st.radio("", ["로그인", "가입하기"], horizontal=True,
                          key="auth_tab", label_visibility="collapsed")
            if _t == "로그인":
                _lem = st.text_input("이메일", key="li_em", placeholder="이메일",
                                     label_visibility="collapsed")
                _lpw = st.text_input("비밀번호", key="li_pw", type="password",
                                     placeholder="비밀번호", label_visibility="collapsed")
                if st.button("로그인", key="btn_login", use_container_width=True):
                    if _lem and _lpw:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/login",
                                           json={"email": _lem, "password": _lpw})
                            if r.status_code < 400:
                                d = r.json()
                                st.session_state.auth_token        = d["token"]
                                st.session_state.subscriber_id     = d["sub_id"]
                                st.session_state.user_display_name = _lem.split("@")[0]
                                st.rerun()
                            else:
                                st.error("이메일 또는 비밀번호가 올바르지 않습니다.")
                        except Exception as e:
                            st.error(f"오류: {e}")
            else:
                _em = st.text_input("이메일", key="su_em", placeholder="이메일",
                                    label_visibility="collapsed")
                _pw = st.text_input("비밀번호", key="su_pw", type="password",
                                    placeholder="비밀번호 (6자+)", label_visibility="collapsed")
                _nm = st.text_input("이름", key="su_nm", placeholder="이름 (선택)",
                                    label_visibility="collapsed")
                if st.button("✨ 가입하기", key="btn_signup", use_container_width=True):
                    if _em and _pw:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/signup", json={
                                    "email": _em, "password": _pw,
                                    "display_name": _nm or None,
                                    "guest_sub_id": st.session_state.subscriber_id,
                                })
                            if r.status_code < 400:
                                d = r.json()
                                st.session_state.auth_token        = d["token"]
                                st.session_state.subscriber_id     = d["sub_id"]
                                st.session_state.user_display_name = _nm or _em.split("@")[0]
                                st.success(f"🎁 {d.get('tokens_bonus',0):,}토큰 지급!")
                                st.rerun()
                            else:
                                st.error(r.json().get("detail", "가입 실패"))
                        except Exception as e:
                            st.error(f"오류: {e}")
                    else:
                        st.warning("이메일과 비밀번호를 입력해 주세요.")
        else:
            st.markdown(f"**{_uname}** 님")
            st.divider()
            if st.button("로그아웃", key="btn_logout", use_container_width=True):
                st.session_state.auth_token        = None
                st.session_state.user_display_name = None
                st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# 빈 화면 — Gemini 그리팅 + 예시 칩
# ════════════════════════════════════════════════════════
has_msgs = bool(st.session_state.msgs)

if not has_msgs:
    # 시간에 따른 인사
    _hour = datetime.now().hour
    _greet = "좋은 아침입니다" if _hour < 12 else ("좋은 오후입니다" if _hour < 18 else "좋은 저녁입니다")

    st.markdown(f"""
<div class="gemini-greeting">
    <div class="icon">🌿</div>
    <h2>무엇을 도와드릴까요?</h2>
    <p class="sub">{_greet}. 복음과 말씀에 대해 무엇이든 편하게 물어보세요.</p>
</div>
""", unsafe_allow_html=True)



# ════════════════════════════════════════════════════════
# 대화 메시지 표시
# ════════════════════════════════════════════════════════
for idx, m in enumerate(st.session_state.msgs):
    _av = "🌿" if m["role"] == "assistant" else "🙋"
    with st.chat_message(m["role"], avatar=_av):
        st.markdown(m["content"])
        iid = m.get("interaction_id")
        if m["role"] == "assistant" and iid and m.get("feedback") is None:
            c1, c2, _ = st.columns([1, 1, 7])
            with c1:
                if st.button("👍", key=f"up_{idx}", help="도움됐어요"):
                    if _send_feedback(iid, 1): m["feedback"] = 1; st.rerun()
            with c2:
                if st.button("👎", key=f"dn_{idx}", help="아쉬워요"):
                    if _send_feedback(iid, -1): m["feedback"] = -1; st.rerun()


# ════════════════════════════════════════════════════════
# 채팅 입력 (Gemini 스타일 pill — 항상 하단)
# ════════════════════════════════════════════════════════
_pending = st.session_state.pop("_pending", None)
_ph = "무엇이든 물어보세요…" if not has_msgs else "메시지 입력…"
prompt = _pending or st.chat_input(_ph)

if prompt:
    st.session_state.msgs.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar="🙋"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🌿"):
        full_text = ""
        sources: list = []
        interaction_id = None
        ph = st.empty()

        _streaming = st.session_state.get("streaming_mode", False)

        if _streaming:
            # G-6: 스트리밍 모드 ─────────────────────────────────────────────
            try:
                with httpx.stream(
                    "POST", f"{API_BASE}/chat/stream",
                    json={
                        "query": prompt,
                        "history": [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.msgs[:-1]
                        ],
                        "user_id": st.session_state.subscriber_id,
                    },
                    timeout=180,
                ) as r:
                    r.raise_for_status()
                    for chunk in r.iter_text():
                        if chunk.strip():
                            full_text += chunk
                            ph.markdown(full_text + "▌")
                    ph.markdown(full_text)
            except Exception as e:
                st.error(f"스트리밍 중 오류: {e}")
                full_text = "죄송합니다. 스트리밍 응답을 가져오지 못했어요."
                ph.markdown(full_text)
        else:
            # 기존 비스트리밍 모드 ─────────────────────────────────────────
            with st.spinner(""):
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
                        full_text      = data.get("answer", "")
                        sources        = data.get("sources", [])
                        interaction_id = data.get("interaction_id")
                        ph.markdown(full_text)
                    elif r.status_code == 429:
                        st.warning("오늘 무료 응답이 모두 사용되었어요. 오른쪽 상단 👤 에서 가입하시면 월 10만 토큰을 드려요. 🎁")
                        full_text = ""
                    else:
                        st.error("죄송합니다. 잠시 후 다시 시도해 주세요.")
                        full_text = ""
                except Exception:
                    st.error("연결에 문제가 있어요. 잠시 후 다시 시도해 주세요.")
                    full_text = ""

    if full_text:
        st.session_state.msgs.append({
            "role": "assistant", "content": full_text,
            "sources": sources, "interaction_id": interaction_id, "feedback": None,
        })
        st.rerun()
