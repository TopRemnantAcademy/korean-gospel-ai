"""🌿  — Google Gemini 스타일 채팅 UI

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
st.set_page_config(page_title="", page_icon="🌿", layout="centered")
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

# ════════════════════════════════════════════════════════
# 테마 (라이트 / 다크)
# ════════════════════════════════════════════════════════
THEMES = {
    "light": {
        "bg":            "#FBF7F0",
        "surface":       "#FFFFFF",
        "surface_2":     "#FFFDF9",
        "sidebar_bg":    "#F4EDE2",
        "sidebar_hover": "#EAE0D0",
        "ink":           "#2A2118",
        "ink_sub":       "#574B3C",
        "ink_muted":     "#8A7B66",
        "divider":       "#E7DCCB",
        "primary":       "#1F4D3A",
        "primary_hover": "#163A2B",
        "primary_soft":  "rgba(31,77,58,0.10)",
        "gold":          "#B08642",
        "gold_soft":     "rgba(176,134,66,0.16)",
        "user_msg":      "#E7EEE6",
        "chip_bg":       "#FFFFFF",
        "chip_border":   "#DCCFB9",
        "btn_bg":        "#1F4D3A",
        "btn_text":      "#FBF7F0",
        "popup_bg":      "#FFFFFF",
        "danger_bg":     "#FBEDEA",
        "danger_ink":    "#9B2C2C",
        "danger_border": "#EFC9C0",
        "shadow_soft":   "0 1px 2px rgba(42,33,24,0.05), 0 10px 30px rgba(42,33,24,0.08)",
        "shadow_card":   "0 2px 6px rgba(42,33,24,0.06), 0 20px 50px rgba(42,33,24,0.10)",
        "dark":          False,
    },
    "dark": {
        "bg":            "#0C0A08",
        "surface":       "#15120E",
        "surface_2":     "#1B1712",
        "sidebar_bg":    "#100D0A",
        "sidebar_hover": "#1E1A14",
        "ink":           "#EFE9DD",
        "ink_sub":       "#C3B8A6",
        "ink_muted":     "#867862",
        "divider":       "#2A241C",
        "primary":       "#5FAE84",
        "primary_hover": "#7CC39C",
        "primary_soft":  "rgba(95,174,132,0.14)",
        "gold":          "#C9A24B",
        "gold_soft":     "rgba(201,162,75,0.18)",
        "user_msg":      "#1C2A22",
        "chip_bg":       "#1B1712",
        "chip_border":   "#2E271E",
        "btn_bg":        "#2E7D56",
        "btn_text":      "#FBF7F0",
        "popup_bg":      "#1A160F",
        "danger_bg":     "#2A1410",
        "danger_ink":    "#F0B4A8",
        "danger_border": "#5C2A22",
        "shadow_soft":   "0 1px 2px rgba(0,0,0,0.5), 0 12px 32px rgba(0,0,0,0.5)",
        "shadow_card":   "0 2px 8px rgba(0,0,0,0.55), 0 22px 54px rgba(0,0,0,0.6)",
        "dark":          True,
    },
}


def _css(t: dict) -> str:
    return f"""
<style>
/* ════════ Design tokens — Sacred Garden · Editorial Luxe ════════ */
:root {{
  --bg:{t['bg']}; --surface:{t['surface']}; --surface-2:{t['surface_2']};
  --sidebar-bg:{t['sidebar_bg']}; --sidebar-hover:{t['sidebar_hover']};
  --ink:{t['ink']}; --ink-sub:{t['ink_sub']}; --ink-muted:{t['ink_muted']};
  --divider:{t['divider']}; --primary:{t['primary']}; --primary-hover:{t['primary_hover']};
  --primary-soft:{t['primary_soft']}; --gold:{t['gold']}; --gold-soft:{t['gold_soft']};
  --user-msg:{t['user_msg']}; --chip-bg:{t['chip_bg']}; --chip-border:{t['chip_border']};
  --btn-bg:{t['btn_bg']}; --btn-text:{t['btn_text']}; --popup-bg:{t['popup_bg']};
  --danger-bg:{t['danger_bg']}; --danger-ink:{t['danger_ink']}; --danger-border:{t['danger_border']};
  --shadow-soft:{t['shadow_soft']}; --shadow-card:{t['shadow_card']};
  --radius:18px; --radius-sm:12px;
  --serif:'Gowun Batang','Nanum Myeongjo',serif;
  --sans:'Noto Sans KR','Apple SD Gothic Neo',sans-serif;
}}

/* ── Streamlit chrome 숨김 ──────────────────────────── */
#MainMenu, header[data-testid="stHeader"], .stDeployButton,
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"]
{{ display:none !important; visibility:hidden !important; }}
header[data-testid="stHeader"] {{ height:0 !important; }}

/* ── 폰트 ──────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@300;400;500;700&family=Cormorant+Garamond:wght@500;600&display=swap');
html, body, [class*="css"] {{
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
}}

/* ── 전체 배경: 따뜻한 종이 + 은은한 빛 ─────────────── */
.stApp {{
  background:
    radial-gradient(1100px 460px at 50% -12%, var(--primary-soft), transparent 62%),
    var(--bg) !important;
  position: relative;
}}
.stApp::before {{
  content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity:0.03; mix-blend-mode:multiply;
}}
.main, .block-container {{ position:relative; z-index:1; }}
.block-container {{ padding-top:0 !important; padding-bottom:0.5rem !important; max-width:780px; }}

/* ── 텍스트 컬러 ──────────────────────────────────── */
.stApp, .stApp p, .stApp span, .stApp li,
[data-testid="stMarkdownContainer"], [data-testid="stChatMessageContent"]
{{ color:var(--ink) !important; }}
.stCaption {{ color:var(--ink-muted) !important; }}
textarea, [data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input {{ color:var(--ink) !important; }}

/* ── 접근성: focus-visible (웹 표준) ───────────────── */
*:focus-visible {{ outline:2px solid var(--gold) !important; outline-offset:3px !important; border-radius:4px !important; }}
button:focus-visible {{ outline-offset:2px !important; }}

/* ── Reduced motion ───────────────────────────────── */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation-duration:0.01ms !important; transition-duration:0.01ms !important; }}
  .stApp, [data-testid="stSidebar"] {{ transition:none !important; }}
}}

/* ════════ 사이드바 ════════ */
[data-testid="stSidebar"] {{
  background:var(--sidebar-bg) !important;
  border-right:1px solid var(--divider) !important;
}}
[data-testid="stSidebarContent"] {{ padding:1.4rem 0.9rem 1.6rem; }}
.brand {{
  font-family:var(--serif); font-weight:700; font-size:1.3rem; color:var(--ink);
  letter-spacing:-0.01em; display:flex; align-items:center; gap:0.5rem;
  padding:0.2rem 0.4rem 1.1rem;
}}
.brand .leaf {{ font-size:1.35rem; filter:drop-shadow(0 3px 8px var(--primary-soft)); }}
.new-chat-btn button {{
  background:transparent !important; border:1px solid var(--divider) !important;
  border-radius:var(--radius-sm) !important; color:var(--ink) !important;
  font-size:0.9rem !important; font-weight:500 !important; padding:0.65rem 1rem !important;
  width:100% !important; text-align:left !important; justify-content:flex-start !important;
  gap:8px !important; transition:all 0.22s ease !important; margin-bottom:0.6rem; cursor:pointer !important;
}}
.new-chat-btn button:hover {{
  background:var(--sidebar-hover) !important; border-color:var(--gold); color:var(--primary) !important;
}}
[data-testid="stSidebar"] .stButton button {{
  background:transparent !important; border:none !important; border-radius:10px !important;
  color:var(--ink) !important; font-size:0.87rem !important; padding:0.5rem 0.75rem !important;
  width:100% !important; text-align:left !important; justify-content:flex-start !important;
  white-space:nowrap !important; overflow:hidden !important; text-overflow:ellipsis !important;
  margin-bottom:1px !important; transition:all 0.2s ease !important; cursor:pointer !important;
}}
[data-testid="stSidebar"] .stButton button:hover {{ background:var(--sidebar-hover) !important; }}
.side-section-label {{
  font-size:0.72rem; letter-spacing:0.08em; text-transform:uppercase;
  color:var(--ink-muted); padding:0.8rem 0.4rem 0.3rem; font-weight:600;
}}
.side-foot {{ margin-top:auto; padding-top:2rem; font-size:0.72rem; color:var(--ink-muted); line-height:1.7; opacity:0.8; }}

/* ════════ 상단 바 ════════ */
.topbar {{ display:flex; justify-content:flex-end; align-items:center; padding:0.7rem 0 0.5rem; gap:8px; }}
.topbar [data-testid="stHorizontalBlock"] > [data-testid="column"]
{{ display:flex !important; align-items:center !important; justify-content:flex-end; padding:0 !important; }}
.topbar .stButton button {{
  height:38px; min-width:38px; padding:0 !important; border-radius:50% !important;
  border:1px solid var(--divider) !important; background:transparent !important;
  color:var(--ink-sub) !important; font-size:1.05rem !important; line-height:1 !important;
  cursor:pointer !important; transition:all 0.25s ease !important;
}}
.topbar .stButton button:hover {{
  border-color:var(--gold) !important; color:var(--gold) !important;
  background:var(--gold-soft) !important; transform:translateY(-1px);
}}
.topbar [data-testid="stPopover"] > button {{
  height:38px !important; min-width:38px !important; padding:0 1.1rem !important;
  border-radius:19px !important; border:1px solid var(--divider) !important;
  background:transparent !important; color:var(--ink-sub) !important;
  font-size:0.85rem !important; font-weight:500 !important; white-space:nowrap !important;
  cursor:pointer !important; transition:all 0.25s ease !important;
}}
.topbar [data-testid="stPopover"] > button:hover {{
  border-color:var(--gold) !important; color:var(--ink) !important; background:var(--gold-soft) !important;
}}

/* ════════ 빈 화면 — 그리팅 ════════ */
.bible-greeting {{ text-align:center; padding:5rem 1.5rem 2.5rem; position:relative; }}
.bible-greeting .glyph {{
  font-size:3rem; display:inline-block; margin-bottom:1rem;
  animation:glyphIn 0.9s cubic-bezier(.2,.7,.2,1) both;
  filter:drop-shadow(0 6px 14px var(--primary-soft));
}}
.bible-greeting h1 {{
  font-family:var(--serif); font-weight:700; font-size:2.4rem; line-height:1.35;
  letter-spacing:-0.01em; color:var(--ink); margin:0 0 0.9rem;
  animation:riseIn 0.8s ease both 0.12s;
}}
.bible-greeting .lede {{
  font-size:1.05rem; line-height:1.8; color:var(--ink-sub); max-width:460px;
  margin:0 auto; animation:riseIn 0.8s ease both 0.24s;
}}
.bible-greeting .rule {{
  width:72px; height:1px; margin:1.7rem auto 0; position:relative;
  background:linear-gradient(90deg,transparent,var(--gold),transparent);
  animation:riseIn 0.8s ease both 0.36s;
}}
.bible-greeting .rule::after {{
  content:"✦"; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
  color:var(--gold); font-size:0.7rem; background:var(--bg); padding:0 7px;
}}
@keyframes glyphIn {{ from{{opacity:0; transform:translateY(-8px) scale(.92);}} to{{opacity:1; transform:none;}} }}
@keyframes riseIn {{ from{{opacity:0; transform:translateY(14px);}} to{{opacity:1; transform:none;}} }}

/* ════════ 채팅 메시지 ════════ */
.stChatMessage {{ font-size:1rem; line-height:1.85; gap:1rem; }}
[data-testid="stChatMessageContent"] p {{ margin-bottom:0.6em; }}
[data-testid="stChatMessage"][data-testid*="user"] {{ flex-direction:row-reverse !important; }}
[data-testid="stChatMessage"][data-testid*="assistant"] {{
  background:var(--surface) !important; border:1px solid var(--divider) !important;
  border-radius:var(--radius) !important; padding:0.2rem 0.5rem;
  box-shadow:var(--shadow-card) !important; margin-bottom:1.2rem !important;
}}
[data-testid="stChatMessageAvatarAssistant"] {{
  background:linear-gradient(140deg,var(--primary),var(--primary-hover)) !important;
  border-radius:50% !important; box-shadow:0 2px 10px var(--primary-soft) !important;
  outline:1px solid var(--gold-soft); outline-offset:2px;
}}
[data-testid="stChatMessageAvatarUser"] {{
  background:var(--surface-2) !important; border:1px solid var(--divider) !important;
  border-radius:50% !important;
}}

/* ════════ 입력창 pill ════════ */
[data-testid="stChatInput"] {{
  border-radius:26px !important; background:var(--surface) !important;
  border:1.5px solid var(--divider) !important; padding:0.35rem 0.6rem !important;
  box-shadow:var(--shadow-card) !important;
  transition:border-color 0.25s ease, box-shadow 0.25s ease !important;
}}
[data-testid="stChatInput"]:focus-within {{
  border-color:var(--primary) !important;
  box-shadow:0 0 0 4px var(--primary-soft), 0 10px 30px var(--primary-soft) !important;
}}
[data-testid="stChatInputTextArea"] {{ font-size:1rem !important; background:transparent !important; color:var(--ink) !important; }}
[data-testid="stChatInputTextArea"]::placeholder {{ color:var(--ink-muted) !important; opacity:0.7 !important; }}

/* ════════ 피드백 버튼 ════════ */
.feedback-btn-area button {{
  background:transparent !important; border:1px solid var(--divider) !important;
  border-radius:14px !important; padding:2px 10px !important; font-size:0.85rem !important;
  cursor:pointer !important; transition:all 0.2s ease !important; min-height:30px !important;
}}
.feedback-btn-area button:hover {{ border-color:var(--gold) !important; background:var(--gold-soft) !important; }}

/* ════════ 참고문헌 expander ════════ */
[data-testid="stExpander"] {{
  border:1px solid var(--divider) !important; border-radius:var(--radius-sm) !important;
  margin-top:0.6rem !important; background:transparent !important; overflow:hidden;
}}
[data-testid="stExpander"] summary {{ border-radius:var(--radius-sm) !important; }}

/* ════════ 로그인 팝오버 폼 ════════ */
.stPopover [data-testid="stTextInput"] label {{
  font-size:0.8rem !important; color:var(--ink-muted) !important; font-weight:500 !important; margin-bottom:2px !important;
}}
.stPopover [data-testid="stTextInput"] input {{
  border-radius:10px !important; border-color:var(--divider) !important;
  font-size:0.9rem !important; padding:0.55rem 0.8rem !important; background:var(--surface-2) !important;
  transition:all 0.2s ease !important;
}}
.stPopover [data-testid="stTextInput"] input:focus {{ border-color:var(--primary) !important; box-shadow:0 0 0 3px var(--primary-soft) !important; }}
.stPopover .stButton button {{ border-radius:10px !important; font-weight:500 !important; transition:all 0.2s ease !important; cursor:pointer !important; }}

/* ════════ 스크롤바 ════════ */
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:var(--divider); border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:var(--gold); }}

/* ════════ 글로벌 트랜지션 ════════ */
.stApp, [data-testid="stSidebar"] {{ transition:background 0.35s ease; }}
</style>
"""



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

# ✅ 패치 4: 첫 로드시 Ping + 개인화 Greeting 호출
def _call_ping_and_greeting():
    """✅ 패치 4: 첫 로드시 ping + greeting 호출하여 개인화."""
    try:
        headers = {}
        if st.session_state.auth_token:
            headers["Authorization"] = f"Bearer {st.session_state.auth_token}"
        with httpx.Client(timeout=5) as c:
            ping = c.get(f"{API_BASE}/chat/ping",
                         params={"user_id": st.session_state.subscriber_id},
                         headers=headers)
            if ping.status_code < 400:
                ping_data = ping.json()
                st.session_state["_ping_data"] = ping_data

                # 재방문 사용자면 greeting 호출
                if ping_data.get("is_returning"):
                    greet = c.get(f"{API_BASE}/chat/greeting",
                                 params={"user_id": st.session_state.subscriber_id,
                                        "mode": "auto", "target_lang": "ko"},
                                 headers=headers)
                    if greet.status_code < 400:
                        greet_data = greet.json()
                        st.session_state["_greeting"] = greet_data.get("greeting")
    except Exception:
        pass  # 네트워크 오류시 무시

if "_ping_called" not in st.session_state:
    st.session_state["_ping_called"] = True
    _call_ping_and_greeting()

# ════════════════════════════════════════════════════════
# 헬퍼 함수
# ════════════════════════════════════════════════════════

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
    st.markdown('<div class="brand"><span class="leaf">🌿</span> </div>', unsafe_allow_html=True)

    st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
    if st.button("✏️  새 대화", key="btn_new", use_container_width=True):
        _new_conv()
    st.markdown('</div>', unsafe_allow_html=True)

    convs = st.session_state.conversations
    if convs:
        st.markdown('<div class="side-section-label">최근 대화</div>', unsafe_allow_html=True)
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

    st.markdown('<div class="side-foot">응급: 자살예방상담전화 1393 &middot; 정신건강위기상담 1577-0199</div>', unsafe_allow_html=True)


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
    if st.button("▶" if not _sm else "■", key="btn_stream",
                 help="실시간 응답 켜기" if not _sm else "실시간 응답 끄기"):
        st.session_state.streaming_mode = not _sm
        st.rerun()

with c_login:
    _plabel = f"👤 {_uname}" if (_logged_in and _uname) else "👤 로그인"
    with st.popover(_plabel, use_container_width=True):
        if not _logged_in:
            _t = st.radio("", ["로그인", "가입하기"], horizontal=True,
                          key="auth_tab", label_visibility="collapsed")
            st.markdown("")  # spacer
            if _t == "로그인":
                _lem = st.text_input("이메일", key="li_em", placeholder="name@example.com")
                _lpw = st.text_input("비밀번호", key="li_pw", type="password", placeholder="••••••••")
                if st.button("로그인", key="btn_login", use_container_width=True):
                    if not _lem or not _lpw:
                        st.warning("이메일과 비밀번호를 모두 입력해 주세요.")
                    elif "@" not in _lem:
                        st.warning("올바른 이메일 형식으로 입력해 주세요.")
                    else:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/login",
                                           json={"email": _lem, "password": _lpw})
                            if r.status_code < 400:
                                d = r.json()
                                st.session_state.auth_token        = d["token"]
                                st.session_state.subscriber_id     = d["sub_id"]
                                st.session_state.user_display_name = _lem.split("@")[0]
                                st.success("로그인되었습니다!")
                                st.rerun()
                            else:
                                detail = r.json().get("detail", "")
                                st.error(detail or "이메일 또는 비밀번호가 올바르지 않습니다.")
                        except Exception as e:
                            st.error(f"서버 연결 오류: {e}")
            else:
                _em = st.text_input("이메일", key="su_em", placeholder="name@example.com")
                _pw = st.text_input("비밀번호", key="su_pw", type="password",
                                    placeholder="영문 + 숫자 8자 이상")
                _nm = st.text_input("이름 (선택)", key="su_nm", placeholder="표시될 이름")
                if st.button("✨ 가입하기", key="btn_signup", use_container_width=True):
                    if not _em or not _pw:
                        st.warning("이메일과 비밀번호를 입력해 주세요.")
                    elif "@" not in _em:
                        st.warning("올바른 이메일 형식으로 입력해 주세요.")
                    elif len(_pw) < 8:
                        st.warning("비밀번호는 8자 이상이어야 합니다.")
                    elif not any(c.isdigit() for c in _pw) or not any(c.isalpha() for c in _pw):
                        st.warning("비밀번호는 영문과 숫자를 포함해야 합니다.")
                    else:
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
                                st.success("가입이 완료되었습니다! 🎉")
                                st.rerun()
                            else:
                                st.error(r.json().get("detail", "가입에 실패했습니다."))
                        except Exception as e:
                            st.error(f"서버 연결 오류: {e}")
        else:
            st.markdown(f"**{_uname}** 님, 환영합니다")
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
    # ✅ 패치 4: 개인화된 greeting 표시
    personal_greeting = st.session_state.get("_greeting")

    if personal_greeting:
        _sub_text = personal_greeting
    else:
        _hour = datetime.now().hour
        _greet = "좋은 아침입니다" if _hour < 12 else ("좋은 오후입니다" if _hour < 18 else "좋은 저녁입니다")
        _sub_text = f"{_greet}. 복음과 말씀에 대해 무엇이든 편하게 물어보세요."

    st.markdown(f"""
<div class="bible-greeting">
    <div class="glyph">🌿</div>
    <h1>무엇을 도와드릴까요?</h1>
    <p class="lede">{_sub_text}</p>
    <div class="rule"></div>
</div>
""", unsafe_allow_html=True)



# ════════════════════════════════════════════════════════
# 대화 메시지 표시
# ════════════════════════════════════════════════════════
for idx, m in enumerate(st.session_state.msgs):
    _av = "🌿" if m["role"] == "assistant" else "🙋"
    with st.chat_message(m["role"], avatar=_av):
        st.markdown(m["content"])

        # 출처 표시 (기존 대화 메시지)
        if m["role"] == "assistant" and m.get("sources"):
            srcs = m["sources"]
            if isinstance(srcs, list) and len(srcs) > 0:
                with st.expander(f"참고 문헌 ({len(srcs)}개)", expanded=False):
                    for i, s in enumerate(srcs[:5]):
                        if isinstance(s, dict):
                            title = s.get("title", "문서") or "문서"
                            st.caption(f"{i+1}. **{title}**")

        iid = m.get("interaction_id")
        if m["role"] == "assistant" and iid and m.get("feedback") is None:
            st.markdown('<div class="feedback-btn-area">', unsafe_allow_html=True)
            c1, c2, _ = st.columns([0.5, 0.5, 7])
            with c1:
                if st.button("👍", key=f"up_{idx}", help="도움이 되었어요"):
                    if _send_feedback(iid, 1): m["feedback"] = 1; st.rerun()
            with c2:
                if st.button("👎", key=f"dn_{idx}", help="아쉬워요"):
                    if _send_feedback(iid, -1): m["feedback"] = -1; st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        elif m["role"] == "assistant" and m.get("feedback") is not None:
            _fb = m["feedback"]
            _fb_icon = "👍" if _fb == 1 else "👎"
            _fb_text = "의견 감사합니다" if _fb == 1 else "피드백 감사합니다"
            st.caption(f"{_fb_icon} {_fb_text}")


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
            # G-6: 스트리밍 모드 (SSE 파서 v2) ──────────────────────────────────
            import json as _sse_json
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
                    buffer = ""
                    for line in r.iter_lines():
                        if not line:
                            continue

                        # SSE 라인 파싱
                        if line.startswith("data: "):
                            data = line[6:]  # "data: " 제거
                            if data == "done":
                                break

                            # ✅ JSON이면 메타데이터 (sources, interaction_id)
                            try:
                                parsed = _sse_json.loads(data)
                                if isinstance(parsed, dict) and "interaction_id" in parsed:
                                    interaction_id = parsed.get("interaction_id")
                                    sources = parsed.get("sources", [])
                                    continue  # 메타데이터는 텍스트에 합치지 않음
                            except Exception:
                                pass

                            # 일반 텍스트 조각
                            if data.strip():
                                buffer += data
                                full_text += data
                                ph.markdown(full_text + "▌")

                        elif line.startswith("event: done"):
                            break

                    ph.markdown(full_text)

                    # 출처 표시 (스트리밍)
                    if sources:
                        with st.expander(f"참고 문헌 ({len(sources)}개)", expanded=False):
                            for i, s in enumerate(sources[:5]):
                                title = s.get("title", "문서") or "문서"
                                st.caption(f"{i+1}. **{title}**")
            except httpx.ConnectError:
                st.error("서버에 연결할 수 없어요. 나중에 다시 시도해 주세요.")
                full_text = ""
                ph.markdown("")
            except httpx.TimeoutException:
                st.error("응답 시간이 너무 길어요. 질문을 줄여서 다시 시도해 주세요.")
                full_text = ""
                ph.markdown("")
            except Exception as e:
                st.error(f"스트리밍 중 오류가 발생했어요. 다시 시도해 주세요.")
                full_text = ""
                ph.markdown("")
        else:
            # 기존 비스트리밍 모드 ─────────────────────────────────────────
            with st.spinner("답변 생성 중..."):
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

                        # 출처 표시
                        if sources:
                            with st.expander(f"참고 문헌 ({len(sources)}개)", expanded=False):
                                for i, s in enumerate(sources[:5]):
                                    title = s.get("title", "문서") or "문서"
                                    st.caption(f"{i+1}. **{title}**")
                    elif r.status_code == 429:
                        st.warning("오늘 무료 응답이 모두 사용되었어요. 오른쪽 상단 👤 에서 가입하시면 월 10만 토큰을 드려요.")
                        full_text = ""
                    elif r.status_code >= 500:
                        st.error("서버가 응답하지 않아요. 잠시 후 다시 시도해 주세요.")
                        full_text = ""
                    else:
                        detail = ""
                        try:
                            detail = r.json().get("detail", "")
                        except Exception:
                            pass
                        st.error(detail or "요청을 처리하는 중 문제가 생겼어요. 다시 시도해 주세요.")
                        full_text = ""
                except httpx.TimeoutException:
                    st.error("응답 시간이 너무 오래 걸려요. 질문을 더 구체적으로 줄여보세요.")
                    full_text = ""
                except httpx.ConnectError:
                    st.error("서버에 연결할 수 없어요. 나중에 다시 시도해 주세요.")
                    full_text = ""
                except Exception as e:
                    st.error(f"오류가 발생했어요. 잠시 후 다시 시도해 주세요.")
                    full_text = ""

    if full_text:
        st.session_state.msgs.append({
            "role": "assistant", "content": full_text,
            "sources": sources, "interaction_id": interaction_id, "feedback": None,
        })
        st.rerun()
