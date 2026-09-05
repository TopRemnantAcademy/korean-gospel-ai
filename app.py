"""통합 앱 — 복음 AI 채팅 + 관리 콘솔

실행: streamlit run app.py --server.port 8501
포트 하나로 사용자 채팅 + 관리자 기능 모두 제공.
"""
from __future__ import annotations

import os
import sys
import uuid
import httpx
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
API_BASE     = os.getenv("API_BASE", "http://127.0.0.1:8000")
QDRANT_URL   = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")

# KRAI.com 공개 모드: true 이면 통합앱(8501)에서 관리자 진입/페이지 완전 차단.
# 운영자 콘솔은 별도 관리자 허브(8502, admin/app.py)로 분리 운영.
# ⚠️ 8502 관리자 허브는 이 값을 설정하지 않아야(또는 false) 정상 동작함.
KRAI_PUBLIC_MODE = os.getenv("KRAI_PUBLIC_MODE", "false").lower() == "true"

# ══════════════════════════════════════════════════════════════════════════════
# 페이지 설정 (최우선)
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="복음 AI",
    page_icon="🌿",
    layout="centered",
    initial_sidebar_state="auto",
)

# ══════════════════════════════════════════════════════════════════════════════
# 세션 초기화
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULTS = {
    "mode":              "chat",       # "chat" | "admin_login" | "admin"
    "auth_ok":           False,        # admin/pages gate() 호환
    "subscriber_id":     "anon_" + uuid.uuid4().hex[:12],
    "msgs":              [],
    "conversations":     [],
    "auth_token":        None,
    "user_display_name": None,
    "theme":             "light",
    "streaming_mode":    False,
    "lang":              None,         # 첫 방문 시 시스템 언어로 자동 감지, 이후 사용자 선택 유지
    "show_settings":     False,        # 모바일 설정 패널 열림 여부
    "vpflag":            "d",          # viewport 플래그: "d"(데스크톱) / "m"(모바일)
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 첫 등록(최초 방문) 언어 자동 적용 ──
# 브라우저 Accept-Language 를 읽어 한국어/중국어 결정.
# 주의: st.context.headers 는 Streamlit 에서 안정적으로 보장되지 않아 자주 비어 있음.
#       따라서 zh 가 '명시적으로' 포함된 경우만 zh 로 판정하고, 그 외(비어있음/ko/en 등)
#       모든 경우는 한국어(ko) 기본으로 처리 → 한국어 사용자에게 중국어가 보이는 일 차단.
# 이미 사용자가 선택한 적 있으면(st.session_state.lang 가 None 아님) 덮어쓰지 않음.
if st.session_state.lang is None:
    _detected = "ko"
    try:
        _al = (st.context.headers or {}).get("Accept-Language", "") or ""
        _al_l = _al.lower()
        # zh 가 명시적으로 첫 언어로 오는 경우만 중국어로 판정
        if _al_l.startswith("zh") or ",zh" in _al_l or ";zh" in _al_l:
            _detected = "zh"
        else:
            _detected = "ko"   # ko/en/others/empty → 모두 한국어 기본
    except Exception:
        _detected = "ko"
    st.session_state.lang = _detected


# ── i18n 헬퍼 ──
# UI 에 하드코딩된 중국어/한국어 텍스트를 lang 에 따라 분기시켜
# "한국어 버전인데 중국어가 보인다" 문제를 근본 차단.
def _t(ko_text: str, zh_text: str) -> str:
    """현재 선택된 언어(ko 기본)에 따라 텍스트 반환."""
    return zh_text if st.session_state.get("lang", "ko") == "zh" else ko_text

# ══════════════════════════════════════════════════════════════════════════════
# 테마
# ══════════════════════════════════════════════════════════════════════════════
THEMES = {
    "light": dict(
        app_bg="#FFFFFF", sidebar_bg="#F7F7F5", sidebar_hover="#ECECEA",
        sidebar_text="#111111", input_bg="#F5F5F3", input_border="#D4D4D2",
        input_focus="#111111", text="#111111", text_sub="#454545",
        text_muted="#757575", divider="#E6E6E4", accent="#111111",
        btn_bg="#111111", btn_text="#FFFFFF", popup_bg="#FFFFFF",
        user_msg_bg="#F0F0EE", dark=False,
        grad_from="#111111", grad_to="#6B6B6B",
    ),
    "dark": dict(
        app_bg="#0A0A0A", sidebar_bg="#121212", sidebar_hover="#1F1F1F",
        sidebar_text="#ECECEC", input_bg="#161616", input_border="#333333",
        input_focus="#FFFFFF", text="#ECECEC", text_sub="#C6C6C6",
        text_muted="#888888", divider="#262626", accent="#FFFFFF",
        btn_bg="#FFFFFF", btn_text="#111111", popup_bg="#1A1A1A",
        user_msg_bg="#1E1E1E", dark=True,
        grad_from="#FFFFFF", grad_to="#9A9A9A",
    ),
}
_TK = st.session_state.theme
_T  = THEMES[_TK]


def _inject_css(t: dict) -> None:
    # 다크 모드 대응: 텍스트 색뿐 아니라 컨테이너 '배경'까지 함께 테마화해야
    # 흰 판에 흰 글자(가독성 0) 현상이 사라진다. (접근성 대비 4.5:1 이상)
    dark_extra = ""
    if t["dark"]:
        dark_extra = f"""
/* ── 다크: 본문 텍스트 ── */
.stApp, .stApp p, .stApp span, .stApp li, .stApp label,
[data-testid="stMarkdownContainer"],
[data-testid="stChatMessageContent"] {{ color: {t['text']} !important; }}

/* ── 다크: 입력 필드 ── */
textarea, [data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input {{
    background: {t['input_bg']} !important; color: {t['text']} !important;
    border-color: {t['input_border']} !important;
}}
[data-testid="stTextInput"] input:focus {{
    border-color: {t['input_focus']} !important;
}}

/* ── 다크: 채팅 말풍선(어시스턴트/유저) 배경 + 텍스트 ── */
[data-testid="stChatMessageContent"] {{
    background: {t['user_msg_bg']} !important;
    border: 1px solid {t['divider']} !important;
    border-radius: 14px !important;
    padding: 0.75rem 0.95rem !important;
    color: {t['text']} !important;
}}
[data-testid="stChatMessageContent"] p,
[data-testid="stChatMessageContent"] code,
[data-testid="stChatMessageContent"] a {{ color: {t['text']} !important; }}
[data-testid="stChatMessageContent"] a {{ text-decoration: underline; }}
[data-testid="stChatMessageContent"] code {{
    background: {t['sidebar_bg']} !important;
}}
[data-testid="stChatMessageAvatarUser"] {{
    background: {t['sidebar_hover']} !important; border-radius: 50% !important;
}}

/* ── 다크: 위젯(radio/selectbox/checkbox/expander) ── */
[data-testid="stRadio"] label,
[data-testid="stRadio"] span,
[data-testid="stCheckbox"] label,
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label {{ color: {t['text']} !important; }}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    background: {t['sidebar_bg']} !important; color: {t['text']} !important;
}}
[data-testid="stExpander"] {{
    border: 1px solid {t['divider']} !important; border-radius: 12px !important;
    background: {t['sidebar_bg']} !important;
}}

/* ── 다크: 팝오버(로그인 등) 컨텐츠 배경 ── */
[data-testid="stPopover"] [data-testid="stPopoverContent"],
[data-baseweb="popover"] {{
    background: {t['popup_bg']} !important;
    border: 1px solid {t['divider']} !important;
    color: {t['text']} !important;
}}
[data-testid="stPopover"] [data-testid="stPopoverContent"] * {{
    color: {t['text']} !important;
}}

/* ── 다크: 알림(info/success/warning/error) ── */
.stAlert, [data-testid="stAlert"] {{
    background: {t['sidebar_bg']} !important;
    border: 1px solid {t['divider']} !important;
    color: {t['text']} !important;
}}
[data-testid="stAlert"] p, [data-testid="stAlert"] span,
[data-testid="stAlert"] a {{ color: {t['text']} !important; }}
[data-testid="stAlert"] a {{ text-decoration: underline; }}

/* ── 다크: 테이블/데이터프레임 ── */
[data-testid="stTable"] table, [data-testid="stDataFrame"] table {{
    background: {t['sidebar_bg']} !important; color: {t['text']} !important;
}}
[data-testid="stTable"] th, [data-testid="stTable"] td,
[data-testid="stDataFrame"] th, [data-testid="stDataFrame"] td {{
    border-color: {t['divider']} !important; color: {t['text']} !important;
}}

.stCaption {{ color: {t['text_muted']} !important; }}
"""
    st.markdown(f"""
<style>
#MainMenu, header[data-testid="stHeader"],
.stDeployButton, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"]
{{ display:none !important; visibility:hidden !important; }}
header[data-testid="stHeader"] {{ height:0 !important; }}

.stApp {{ background:{t['app_bg']} !important; transition:background 0.3s; }}
[data-testid="stSidebar"] {{
    background:{t['sidebar_bg']} !important;
    border-right:1px solid {t['divider']} !important;
    transition:background 0.3s;
}}
html, body, [class*="css"] {{
    font-family: 'Google Sans', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
}}
.block-container {{
    padding-top:0 !important; padding-bottom:0.5rem !important; max-width:100% !important;
}}
[data-testid="stSidebarContent"] {{ padding:1rem 0.75rem 1.5rem; }}

/* ── 우측 인기 질문 패널 ── */
.right-panel {{
    background: {t['sidebar_bg']};
    border: 1px solid {t['divider']};
    border-radius: 14px;
    padding: 1rem 0.85rem;
    margin-top: 0.5rem;
}}
.right-panel h4 {{
    margin: 0 0 0.6rem 0;
    font-size: 1rem;
    font-weight: 600;
    color: {t['text']};
}}
.right-panel .rank-item {{
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.35rem 0;
    font-size: 0.92rem;
    color: {t['text']};
    border-bottom: 1px solid {t['divider']};
}}
.right-panel .rank-item:last-child {{ border-bottom: none; }}
.right-panel .rank-num {{
    min-width: 1.5rem;
    font-weight: 700;
    color: {t['text_muted']};
}}
.right-panel .rank-text {{
    flex: 1;
    line-height: 1.35;
}}

/* ── 사이드바 버튼 공통 ── */
[data-testid="stSidebar"] .stButton button {{
    background:transparent !important; border:none !important;
    border-radius:8px !important; color:{t['sidebar_text']} !important;
    font-size:0.87rem !important; padding:0.45rem 0.75rem !important;
    width:100% !important; text-align:left !important;
    justify-content:flex-start !important; white-space:nowrap !important;
    overflow:hidden !important; text-overflow:ellipsis !important;
    margin-bottom:1px !important; transition:background 0.15s !important;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background:{t['sidebar_hover']} !important;
}}

/* ── 새 채팅 버튼 ── */
.new-chat-btn button {{
    background:transparent !important;
    border:1px solid {t['divider']} !important;
    border-radius:24px !important;
    color:{t['sidebar_text']} !important;
    font-size:0.9rem !important; font-weight:500 !important;
    padding:0.5rem 1rem !important; width:100% !important;
    text-align:left !important; justify-content:flex-start !important;
    gap:8px !important; transition:background 0.15s !important;
    margin-bottom:0.5rem !important;
}}
.new-chat-btn button:hover {{ background:{t['sidebar_hover']} !important; }}

/* ── 관리자 진입 버튼 (사이드바 내 강조) ── */
.admin-entry-btn button {{
    background:transparent !important;
    border:1px solid {t['divider']} !important;
    border-radius:8px !important;
    color:{t['text_muted']} !important;
    font-size:0.82rem !important;
    padding:0.4rem 0.75rem !important;
    width:100% !important; text-align:center !important;
    justify-content:center !important;
    transition:all 0.15s !important;
}}
.admin-entry-btn button:hover {{
    background:{t['sidebar_hover']} !important;
    color:{t['text']} !important;
    border-color:{t['accent']} !important;
}}

/* ── 상단 바 ── */
.topbar {{
    display:flex; justify-content:flex-end; align-items:center;
    padding:0.5rem 0 0.3rem 0; gap:4px;
}}

/* 모바일/태블릿용 설정 토글(⚙️) + 설정 패널 */
.settings-toggle button {{
    height:40px !important; width:40px !important; padding:0 !important;
    border-radius:50% !important; border:1px solid {t['divider']} !important;
    background:{t['input_bg']} !important; color:{t['text']} !important;
    font-size:1.1rem !important; box-shadow:0 1px 4px rgba(0,0,0,.12) !important;
    transition:transform .15s ease, background .2s ease !important;
}}
.settings-toggle button:hover {{ background:{t['sidebar_hover']} !important; transform:rotate(25deg); }}

/* 설정 패널(드로어/카드) */
.settings-panel {{
    background:{t['popup_bg']};
    border:1px solid {t['divider']};
    border-radius:16px;
    padding:0.9rem 1rem 1.1rem;
    margin:0.4rem 0 0.8rem;
    box-shadow:0 8px 28px rgba(0,0,0,.18);
    backdrop-filter:blur(8px);
}}
.settings-panel .sp-title {{
    font-size:0.78rem; font-weight:600; letter-spacing:.04em;
    color:{t['text_muted']}; text-transform:uppercase; margin:0 0 0.5rem;
}}
.settings-panel .sp-row {{
    display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.55rem;
}}
.settings-panel .sp-row .stButton button,
.settings-panel .sp-row [data-testid="stPopover"] > button {{
    height:38px !important; padding:0 0.9rem !important;
    border-radius:12px !important; border:1px solid {t['divider']} !important;
    background:{t['input_bg']} !important; color:{t['text']} !important;
    font-size:0.9rem !important; white-space:nowrap !important;
    transition:background .2s ease !important;
}}
.settings-panel .sp-row .stButton button:hover,
.settings-panel .sp-row [data-testid="stPopover"] > button:hover {{
    background:{t['sidebar_hover']} !important;
}}
/* JS 로 주입한 viewport 플래그 입력창 숨김 */
input[aria-label="vpflag"] {{
    position:absolute !important; width:1px !important; height:1px !important;
    opacity:0 !important; pointer-events:none !important; overflow:hidden !important;
}}
.topbar .stButton button {{
    height:32px !important; padding:0 0.7rem !important;
    border-radius:18px !important; border:1px solid {t['divider']} !important;
    background:transparent !important; color:{t['text_sub']} !important;
    font-size:0.9rem !important; line-height:1 !important;
    white-space:nowrap !important;
}}
.topbar .stButton button:hover {{
    background:{t['sidebar_bg']} !important; color:{t['text']} !important;
}}
.topbar [data-testid="stPopover"] > button {{
    height:32px !important; padding:0 0.9rem !important;
    border-radius:18px !important; border:1px solid {t['divider']} !important;
    background:transparent !important; color:{t['text_sub']} !important;
    font-size:0.83rem !important; font-weight:500 !important;
    white-space:nowrap !important;
}}
.topbar [data-testid="stPopover"] > button:hover {{
    background:{t['sidebar_bg']} !important; color:{t['text']} !important;
}}

/* ── 그리팅 ── */
.gemini-greeting {{ text-align:center; padding:3rem 1rem 2rem; }}
.gemini-greeting .icon {{ font-size:3rem; margin-bottom:0.5rem; }}
.gemini-greeting h2 {{
    font-size:2rem !important; font-weight:400 !important;
    color:{t['text']} !important; margin:0 0 0.4rem !important;
    letter-spacing:-0.01em;
    background:linear-gradient(135deg,{t['grad_from']} 0%,{t['grad_to']} 100%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    background-clip:text;
}}
.gemini-greeting .sub {{ font-size:1rem; color:{t['text_sub']}; margin:0; }}

/* ── 채팅 메시지 ── */
.stChatMessage {{ font-size:1.0rem; line-height:1.8; }}
[data-testid="stChatMessageContent"] p {{ margin-bottom:0.6em; }}
[data-testid="stChatMessageAvatarAssistant"] {{
    background:{t['accent']} !important; border-radius:50% !important;
}}

/* ── 채팅 입력 (단일 컨테이너로 겹침 제거) ── */
[data-testid="stChatInput"] {{
    border-radius:24px !important; background:{t['input_bg']} !important;
    border:1px solid {t['input_border']} !important;
    padding:0.35rem 0.6rem !important;
    box-shadow:0 1px 3px rgba(0,0,0,0.08) !important;
    transition:border-color 0.2s, box-shadow 0.2s !important;
}}
[data-testid="stChatInput"]:focus-within {{
    border-color:{t['input_focus']} !important;
    box-shadow:0 1px 6px rgba(0,0,0,0.16) !important;
}}
/* 내부 base-input 의 기본 테두리/배경을 제거해 겹친 이중 박스 현상 방지 */
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="textarea"] {{
    background:transparent !important; border:none !important;
    box-shadow:none !important;
}}
[data-testid="stChatInput"] textarea {{
    background:transparent !important; border:none !important;
    box-shadow:none !important; color:{t['text']} !important;
    font-size:1rem !important; padding:0.15rem 0.4rem !important;
    resize:none !important;
}}
/* 빈 안내 텍스트 영역이 차지하는 여백 제거 */
[data-testid="InputInstructions"] {{ display:none !important; }}
/* 전송 버튼(비활성)은 입력창 우측에 자연스럽게 배치 */
[data-testid="stChatInputSubmitButton"] {{
    background:transparent !important; border:none !important;
    color:{t['text_muted']} !important;
}}
{dark_extra}
</style>
""", unsafe_allow_html=True)


_inject_css(_T)


# ══════════════════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def _get_http_client() -> httpx.Client:
    """프로세스 전역 공유 httpx.Client — 커넥션 풀 재사용.

    [PERF] 이전엔 매 호출 `with httpx.Client(...)` 로 새 커넥션 풀을 만들어
    TCP+TLS 핸드셰이크를 반복했다. 공유 클라이언트로 연결을 재사용한다.
    (요청별 timeout 은 각 호출에서 명시 전달. 절대 close 하지 않음.)
    """
    return httpx.Client(
        timeout=60.0,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    )


def _fetch_quota(sub_id: str) -> dict | None:
    """일일 질문 할당량(quota_service) 잔여 조회. 백엔드 GET /quota 와 계약 일치.

    반환: {"tier","remaining","daily_limit","reset_in_hours","enabled"} 또는 None.
    로그인 시 Bearer 토큰을, 게스트(미로그인) 시 DEFAULT_USER 기반 IP/uuid 산정을 위해
    user_id 를 함께 전달한다.
    """
    headers = {}
    if st.session_state.get("auth_token"):
        headers["Authorization"] = f"Bearer {st.session_state.auth_token}"
    try:
        c = _get_http_client()
        r = c.get(f"{API_BASE}/quota", params={"user_id": sub_id}, headers=headers, timeout=4)
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


def _send_feedback(iid: str, val: int) -> bool:
    try:
        c = _get_http_client()
        r = c.post(f"{API_BASE}/feedback",
                   json={"interaction_id": iid, "value": val,
                         "user_id": st.session_state.subscriber_id}, timeout=15)
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
    st.session_state.conversations = [c for c in st.session_state.conversations
                                       if c["id"] != conv["id"]]
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# 모드 분기
# ══════════════════════════════════════════════════════════════════════════════
_mode = st.session_state.mode  # "chat" | "admin_login" | "admin"

# DD-2: 공개 모드에서는 관리자 모드 진입 자체를 차단
if KRAI_PUBLIC_MODE and _mode in ("admin", "admin_login"):
    st.session_state.mode    = "chat"
    st.session_state.auth_ok = False
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ① ADMIN 모드 — 기존 admin/app.py 페이지들을 st.navigation 으로 통합
# ══════════════════════════════════════════════════════════════════════════════
if _mode == "admin":
    # --- Admin 페이지 정의 ---
    admin_pages = {
        "운영": [
            st.Page("admin/app.py", title="운영 허브", icon="🏠"),
        ],
        "콘텐츠": [
            st.Page("admin/pages/1_📚_Library.py",   title="자료실",      icon="📚"),
            st.Page("admin/pages/2_📥_Upload.py",    title="자료 업로드", icon="📥"),
            st.Page("admin/pages/14_📚_용어집.py",   title="용어집",      icon="📖"),
            st.Page("admin/pages/15_📥_자료흐름.py", title="자료 흐름",   icon="🔄"),
        ],
        "모니터링": [
            st.Page("admin/pages/4_📊_Status.py",   title="상태 모니터", icon="📊"),
            st.Page("admin/pages/5_💭_대화기록.py", title="대화 기록",   icon="💭"),
        ],
        "시스템": [
            st.Page("admin/pages/6_📝_프롬프트.py", title="프롬프트",    icon="📝"),
            st.Page("admin/pages/9_👥_유저관리.py", title="유저 관리",  icon="👥"),  # [P0-9] 파일명 수정(기존 9_👥_사람.py 로 참조해 crash)
            st.Page("admin/pages/10_⚙️_설정.py",    title="설정",        icon="⚙️"),
        ],
    }

    # --- Admin 사이드바 하단 버튼 ---
    with st.sidebar:
        st.markdown("---")
        st.markdown(
            f"<div style='font-size:0.75rem;color:{_T['text_muted']};padding:0.25rem 0;'>"
            f"<a href='{QDRANT_URL}/dashboard' target='_blank' "
            f"style='text-decoration:none;color:{_T['text_muted']};'>⚡ Qdrant 대시보드 열기</a></div>",
            unsafe_allow_html=True,
        )
        if st.button("💬 채팅으로 돌아가기", key="back_to_chat", use_container_width=True,
                     help="사용자 채팅 화면으로 돌아가기"):
            st.session_state.mode    = "chat"
            st.session_state.auth_ok = False
            st.rerun()

    pg = st.navigation(admin_pages)
    pg.run()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# ② ADMIN 로그인 화면
# ══════════════════════════════════════════════════════════════════════════════
if _mode == "admin_login":
    with st.sidebar:
        if st.button("← 채팅으로", key="cancel_login", use_container_width=True):
            st.session_state.mode = "chat"
            st.rerun()

    st.markdown("---")
    st.markdown("### 🔒 관리자 인증")
    st.caption("운영 콘솔에 접근하려면 비밀번호를 입력하세요.")
    pw = st.text_input("비밀번호", type="password", key="admin_pw",
                       placeholder="관리자 비밀번호 입력")
    col_ok, col_cancel = st.columns([1, 1])
    with col_ok:
        if st.button("✅ 확인", type="primary", use_container_width=True, key="pw_ok"):
            if pw == APP_PASSWORD:
                st.session_state.mode    = "admin"
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    with col_cancel:
        if st.button("취소", use_container_width=True, key="pw_cancel"):
            st.session_state.mode = "chat"
            st.rerun()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# ③ 채팅 모드 (기본)
# ══════════════════════════════════════════════════════════════════════════════

# ── 사이드바 ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🌿")

    # 새 대화 버튼
    st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
    if st.button("✏️  새 대화", key="btn_new", use_container_width=True):
        _new_conv()
    st.markdown('</div>', unsafe_allow_html=True)

    # 대화 기록
    convs = st.session_state.conversations
    if convs:
        st.markdown(
            f"<div style='font-size:0.75rem;color:{_T['text_muted']};"
            f"padding:0.5rem 0.25rem 0.25rem;font-weight:500;'>최근 대화</div>",
            unsafe_allow_html=True,
        )
        for conv in convs[:30]:
            if st.button(conv["title"], key=f"h_{conv['id']}", use_container_width=True):
                _load_conv(conv)

    # 대화 요약 (4개 이상 메시지 시)
    if len(st.session_state.msgs) >= 4:
        st.markdown("---")
        if st.button("📋 대화 요약", key="btn_sum", use_container_width=True):
            with st.spinner("요약 중…"):
                excerpt = "\n".join(
                    f"{'나' if m['role']=='user' else 'AI'}: {m['content'][:120]}"
                    for m in st.session_state.msgs[-8:]
                )
                try:
                    c = _get_http_client()
                    r = c.post(f"{API_BASE}/chat", json={
                        "query": f"다음 대화를 2~3줄로 핵심만 요약해 주세요:\n\n{excerpt}",
                        "history": [], "user_id": st.session_state.subscriber_id,
                    }, timeout=60)
                    st.info(r.json().get("answer", "요약 실패") if r.status_code < 400 else "요약 실패")
                except Exception:
                    st.warning("요약 중 오류가 발생했어요.")

    # 쿼터 표시 (question-count 할당량 = quota_service 계약)
    st.markdown("---")
    quota = _fetch_quota(st.session_state.subscriber_id)
    if quota and quota.get("enabled"):
        remaining = quota.get("remaining", 0)
        tier = quota.get("tier", "guest")
        if remaining > 0:
            st.caption(f"오늘 남은 응답({tier}): **{remaining}건**")
        else:
            st.warning("오늘 무료 응답이 모두 사용되었어요.")

    # 하단 구분 — 관리자 진입 + 긴급 전화
    st.markdown(
        f"<div style='margin-top:auto;padding-top:1.5rem;"
        f"font-size:0.72rem;color:{_T['text_muted']};line-height:1.7'>"
        f"⚠️ 응급: 한국생명의전화 1588-9191</div>",
        unsafe_allow_html=True,
    )
    if not KRAI_PUBLIC_MODE:
        st.markdown('<div class="admin-entry-btn">', unsafe_allow_html=True)
        if st.button("⚙️ 관리자", key="enter_admin",
                     help="운영 콘솔 열기 (비밀번호 필요)"):
            if APP_PASSWORD:
                st.session_state.mode = "admin_login"
            else:
                # [P0-6] APP_PASSWORD 미설정 시 무인증 관리자 진입 차단(fail-closed).
                # 기존에는 빈 비밀번호만으로 mode="admin" + auth_ok=True 가 설정됐다.
                st.error(
                    "APP_PASSWORD 가 설정되지 않아 관리자 모드가 잠겨 있습니다. "
                    ".env 에 APP_PASSWORD 를 설정한 뒤 Streamlit을 재시작하세요."
                )
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ── 상단 바 (테마 + 스트리밍 + 로그인) ──────────────────────────────────────
_logged_in = bool(st.session_state.auth_token)
_uname     = st.session_state.get("user_display_name") or ""
_is_dark   = (_TK == "dark")
_streaming = st.session_state.streaming_mode


def _render_auth_popover(label: str, ks: str = ""):
    """로그인/가입/로그아웃 패널 (데스크톱 팝오버와 모바일 설정 패널 공용)."""
    with st.popover(label, use_container_width=True):
        if not _logged_in:
            _t = st.radio("", ["로그인", "가입하기"], horizontal=True,
                          key=f"auth_tab{ks}", label_visibility="collapsed")
            if _t == "로그인":
                _lem = st.text_input("이메일", key=f"li_em{ks}", placeholder="이메일",
                                     label_visibility="collapsed")
                _lpw = st.text_input("비밀번호", key=f"li_pw{ks}", type="password",
                                     placeholder="비밀번호", label_visibility="collapsed")
                if st.button("로그인", key=f"btn_login{ks}", use_container_width=True):
                    if _lem and _lpw:
                        try:
                            c = _get_http_client()
                            r = c.post(f"{API_BASE}/auth/login",
                                       json={"email": _lem, "password": _lpw}, timeout=15)
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
                _em = st.text_input("이메일", key=f"su_em{ks}", placeholder="이메일",
                                    label_visibility="collapsed")
                _pw = st.text_input("비밀번호", key=f"su_pw{ks}", type="password",
                                    placeholder="비밀번호 (6자+)", label_visibility="collapsed")
                _nm = st.text_input("이름", key=f"su_nm{ks}", placeholder="이름 (선택)",
                                    label_visibility="collapsed")
                if st.button("✨ 가입하기", key=f"btn_signup{ks}", use_container_width=True):
                    if _em and _pw:
                        try:
                            c = _get_http_client()
                            r = c.post(f"{API_BASE}/auth/signup", json={
                                "email": _em, "password": _pw,
                                "display_name": _nm or None,
                                "guest_sub_id": st.session_state.subscriber_id,
                            }, timeout=15)
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
            if st.button("로그아웃", key=f"btn_logout{ks}", use_container_width=True):
                st.session_state.auth_token        = None
                st.session_state.user_display_name = None
                st.rerun()


# ── 반응형: viewport 폭을 JS 로 감지해 session_state.vpflag ("d"/"m") 에 기록 ──
import streamlit.components.v1 as components
components.html("""
<script>
(function(){
  function flagEl(){ return window.parent.document.querySelector('input[aria-label="vpflag"]'); }
  function apply(){
    var el = flagEl(); if(!el) return false;
    var m = window.innerWidth <= 768 ? 'm' : 'd';
    if(el.value !== m){
      var s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      s.call(el, m); el.dispatchEvent(new Event('input',{bubbles:true}));
    }
    return true;
  }
  function wait(){ if(apply()){} else setTimeout(wait,200); }
  window.addEventListener('resize', apply);
  wait();
})();
</script>
""", height=0)
_mobile = (st.session_state.get("vpflag") == "m")
st.text_input("vpflag", value=st.session_state.vpflag,
              label_visibility="hidden", key="vpflag")


if not _mobile:
    # ── 데스크톱: 기존 분산 컨트롤 ──
    st.markdown('<div class="topbar">', unsafe_allow_html=True)
    _, c_stream, c_lang, c_theme, c_login = st.columns([4.0, 1.1, 0.7, 0.7, 1.8])

    with c_stream:
        _stream_label = "🟢 스트리밍" if _streaming else "⚪ 스트리밍"
        if st.button(_stream_label, key="btn_stream",
                     help="스트리밍 끄기" if _streaming else "스트리밍 켜기"):
            st.session_state.streaming_mode = not _streaming
            st.rerun()

    with c_lang:
        _lang_now = st.session_state.get("lang", "ko")
        _lang_btn = "🌐 한국어" if _lang_now == "ko" else "🌐 中文"
        if st.button(_lang_btn, key="btn_lang",
                     help="언어 변경 (한국어 / 中文)"):
            st.session_state.lang = "zh" if _lang_now == "ko" else "ko"
            st.session_state.qa_lang = st.session_state.lang
            st.rerun()

    with c_theme:
        if st.button("☀️" if _is_dark else "🌙", key="btn_theme",
                     help="라이트 모드" if _is_dark else "다크 모드"):
            st.session_state.theme = "light" if _is_dark else "dark"
            st.rerun()

    with c_login:
        _plabel = f"👤 {_uname}" if (_logged_in and _uname) else "👤 로그인"
        _render_auth_popover(_plabel)

    st.markdown('</div>', unsafe_allow_html=True)

else:
    # ── 모바일/태블릿: 우측 설정(⚙️) 토글만 표시 ──
    st.markdown('<div class="topbar">', unsafe_allow_html=True)
    _, c_set = st.columns([5.5, 1.0])
    with c_set:
        if st.button("⚙️", key="btn_settings", help="설정 열기/닫기"):
            st.session_state.show_settings = not st.session_state.show_settings
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 설정 패널 (클릭 시 미화된 카드로 펼침)
    if st.session_state.show_settings:
        st.markdown('<div class="settings-panel">', unsafe_allow_html=True)
        st.markdown('<div class="sp-title">설정</div>', unsafe_allow_html=True)
        # 1행: 언어 / 테마
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            _lang_now = st.session_state.get("lang", "ko")
            _lang_btn = "🌐 한국어" if _lang_now == "ko" else "🌐 中文"
            if st.button(_lang_btn, key="btn_lang_m", use_container_width=True,
                         help="언어 변경"):
                st.session_state.lang = "zh" if _lang_now == "ko" else "ko"
                st.session_state.qa_lang = st.session_state.lang
                st.rerun()
        with r1c2:
            if st.button("☀️ 라이트" if _is_dark else "🌙 다크", key="btn_theme_m",
                         use_container_width=True, help="테마 변경"):
                st.session_state.theme = "light" if _is_dark else "dark"
                st.rerun()
        # 2행: 스트리밍 토글
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            _stream_label = "🟢 스트리밍" if _streaming else "⚪ 스트리밍"
            if st.button(_stream_label, key="btn_stream_m", use_container_width=True,
                         help="스트리밍 켜기/끄기"):
                st.session_state.streaming_mode = not _streaming
                st.rerun()
        with r2c2:
            _plabel = f"👤 {_uname}" if (_logged_in and _uname) else "👤 로그인"
            _render_auth_popover(_plabel, "_m")
        st.markdown('</div>', unsafe_allow_html=True)


# ── 빈 화면 그리팅 + 메시지 (좌측) / 인기 질문 (우측) 2단 레이아웃 ──────────
has_msgs = bool(st.session_state.msgs)

_left, _right = st.columns([2.5, 1.0])

with _left:
    if not has_msgs:
        _hour   = datetime.now().hour
        _greet  = ("좋은 아침입니다" if _hour < 12
                   else "좋은 오후입니다" if _hour < 18
                   else "좋은 저녁입니다")
        st.markdown(f"""
<div class="gemini-greeting">
    <div class="icon">🌿</div>
    <h2>무엇을 도와드릴까요?</h2>
    <p class="sub">{_greet}. 복음과 말씀에 대해 무엇이든 편하게 물어보세요.</p>
</div>
""", unsafe_allow_html=True)


    # ── 대화 메시지 표시 ─────────────────────────────────────────────────────────
    for idx, m in enumerate(st.session_state.msgs):
        _av = "🌿" if m["role"] == "assistant" else "🙋"
        with st.chat_message(m["role"], avatar=_av):
            st.markdown(m["content"])
            iid = m.get("interaction_id")
            if m["role"] == "assistant" and iid and m.get("feedback") is None:
                c1, c2, _ = st.columns([1, 1, 7])
                with c1:
                    if st.button("👍", key=f"up_{idx}", help="도움됐어요"):
                        if _send_feedback(iid, 1):
                            m["feedback"] = 1
                            st.rerun()
                with c2:
                    if st.button("👎", key=f"dn_{idx}", help="아쉬워요"):
                        if _send_feedback(iid, -1):
                            m["feedback"] = -1
                            st.rerun()


# ── 인기 질문(热门问答) 모듈 복원 + 모바일과 동일 기능 ─────────────────────────
def _popular_questions(limit: int = 8, lang: str = "ko") -> list:
    """백엔드 /ranking/questions?lang={lang} 를 조회(모바일과 동일 데이터)."""
    try:
        cli = _get_http_client()
        r = cli.get(
            f"{API_BASE}/ranking/questions",
            params={"lang": lang, "limit": limit, "period": "7d"}, timeout=10.0,
        )
        if r.status_code == 200:
            return r.json().get("rankings", []) or []
    except Exception:
        pass
    return []


def render_popular_questions(has_msgs: bool = False) -> None:
    """우측 패널에 실시간 인기 질문(랭킹) 렌더링."""
    _lang_now = st.session_state.get("lang", "ko")

    # 언어 토글: 한국어(기본) / 中文. 상단 언어 버튼과 동기화.
    _lang_label = st.radio(
        "", ["한국어", "中文"], horizontal=True,
        index=0 if _lang_now == "ko" else 1,
        key="qa_lang_radio", label_visibility="collapsed",
    )
    _qa_lang = "ko" if _lang_label == "한국어" else "zh"
    if _qa_lang != _lang_now:
        st.session_state.lang = _qa_lang
    st.session_state.qa_lang = _qa_lang

    items = _popular_questions(8, _qa_lang)
    if not items:
        st.caption(_t("표시할 인기 질문이 없습니다.", "暂无热门问题"))
        return

    # 카드형 랭킹 패널
    st.markdown(
        f'<div class="right-panel">'
        f'<h4>{_t("🔥 인기 질문", "🔥 热门问答")}</h4>',
        unsafe_allow_html=True,
    )
    for idx, it in enumerate(items):
        q = (it.get("question") or "").strip()
        if not q:
            continue
        rank = idx + 1
        st.markdown(
            f'<div class="rank-item">'
            f'<span class="rank-num">{rank}</span>'
            f'<span class="rank-text">{q}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # HTML 줄 사이에 숨겨진 버튼으로 클릭 시 질문 전송
        if st.button(q, key=f"pop_{_qa_lang}_{idx}", use_container_width=True):
            st.session_state["_pending_q"] = q
            st.session_state["_pending_q_lang"] = _qa_lang
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# 우측 패널에 인기 질문 렌더링 (좌측 메시지와 나란히)
with _right:
    render_popular_questions(has_msgs)


# ── 채팅 입력 ────────────────────────────────────────────────────────────────
_ph     = "무엇이든 물어보세요…" if not has_msgs else "메시지 입력…"
prompt  = st.chat_input(_ph)
_pq     = st.session_state.get("_pending_q")
_pq_lang = st.session_state.get("_pending_q_lang")
# 언어 버튼(st.session_state.lang)을 자유 입력 답변 언어 기본값으로 사용.
# 인기질문으로 온 경우에는 해당 질문 언어(_pq_lang)를 우선.
_target_lang = _pq_lang or st.session_state.get("lang", "ko")
# 이중언어 병기: 中文(등 비한국어) 선택 시 백엔드에 bilingual 요청 → 한국어 번역을 병기
_bilingual = (_pq_lang or "ko") != "ko"
if _pq is not None:
    st.session_state["_pending_q"] = None
    if "_pending_q_lang" in st.session_state:
        del st.session_state["_pending_q_lang"]
    prompt = _pq

if prompt:
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🙋"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🌿"):
        full_text = ""
        sources: list = []
        interaction_id = None
        ph = st.empty()

        # 병기 답변은 비스트리밍으로 처리해 본문/한국어 번역을 깔끔히 두 블록으로 분리
        use_stream = st.session_state.streaming_mode and not _bilingual
        if use_stream:
            # 스트리밍 모드
            try:
                c = _get_http_client()
                with c.stream(
                    "POST", f"{API_BASE}/chat/stream",
                    json={
                        "query": prompt,
                        "history": [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.msgs[:-1]
                        ],
                        "user_id": st.session_state.subscriber_id,
                        "target_lang": _target_lang,
                        "bilingual": _bilingual,
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
            # 일반 모드
            with st.spinner(""):
                try:
                    c = _get_http_client()
                    r = c.post(f"{API_BASE}/chat", json={
                        "query": prompt,
                        "history": [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.msgs[:-1]
                        ],
                        "user_id": st.session_state.subscriber_id,
                        "target_lang": _target_lang,
                        "bilingual": _bilingual,
                    }, timeout=180)
                    if r.status_code < 400:
                        data           = r.json()
                        full_text      = data.get("answer", "")
                        sources        = data.get("sources", [])
                        interaction_id = data.get("interaction_id")
                        ph.markdown(full_text)
                        # 이중언어 병기: 한국어 번역을 본문 아래 별도 블록으로 표시
                        _parallel = data.get("answer_parallel")
                        if _parallel:
                            st.divider()
                            st.markdown("🇰🇷 **한국어 번역**")
                            st.markdown(_parallel)
                    elif r.status_code == 429:
                        st.warning("오늘 무료 응답이 모두 사용되었어요. "
                                   "오른쪽 상단 👤 에서 가입하시면 월 10만 토큰을 드려요. 🎁")
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
