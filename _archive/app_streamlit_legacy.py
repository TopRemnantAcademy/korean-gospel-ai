"""통합 앱 — 채팅 + 관리 콘솔

실행: streamlit run app.py --server.port 8501
포트 하나로 사용자 채팅 + 관리자 기능 모두 제공.
"""

from __future__ import annotations

import os
import sys
import uuid
import hmac
import time
import html
import httpx
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from dotenv import load_dotenv
from admin.lib.mobile_swipe import inject_ipad_optimizations
import streamlit.components.v1 as components

load_dotenv(_ROOT / ".env")

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

# ══════════════════════════════════════════════════════════════════════════════
# 페이지 설정 (최우선)
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# 세션 초기화
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULTS = {
    "mode": "chat", # "chat" | "admin_login" | "admin"
    "auth_ok": False, # admin/pages gate() 호환
    "subscriber_id": "anon_" + uuid.uuid4().hex[:12],
    "msgs": [],
    "conversations": [],
    "auth_token": None,
    "user_display_name": None,
    "theme": "dark",
    "target_lang": "ko", # 응답 언어: ko(한국어) / zh(중국어 간체) / en(영어)
    "streaming_mode": True,
    "gemini_panel": None, # 열린 패널 ID (None이면 닫힘)
    "remember_conversations": True, # 이전 대화 기억하기 토글
    "saved_user_info": "", # Gemini 스타일 — 사용자가 기억시키고 싶은 정보
    "greeting_sub_msg": "", # 주간 메시지 (어드민 설정 → API에서 동적 조회)
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════
# UI 다국어 (ko / zh / en) — 단일 언어(지구) 버튼이 화면 전체 언어를 전환
# target_lang 하나로 응답 언어 + UI 언어를 동시에 제어
# ══════════════════════════════════════════════════════════════════
UI_LANGS = ["ko", "zh", "en"]
UI_LANG_NAMES = {"ko": "한국어", "zh": "中文", "en": "English"}

_UI = {
    # ── 사이드바 ──
    "new_chat": {"ko": "새 대화", "zh": "新对话", "en": "New chat"},
    "menu": {"ko": "메뉴", "zh": "菜单", "en": "Menu"},
    "recent": {"ko": "최근 대화", "zh": "最近对话", "en": "Recent chats"},
    "help": {"ko": "도움말", "zh": "帮助", "en": "Help"},
    "settings": {"ko": "설정", "zh": "设置", "en": "Settings"},
    "logout": {"ko": "로그아웃", "zh": "退出登录", "en": "Log out"},
    "login_signup": {"ko": "로그인 / 가입", "zh": "登录 / 注册", "en": "Log in / Sign up"},
    "login": {"ko": "로그인", "zh": "登录", "en": "Log in"},
    "signup": {"ko": "가입하기", "zh": "注册", "en": "Sign up"},
    "email": {"ko": "이메일", "zh": "邮箱", "en": "Email"},
    "password": {"ko": "비밀번호", "zh": "密码", "en": "Password"},
    "name": {"ko": "이름 (선택)", "zh": "姓名（可选）", "en": "Name (optional)"},
    "signup_done": {"ko": "가입이 완료되었습니다.", "zh": "注册已完成。", "en": "Sign-up complete."},
    "login_err": {"ko": "이메일 또는 비밀번호가 올바르지 않습니다.", "zh": "邮箱或密码不正确。", "en": "Email or password is incorrect."},
    "enter_email_pw": {"ko": "이메일과 비밀번호를 입력해 주세요.", "zh": "请输入邮箱和密码。", "en": "Please enter your email and password."},
    # ── 인사 / 그리팅 ──
    "greet_morning": {"ko": "좋은 아침입니다", "zh": "早上好", "en": "Good morning"},
    "greet_afternoon": {"ko": "좋은 오후입니다", "zh": "下午好", "en": "Good afternoon"},
    "greet_evening": {"ko": "좋은 저녁입니다", "zh": "晚上好", "en": "Good evening"},
    "greeting_title": {"ko": "무엇을 도와드릴까요?", "zh": "有什么可以帮您？", "en": "How can I help you?"},
    "greeting_sub": {"ko": "",
                      "zh": "",
                      "en": ""},
    "trending_label": {"ko": "지금 가장 많이 묻는 질문", "zh": "当前热门问题", "en": "Most asked questions right now"},
    "insight_view": {"ko": "통찰 보기", "zh": "查看洞察", "en": "View insight"},
    "ranking_title": {"ko": "실시간 질문 랭킹", "zh": "实时问题排行", "en": "Live question ranking"},
    "ranking_sub": {"ko": "기준 최근 7일", "zh": "近7天", "en": "Last 7 days"},
    "ranking_empty": {"ko": "아직 충분한 질문이 쌓이지 않았어요.<br>곧 실시간 랭킹이 채워질 거예요.",
                      "zh": "暂无足够问题。", "en": "Not enough questions yet."},
    "ranking_refresh": {"ko": "새로고침", "zh": "刷新", "en": "Refresh"},
    # ── 채팅 입력 ──
    "input_empty": {"ko": "무엇이든 물어보세요…", "zh": "请问任何问题…", "en": "Ask anything…"},
    "input_msg": {"ko": "메시지 입력…", "zh": "输入消息…", "en": "Type a message…"},
    # ── 채팅 오류/안내 ──
    "stream_err": {"ko": "지금은 시스템 유지보수 중이에요. 잠시 후 다시 이용해 주세요. 🙏",
                    "zh": "系统正在维护中，请稍后再来使用。🙏",
                    "en": "We're doing some maintenance right now. Please come back a little later. 🙏"},
    "stream_fail": {"ko": "지금은 시스템 유지보수 중이에요. 잠시 후 다시 이용해 주세요. 🙏",
                    "zh": "系统正在维护中，请稍后再来使用。🙏",
                    "en": "We're doing some maintenance right now. Please come back a little later. 🙏"},
    "free_used": {"ko": "오늘 무료 응답이 모두 사용되었어요. 오른쪽 상단 👤 에서 가입하시면 월 10만 토큰을 드려요. 🎁",
                  "zh": "今日免费回复已用完。点击右上角 👤 注册即可获赠每月 10 万 token。🎁",
                  "en": "Your free responses for today are used up. Sign up via 👉 in the top right for 100k tokens/month. 🎁"},
    "err_generic": {"ko": "죄송합니다. 잠시 후 다시 시도해 주세요.",
                    "zh": "抱歉，请稍后再试。",
                    "en": "Sorry, please try again shortly."},
    "conn_err": {"ko": "지금은 시스템 유지보수 중이에요. 잠시 후 다시 이용해 주세요. 🙏",
                 "zh": "系统正在维护中，请稍后再来使用。🙏",
                 "en": "We're doing some maintenance right now. Please come back a little later. 🙏"},
    # ── 패널 ──
    "panel_recent": {"ko": "최근 대화", "zh": "最近对话", "en": "Recent chats"},
    "panel_help": {"ko": "도움말", "zh": "帮助", "en": "Help"},
    "panel_settings": {"ko": "설정", "zh": "设置", "en": "Settings"},
    "panel_insight": {"ko": "질문 통찰", "zh": "问题洞察", "en": "Question insight"},
    "panel_menu": {"ko": "메뉴", "zh": "菜单", "en": "Menu"},
    "panel_close": {"ko": "패널 닫기 (Esc)", "zh": "关闭面板（Esc）", "en": "Close panel (Esc)"},
    "no_history": {"ko": "아직 저장된 대화가 없습니다. 새 대화를 시작해 보세요.",
                   "zh": "还没有保存的对话。开始新对话吧。",
                   "en": "No saved conversations yet. Start a new chat."},
    "continue_chat": {"ko": "이어서 대화하기", "zh": "继续对话", "en": "Continue chat"},
    "insight_sub": {"ko": "많은 분들이 궁금해하는 질문에 대한 분석입니다.",
                    "zh": "关于大家常问问题的分析。",
                    "en": "Analysis of questions many people ask."},
    "sec_root_cause": {"ko": "근본 원인 분석", "zh": "根本原因剖析", "en": "Root cause analysis"},
    "sec_ai_diagnosis": {"ko": "진단", "zh": "诊断", "en": "Diagnosis"},
    "sec_best_why": {"ko": "베스트 답변 이유", "zh": "最佳回答理由", "en": "Why this is the best answer"},
    "sec_reflection": {"ko": "묵상 포인트", "zh": "默想要点", "en": "Reflection point"},
    "best_answer": {"ko": "베스트 답변", "zh": "最佳回答", "en": "Best answer"},
    "insight_data_err": {"ko": "통찰 데이터를 불러올 수 없습니다.",
                         "zh": "无法加载洞察数据。",
                         "en": "Could not load insight data."},
    "insight_conn_err": {"ko": "통찰 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.",
                         "zh": "无法连接洞察服务，请稍后再试。",
                         "en": "Could not connect to the insight service. Please try again shortly."},
    "account_info": {"ko": "계정 정보", "zh": "账户信息", "en": "Account info"},
    "login_status": {"ko": "로그인 상태", "zh": "登录状态", "en": "Login status"},
    "logged_in": {"ko": "로그인 중", "zh": "已登录", "en": "Logged in"},
    "not_logged_in": {"ko": "로그인되지 않음", "zh": "未登录", "en": "Not logged in"},
    "display_name": {"ko": "표시 이름", "zh": "显示名称", "en": "Display name"},
    "go_login_signup": {"ko": "로그인 / 가입하러 가기", "zh": "前往登录 / 注册", "en": "Go to log in / sign up"},
    "login_toast": {"ko": "왼쪽 사이드바의 👤 로그인/가입 버튼을 눌러주세요.",
                    "zh": "请点击左侧边栏的 👤 登录/注册 按钮。",
                    "en": "Tap the 👤 Log in / sign up button in the left sidebar."},
    "chat_settings": {"ko": "대화 설정", "zh": "对话设置", "en": "Chat settings"},
    "remember_conv": {"ko": "이전 대화 내용 기억하기", "zh": "记住之前的对话内容", "en": "Remember previous conversations"},
    "remember_help": {"ko": "켜두면 대화 내역이 사이드바에 저장되고, 페이지를 새로고침해도 유지됩니다.",
                      "zh": "开启后对话记录会保存在侧边栏，刷新页面也不会丢失。",
                      "en": "When on, chat history is saved in the sidebar and persists after refresh."},
    "remember_caption": {"ko": "대화 히스토리를 사이드바에 저장하고 다음 방문 시 이어서 대화할 수 있어요.",
                         "zh": "对话历史会保存在侧边栏，下次访问可继续。",
                         "en": "Chat history is saved in the sidebar so you can continue next visit."},
    "my_info": {"ko": "나의 정보 설정", "zh": "我的信息设置", "en": "My info"},
    "my_info_desc": {"ko": "당신에 대해 기억했으면 하는 정보를 자유롭게 적어주세요. 예: '저는 매일 말씀 묵상으로 믿음을 키우고 있습니다', '가족과의 관계 회복을 위해 기도 중입니다', '교회 공동체와의 교제를 더 깊이 나누고 싶어요' 등",
                     "zh": "请自由填写希望记住的关于您的信息。例如：'我每天通过灵修话语建立信心'、'我为修复家庭关系祷告'、'我想更深入了解教会团契'等",
                     "en": "Freely write what you'd like us to remember about you. e.g. 'I build my faith through daily devotions', 'I'm praying for restored family relationships', 'I want deeper fellowship with my church community'."},
    "remember_info_label": {"ko": "기억할 정보", "zh": "要记住的信息", "en": "Info to remember"},
    "remember_info_ph": {"ko": "기억했으면 하는 정보를 입력하세요...\n예) 저는 30대 직장인이고, 바쁜 일상 속에서도 꾸준히 기도하며 믿음을 지키려 합니다.",
                          "zh": "请输入希望记住的信息...\n例如）我是 30 多岁的上班族，即使在忙碌的日常中也坚持祷告、守护信心。",
                          "en": "Enter info you'd like us to remember...\n e.g. I'm a professional in my 30s who keeps praying and holding to my faith amid a busy life."},
    "saved_ok": {"ko": "저장되었습니다. 앞으로 이 정보를 참고하여 답변합니다.",
                 "zh": "已保存。今后会参考此信息作答。",
                 "en": "Saved. This information will be referenced in future responses."},
    "saved_info": {"ko": "정보를 입력하면 더 개인화된 답변을 드릴 수 있어요.",
                   "zh": "输入信息后能提供更个性化的回答。",
                   "en": "Once you add info, we can give more personalized answers."},
    "reset": {"ko": "초기화", "zh": "重置", "en": "Reset"},
    # ── 도움말 FAQ ──
    "help_q1": {"ko": "어떤 도움을 받을 수 있나요?", "zh": "您可以获得哪些帮助？", "en": "What kind of help can I get?"},
    "help_a1": {"ko": "믿음 생활, 말씀 묵상, 기도, 영적 위로, 가족 및 대인관계 회복 등 신앙과 관련된 주제라면 무엇이든 물어볼 수 있어요.",
                "zh": "只要是信仰相关的话题——灵命生活、话语默想、祷告、心灵安慰、家庭与人际关系恢复等，都可以提问。",
                "en": "Anything faith-related: spiritual life, Scripture meditation, prayer, spiritual comfort, family and relationship restoration, and more."},
    "help_q2": {"ko": "답변은 어떻게 만들어지나요?", "zh": "回答是如何生成的？", "en": "How are answers generated?"},
    "help_a2": {"ko": "성경 말씀, 설교 자료, 신학적 가르침 등을 기반으로 답변을 생성합니다. 각 답변 하단의 📚 참고 문헌을 확인해 보세요.",
                "zh": "基于圣经经文、讲道资料、神学教导等生成回答。请查看每个回答下方的 📚 参考文献。",
                "en": "Answers are generated based on Bible verses, sermon materials, and theological teaching. Check the 📚 references at the bottom of each answer."},
    "help_q3": {"ko": "대화 기록은 저장되나요?", "zh": "对话记录会保存吗？", "en": "Are conversations saved?"},
    "help_a3": {"ko": "브라우저 세션 동안 최근 30개의 대화가 사이드바에 표시됩니다. 페이지를 새로고침하면 초기화됩니다.",
                "zh": "在浏览器会话期间，最近 30 条对话会显示在侧边栏。刷新页面后会重置。",
                "en": "During your browser session, the last 30 chats show in the sidebar. Refreshing the page resets them."},
    "help_q4": {"ko": "가입하면 무엇이 좋나요?", "zh": "注册有什么好处？", "en": "What are the benefits of signing up?"},
    "help_a4": {"ko": "월 10만 토큰의 무료 사용량과 장기 대화 저장, 개인화된 답변 기능을 이용할 수 있습니다.",
                "zh": "可获得每月 10 万 token 的免费额度、长期对话保存，以及个性化回答功能。",
                "en": "You get 100k tokens/month free, long-term chat storage, and personalized answers."},
    # ── 관리자 ──
    "admin_auth": {"ko": "관리자 인증", "zh": "管理员验证", "en": "Admin authentication"},
    "admin_caption": {"ko": "운영 콘솔에 접근하려면 비밀번호를 입력하세요.",
                      "zh": "请输入密码以访问运营控制台。",
                      "en": "Enter the password to access the operations console."},
    "admin_confirm": {"ko": "확인", "zh": "确认", "en": "Confirm"},
    "admin_cancel": {"ko": "취소", "zh": "取消", "en": "Cancel"},
    "admin_pw_wrong": {"ko": "비밀번호가 올바르지 않습니다.", "zh": "密码不正确。", "en": "The password is incorrect."},
    "admin_back": {"ko": "채팅으로 돌아가기", "zh": "返回聊天", "en": "Back to chat"},
    "admin_chat_back": {"ko": "채팅으로 돌아가기", "zh": "返回聊天", "en": "Back to chat"},
    "admin_chat_back_help": {"ko": "사용자 채팅 화면으로 돌아가기",
                             "zh": "返回用户聊天界面",
                             "en": "Return to the user chat screen"},
}


def T(key: str) -> str:
    """현재 언어(target_lang)에 맞는 UI 문자열을 반환합니다."""
    _lang = st.session_state.get("target_lang", "ko")
    if _lang not in UI_LANGS:
        _lang = "ko"
    return _UI.get(key, {}).get(_lang, _UI.get(key, {}).get("ko", key))


def _render_lang_globe(cur_lang: str) -> Optional[str]:
    """지구본 모양의 단일 언어 버튼 — 클릭 시 KO→ZH→EN 순환.

    BUG-01 수정: components.html()은 setComponentValue 반환값을 지원하지 않으므로
    st.button 기반으로 전환. 버튼 클릭 시 다음 언어 코드를 반환.
    """
    _labels = {"ko": "한국어", "zh": "中文", "en": "English"}
    _order = ["ko", "zh", "en"]
    _next = _order[(_order.index(cur_lang) + 1) % len(_order)]
    _label = f"🌐 {_labels.get(cur_lang, cur_lang)}"

    if st.button(
        _label,
        key="lang_globe_btn",
        help=f"클릭하여 언어 전환 (현재: {_labels.get(cur_lang, cur_lang)} → 다음: {_labels.get(_next, _next)})",
        use_container_width=True,
    ):
        return _next
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 테마
# ══════════════════════════════════════════════════════════════════════════════
THEMES = {
    "dark": dict(
        # ── Brutally minimal — monochrome dark. No brand color, no gradients. ──
        app_bg="#0a0a0a",
        surface="#141414",
        sidebar_bg="#0a0a0a",
        sidebar_hover="#1a1a1a",
        sidebar_text="#e6e6e6",
        input_bg="#141414",
        input_border="#232323",
        input_focus="#555555",
        text="#ededed",
        text_sub="#8a8a8a",
        text_muted="#6a6a6a",
        divider="#1e1e1e",
        accent="#ededed",
        accent_secondary="#c8c8c8",
        accent_glow="rgba(255,255,255,0.05)",
        chip_bg="transparent",
        chip_border="#242424",
        chip_hover="#161616",
        chip_text="#cfcfcf",
        btn_bg="transparent",
        btn_text="#ededed",
        popup_bg="#0f0f0f",
        user_msg_bg="#161616",
        gradient_start="#ededed",
        gradient_mid="#c8c8c8",
        gradient_end="#8a8a8a",
        shadow="rgba(0,0,0,0.4)",
        dark=True,
    ),
}
_TK = st.session_state.get("theme", "dark")
_T = THEMES.get(_TK, THEMES["dark"])


def _inject_css(t: dict) -> None:
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600&display=swap');

/* ═══════════════════════════════════════════════════════════════════════════
   BRUTALLY MINIMAL — MONOCHROME
   완전 심플: 브랜드 색 제거, 그라디언트/그림자/글로우/블러 전면 제거.
   순수 흑백 톤, 콘텐츠 우선. 장식은 최소, 여백은 최대.
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── RESET & HIDE ──────────────────────────────────────────────────────────── */
#MainMenu, header[data-testid="stHeader"],
.stDeployButton, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"]
{{ display:none !important; visibility:hidden !important; }}

/* ── ACCESSIBILITY: visible focus ring ─────────────────────────────────────── */
*:focus-visible {{
    outline: 2px solid {t["input_focus"]} !important;
    outline-offset: 2px !important;
}}
header[data-testid="stHeader"] {{ height:0 !important; }}

/* ── GLOBAL ────────────────────────────────────────────────────────────────── */
html, body, .stApp, .main, section[data-testid="stSidebar"] {{
    background: {t["app_bg"]} !important;
}}
html, body {{
    overflow-x: hidden !important;
    overscroll-behavior: none;
}}
[data-testid="stAppViewContainer"] {{
    overflow-x: hidden !important;
}}
[data-testid="stElementContainer"] [data-testid="stTable"] {{
    overflow-x: auto !important;
}}
.stApp {{
    background: {t["app_bg"]} !important;
}}

/* ── FONT: Noto Sans KR (Korean-first, monochrome minimal) ─────────────────── */
html, body, [class*="css"], [class*="st-"] {{
    font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    letter-spacing: -0.01em;
}}

/* ── BLOCK CONTAINER ───────────────────────────────────────────────────────── */
.block-container {{
    padding-top: 1rem !important;
    padding-bottom: 4rem !important;
    max-width: 760px;
    min-height: calc(100vh - 1rem);
}}
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
[data-testid="stMainBlockContainer"],
[data-testid="stVerticalBlockBorderWrapper"],
section.main, .stMainBlockContainer {{
    background: {t["app_bg"]} !important;
}}
[data-testid="stAppViewContainer"] > section,
[data-testid="stAppViewContainer"] > div > div > div,
.stMainBlockContainer > div,
section.main > div > div,
.block-container > div,
.element-container {{
    background: transparent !important;
}}

/* ── SIDEBAR: Gemini-style narrow icon rail ─────────────────────────────── */
[data-testid="stSidebar"] {{
    background: {t["sidebar_bg"]} !important;
    border-right: 1px solid {t["divider"]} !important;
    position: relative !important;
    z-index: 10 !important;
    width: 72px !important;
    min-width: 72px !important;
    max-width: 72px !important;
}}

/* 사이드바 collapse control: 사이드바가 열려 있을 때만 숨김 (JS가 보조) */
[data-testid="stSidebar"][aria-expanded="true"] ~ [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebar"][aria-expanded="true"] ~ div [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebar"][aria-expanded="true"] ~ header [data-testid="stSidebarCollapsedControl"] {{
    display: none !important;
}}

[data-testid="stSidebarContent"] {{
    padding: 0.75rem 0.45rem 1rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    height: 100% !important;
    gap: 0.15rem !important;
}}
[data-testid="stSidebar"] .stButton button {{
    background: transparent !important;
    border: none !important;
    border-radius: 14px !important;
    color: {t["sidebar_text"]} !important;
    font-size: 0.72rem !important;
    font-weight: 400 !important;
    padding: 0.6rem 0.5rem !important;
    width: 52px !important;
    max-width: 52px !important;
    min-width: 52px !important;
    text-align: center !important;
    justify-content: center !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    margin-bottom: 0.1rem !important;
    line-height: 1.2 !important;
    min-height: 44px !important;
    transition: background 0.15s ease, transform 0.12s ease;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background: {t["sidebar_hover"]} !important;
}}
[data-testid="stSidebar"] .stButton button:active {{
    background: {t["sidebar_hover"]} !important;
    transform: scale(0.96);
}}
[data-testid="stSidebarContent"] > div:nth-child(2) {{
    flex: 1 1 auto !important;
    overflow-y: auto !important;
    min-height: 0 !important;
    padding-bottom: 0.25rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: {t["divider"]} !important;
    margin: 0.6rem auto;
    width: 36px;
}}

/* 사이드바 섹션 라벨 — 숨김 (icon rail에서 불필요) */
.sidebar-section-label {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}}

/* ── SIDEBAR NEW CHAT: icon-style button for narrow rail ──────────────────── */
.new-chat-btn button {{
    background: transparent !important;
    border: none !important;
    border-radius: 14px !important;
    color: {t["sidebar_text"]} !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    padding: 0.6rem 0.5rem !important;
    width: 52px !important;
    max-width: 52px !important;
    min-width: 52px !important;
    text-align: center !important;
    justify-content: center !important;
    gap: 0 !important;
    transition: all 0.18s ease;
    margin-bottom: 0.5rem !important;
}}
.new-chat-btn button:hover {{
    background: {t["sidebar_hover"]} !important;
}}

/* ── SIDEBAR POPOVER ───────────────────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stPopover"] > button {{
    background: {t["surface"]} !important;
    border: 1px solid {t["divider"]} !important;
    border-radius: 14px !important;
    color: {t["sidebar_text"]} !important;
    font-size: 0.72rem !important;
    font-weight: 400 !important;
    padding: 0.55rem 0.5rem !important;
    width: 52px !important;
    max-width: 52px !important;
    min-width: 52px !important;
    text-align: center !important;
    justify-content: center !important;
    transition: all 0.2s ease;
}}
[data-testid="stSidebar"] [data-testid="stPopover"] > button:hover {{
    background: {t["sidebar_hover"]} !important;
}}
[data-testid="stSidebar"] [data-testid="stPopover"] > button svg,
[data-testid="stSidebar"] [data-testid="stPopover"] > button [data-testid="stIcon"],
[data-testid="stSidebar"] [data-testid="stPopover"] > button span[class*="Icon"],
[data-testid="stSidebar"] [data-testid="stPopover"] > button span[class*="icon"],
[data-testid="stSidebar"] [data-testid="stPopover"] > button i[class*="material"],
[data-testid="stSidebar"] [data-testid="stPopover"] > button [data-testid="stIconMaterial"],
[data-testid="stSidebar"] [data-testid="stPopover"] > button > span:last-child {{
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}}
[data-testid="stSidebar"] [data-testid="stPopover"] > button::after {{
    content: "▾" !important;
    font-size: 0.75rem !important;
    color: {t["text_muted"]} !important;
    margin-left: auto !important;
    line-height: 1 !important;
}}

/* ── TOP BAR: Gemini-style top-right user + settings ─────────────────────── */
.topbar {{
    display: flex !important;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 0.6rem 1.2rem;
    position: sticky;
    top: 0;
    z-index: 20;
    background: {t["app_bg"]};
}}
.topbar-user {{
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: {t["surface"]};
    display: flex;
    align-items: center;
    justify-content: center;
    color: {t["text"]};
    font-size: 0.82rem;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid {t["divider"]};
    transition: border-color 0.15s ease;
    flex-shrink: 0;
}}
.topbar-user:hover {{
    border-color: {t["text_muted"]};
}}
.topbar-settings {{
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: transparent;
    border: 1px solid {t["divider"]};
    color: {t["text_sub"]};
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.15s ease;
    flex-shrink: 0;
}}
.topbar-settings:hover {{
    background: {t["sidebar_hover"]};
    border-color: {t["text_muted"]};
    color: {t["text"]};
}}

/* ── GREETING: Gemini-style clean centered welcome ──────────────────────── */
.greeting {{
    text-align: center;
    padding: 4rem 1rem 1.5rem;
    position: relative;
    overflow: visible;
}}
.greeting h2 {{
    font-size: 1.7rem !important;
    font-weight: 300 !important;
    color: {t["text"]} !important;
    margin: 0 0 0.5rem !important;
    letter-spacing: -0.02em;
    line-height: 1.4;
}}
.greeting .sub {{
    font-size: 0.9rem;
    color: {t["text_sub"]};
    margin: 0;
    font-weight: 300;
    line-height: 1.6;
    max-width: 440px;
    margin-left: auto;
    margin-right: auto;
}}
.greeting .greeting-sub {{
    font-size: 0.92rem;
    color: {t["text_sub"]};
    margin: 0.6rem auto 0;
    font-weight: 400;
    line-height: 1.65;
    max-width: 520px;
    font-style: italic;
    opacity: 0.85;
}}

/* ── PROMPT SUGGESTION CHIPS: Gemini-style clean pills ────────────────────── */
.prompt-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
    justify-content: center;
    padding: 0.3rem 1rem 1.5rem;
    max-width: 100%;
    margin: 0 auto;
}}
.prompt-chip {{
    display: inline-flex;
    align-items: center;
    padding: 0.55rem 1.1rem;
    border-radius: 22px;
    border: 1px solid {t["chip_border"]};
    background: transparent;
    color: {t["chip_text"]};
    font-size: 0.87rem;
    font-weight: 400;
    cursor: pointer;
    transition: all 0.18s ease;
    white-space: nowrap;
    text-decoration: none !important;
    line-height: 1.4;
}}
.prompt-chip:hover {{
    background: {t["chip_hover"]};
    border-color: {t["text_muted"]};
}}
@media (max-width: 480px) {{
    .prompt-chips {{
        gap: 8px;
        padding: 0.25rem 0.5rem 1rem;
    }}
    .prompt-chip {{
        padding: 0.5rem 0.9rem;
        font-size: 0.82rem;
        border-radius: 20px;
    }}
}}

/* ── CHAT MESSAGES: refined bubble style ─────────────────────────────────────── */
/* 채팅 메시지 헤더 액션 버튼 중 링크/퍼머링크만 숨기기 — 복사/공유/피드백 버튼은 유지 */
[data-testid="stChatMessage"] [data-testid="stBaseButton-header"],
[data-testid="stChatMessage"] button[kind="header"],
[data-testid="stChatMessage"] [data-testid="stChatMessageAction"],
[data-testid="stChatMessage"] [data-testid="stChatMessageActionButton"],
[data-testid="stChatMessage"] a[href*="message"],
[data-testid="stChatMessage"] button[aria-label*="link" i],
[data-testid="stChatMessage"] button[aria-label*="permalink" i] {{
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    width: 0 !important;
    height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    pointer-events: none !important;
    position: absolute !important;
}}
.stChatMessage {{
    font-size: 0.95rem;
    line-height: 1.75;
    padding: 0.6rem 0 !important;
}}
[data-testid="stChatMessageContent"] {{
    padding: 0.85rem 1rem !important;
    border-radius: 18px !important;
}}
[data-testid="stChatMessageContent"]:has(> :only-child) {{
}}
[data-testid="stChatMessageContent"] p {{
    margin-bottom: 0.5em;
}}
[data-testid="stChatMessageContent"] p:last-child {{
    margin-bottom: 0;
}}
/* User message bubble — subtle */
[data-testid="stChatMessage"][aria-label*="user" i] [data-testid="stChatMessageContent"] {{
    background: {t["user_msg_bg"]} !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
}}
/* Assistant message — clean transparent */
[data-testid="stChatMessage"][aria-label*="assistant" i] [data-testid="stChatMessageContent"] {{
    background: transparent !important;
    border: none !important;
}}
[data-testid="stChatMessageAvatarAssistant"] {{
    background: {t["accent"]} !important;
    border-radius: 50% !important;
    box-shadow: none !important;
}}
[data-testid="chatAvatarIcon-assistant"] {{
    fill: {t["app_bg"]} !important;
}}
[data-testid="chatAvatarIcon-user"] {{
    fill: {t["text"]} !important;
}}

/* ── CHAT INPUT BOTTOM CONTAINER ────────────────────────────────────────────── */
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > *,
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stBottom"] {{
    border: none !important;
    border-top: none !important;
    outline: none !important;
    box-shadow: none !important;
    background: transparent !important;
}}
[data-testid="stBottomBlockContainer"] {{
    position: relative !important;
    z-index: 5 !important;
    padding: 0.5rem 0 0.75rem !important;
}}

/* ── CHAT INPUT: Gemini-style clean pill ──────────────────────────────────── */
[data-testid="stChatInput"] {{
    border-radius: 28px !important;
    background: {t["input_bg"]} !important;
    border: 1px solid {t["input_border"]} !important;
    padding: 0.5rem 0.6rem 0.5rem 1rem !important;
    transition: all 0.2s ease !important;
    box-shadow: none !important;
    margin-top: 0.3rem !important;
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    min-height: 52px !important;
}}
[data-testid="stChatInput"] > div {{
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
    gap: 4px !important;
}}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] [data-testid="stChatInputTextArea"] {{
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    background: transparent !important;
    resize: none !important;
    flex: 1 1 auto !important;
    min-width: 0 !important;
    max-height: 140px !important;
    overflow-y: auto !important;
}}
[data-testid="stChatInput"]:focus-within {{
    border-color: {t["input_focus"]} !important;
    background: {t["input_bg"]} !important;
    box-shadow: none !important;
}}
[data-testid="stChatInputTextArea"] {{
    font-size: 0.96rem !important;
    background: transparent !important;
    color: {t["text"]} !important;
    line-height: 1.58;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    padding: 2px 0 !important;
}}
[data-testid="stChatInputTextArea"]::placeholder {{
    color: {t["text_muted"]} !important;
    opacity: 0.85 !important;
}}
[data-testid="stChatInputTextArea"]::selection {{
    background: rgba(255,255,255,0.18) !important;
}}

/* ── SEND BUTTON: clean Gemini-style circle ──────────────────────────────── */
[data-testid="stChatInput"] button[data-testid*="submit"],
[data-testid="stChatInput"] button[aria-label*="send" i],
[data-testid="stChatInput"] button[kind="primary"] {{
    flex: 0 0 auto !important;
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    max-width: 34px !important;
    border-radius: 50% !important;
    background: {t["accent"]} !important;
    color: {t["app_bg"]} !important;
    border: none !important;
    box-shadow: none !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
    margin: 0 2px 0 4px !important;
    transition: all 0.18s ease !important;
    cursor: pointer !important;
    position: relative !important;
    z-index: 2 !important;
    overflow: hidden !important;
}}
[data-testid="stChatInput"] button[data-testid*="submit"]:hover,
[data-testid="stChatInput"] button[aria-label*="send" i]:hover,
[data-testid="stChatInput"] button[kind="primary"]:hover {{
    background: {t["accent_secondary"]} !important;
}}
[data-testid="stChatInput"] button[data-testid*="submit"]:active,
[data-testid="stChatInput"] button[aria-label*="send" i]:active,
[data-testid="stChatInput"] button[kind="primary"]:active {{
    transform: scale(0.95) !important;
}}
/* Fallback for other buttons inside input */
[data-testid="stChatInput"] button:not([data-testid*="submit"]):not([aria-label*="send" i]):not([kind="primary"]) {{
    background: transparent !important;
    color: {t["text_sub"]} !important;
    border: none !important;
    box-shadow: none !important;
    transition: color 0.2s ease;
    flex-shrink: 0 !important;
    margin-right: 2px !important;
}}
[data-testid="stChatInput"] button:not([data-testid*="submit"]):not([aria-label*="send" i]):not([kind="primary"]):hover {{
    color: {t["accent"]} !important;
}}

/* ── CHAT INPUT CONTAINER ───────────────────────────────────────────────────── */
[data-testid="stChatInputContainer"],
.stChatInputContainer {{
    background: transparent !important;
    border: none !important;
}}

/* ── 빈 화면: 입력창을 하단에 고정 (중첩 방지) ─────────────────────────────────── */
/* Greeting 페이지에서만 입력창을 하단 sticky로 배치.
   fixed 대신 아래 방식으로 전환하여 콘텐츠와 겹치지 않음:
   - main 컨테이너는 normal flow 유지 (greeting → chips → 입력창 순서)
   - 입력창은 하단에 붙되 스크롤 시 따라옴 */
.main:has(.greeting) [data-testid="stBottomBlockContainer"] {{
    position: fixed !important;
    bottom: 0 !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    width: 100% !important;
    max-width: 720px !important;
    padding: 0.75rem 1rem 1rem !important;
    z-index: 10 !important;
    background: linear-gradient(to top, {t["app_bg"]} 70%, transparent) !important;
}}

/* greeting 영역에 하단 여백 추가 — 고정 입력창과 겹침 방지 */
.main:has(.greeting) .greeting {{
    padding-bottom: 6rem !important;
}}
.main:has(.greeting) .prompt-chips {{
    padding-bottom: 7rem !important;
}}

/* ── TEXT COLOR ─────────────────────────────────────────────────────────────── */
.stApp p, .stApp span, .stApp li, .stApp label,
[data-testid="stMarkdownContainer"],
[data-testid="stChatMessageContent"],
.stMarkdown, .stMarkdown p {{
    color: {t["text"]} !important;
}}

/* ── FORM ELEMENTS ──────────────────────────────────────────────────────────── */
textarea, [data-testid="stTextArea"] textarea {{
    background: {t["input_bg"]} !important;
    color: {t["text"]} !important;
    border-color: {t["input_border"]} !important;
}}
[data-testid="stTextInput"] input {{
    background: {t["input_bg"]} !important;
    color: {t["text"]} !important;
    border-color: {t["input_border"]} !important;
    border-radius: 8px !important;
}}
[data-testid="stRadio"] label {{ color: {t["text"]} !important; }}
.stCaption {{ color: {t["text_muted"]} !important; }}
[data-testid="stForm"] {{ border-color: {t["divider"]} !important; }}
input::placeholder, textarea::placeholder {{ color: {t["text_muted"]} !important; }}

/* ── POPOVER ────────────────────────────────────────────────────────────────── */
[data-testid="stPopover"] > div:first-child {{
    background: {t["popup_bg"]} !important;
    border: 1px solid {t["divider"]} !important;
    border-radius: 14px !important;
}}
[data-testid="stPopover"] [data-testid="stTextInput"] input {{
    font-size: 0.9rem !important;
}}
[data-testid="stPopover"] .stButton button {{
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
}}
[data-testid="stSidebar"] [data-testid="stPopover"] {{
    position: relative !important;
    z-index: 100 !important;
}}
[data-testid="stSidebar"] [data-testid="stPopover"] > div:first-child {{
    max-height: 70vh !important;
    overflow-y: auto !important;
}}

/* ── NOTIFICATION ───────────────────────────────────────────────────────────── */
[data-testid="stNotification"] > div {{
    background: {t["popup_bg"]} !important;
    color: {t["text"]} !important;
}}

/* ── SPINNER ────────────────────────────────────────────────────────────────── */
.stSpinner > div {{ border-color: {t["accent"]} transparent transparent transparent !important; }}

/* ── ALERT ──────────────────────────────────────────────────────────────────── */
.stAlert {{
    background: {t["popup_bg"]} !important;
    border-color: {t["divider"]} !important;
    color: {t["text"]} !important;
    border-radius: 12px !important;
}}

/* ── CODE ───────────────────────────────────────────────────────────────────── */
.stCode, .stCodeBlock, code {{
    background: {t["surface"]} !important;
    color: {t["text"]} !important;
    border-color: {t["divider"]} !important;
    border-radius: 10px !important;
}}

/* ── EXPANDER ───────────────────────────────────────────────────────────────── */
.stExpander {{
    border: 1px solid {t["divider"]} !important;
    border-radius: 12px !important;
}}
.stExpander details summary {{
    color: {t["text_sub"]} !important;
    font-size: 0.85rem !important;
}}
.stExpander details {{ border-color: {t["divider"]} !important; }}

/* ── TABS ───────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{ background: {t["surface"]} !important; }}
.stTabs [data-baseweb="tab"] {{ color: {t["text_sub"]} !important; }}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{ color: {t["accent"]} !important; }}

/* ── DIVIDER ────────────────────────────────────────────────────────────────── */
hr, .stDivider {{ border-color: {t["divider"]} !important; }}

/* ── FEEDBACK BUTTONS: refined pill style ───────────────────────────────────── */
.stChatMessage .stButton button {{
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    padding: 0.28rem 0.6rem !important;
    font-size: 0.84rem !important;
    line-height: 1 !important;
    min-height: 30px !important;
    transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
}}
.stChatMessage .stButton button:hover {{
    background: rgba(255,255,255,0.05) !important;
    border-color: rgba(255,255,255,0.18) !important;
}}
[data-testid="stChatMessage"] [data-testid="column"] {{
    padding: 0 2px !important;
}}

/* ── SCROLLBAR ──────────────────────────────────────────────────────────────── */
.st-emotion-cache {{ scrollbar-width: thin; }}
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{
    background: {t["divider"]};
    border-radius: 3px;
}}
::-webkit-scrollbar-thumb:hover {{ background: {t["text_muted"]}; }}

/* ── LOGIN FORM: clean Gemini-style primary button ─────────────────────────── */
[data-testid="stForm"] button[kind="primary"] {{
    background: {t["accent"]} !important;
    border: none !important;
    color: white !important;
    border-radius: 12px !important;
    font-weight: 500 !important;
    transition: all 0.18s ease;
    box-shadow: none !important;
}}
[data-testid="stForm"] button[kind="primary"]:hover {{
    background: {t["accent_secondary"]} !important;
}}

/* ── EMPTY STATE ────────────────────────────────────────────────────────────── */
.st-emotion-cache-1h77w2v {{ color: {t["text"]} !important; }}

/* ── BUTTON RESET ───────────────────────────────────────────────────────────── */
.stButton > button {{
    background: transparent !important;
    border-color: {t["divider"]} !important;
    color: {t["text"]} !important;
}}
div[data-testid="stVerticalBlock"] {{
    background: transparent !important;
}}

/* ── GEMINI-STYLE FULL-SCREEN PANEL ──────────────────────────────────────────── */
.gemini-panel-overlay {{
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    backdrop-filter: blur(2px);
    z-index: 2000;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    animation: geminiFadeIn 0.25s ease forwards;
    pointer-events: none;
}}
.gemini-panel {{
    width: 100%;
    max-width: 720px;
    height: 100vh;
    background: {t["app_bg"]} !important;
    border-right: 1px solid {t["divider"]};
    border-left: 1px solid {t["divider"]};
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: geminiSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    pointer-events: auto;
}}
.gemini-panel-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.1rem 1.25rem;
    border-bottom: 1px solid {t["divider"]};
    background: {t["app_bg"]} !important;
    flex: 0 0 auto;
}}
.gemini-panel-title {{
    font-size: 1.15rem !important;
    font-weight: 500 !important;
    color: {t["text"]} !important;
    margin: 0 !important;
    letter-spacing: -0.01em;
}}
.gemini-panel-close {{
    background: transparent !important;
    border: 1px solid {t["divider"]} !important;
    border-radius: 12px !important;
    color: {t["text_sub"]} !important;
    width: 38px !important;
    height: 38px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
    font-size: 1.1rem !important;
    transition: all 0.15s ease;
    cursor: pointer;
}}
.gemini-panel-close:hover {{
    border-color: {t["text_muted"]} !important;
    color: {t["text"]} !important;
    background: {t["sidebar_hover"]} !important;
}}
.gemini-panel-body {{
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 1.25rem;
    background: {t["app_bg"]} !important;
}}
.gemini-panel-body p,
.gemini-panel-body li,
.gemini-panel-body span,
.gemini-panel-body h3,
.gemini-panel-body h4 {{
    color: {t["text"]} !important;
}}
.gemini-panel-body .muted {{
    color: {t["text_sub"]} !important;
}}
.gemini-panel-card {{
    background: {t["surface"]} !important;
    border: 1px solid {t["divider"]};
    border-radius: 16px;
    padding: 1.1rem;
    margin-bottom: 0.85rem;
    transition: all 0.2s ease;
}}
.gemini-panel-card:hover {{
    border-color: {t["text_muted"]};
}}
.gemini-panel-card h4 {{
    margin: 0 0 0.5rem;
    font-size: 0.95rem;
    font-weight: 500;
    color: {t["text"]} !important;
}}
.gemini-panel-card p {{
    margin: 0;
    font-size: 0.86rem;
    line-height: 1.6;
    color: {t["text_sub"]} !important;
}}

@keyframes geminiFadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
}}
@keyframes geminiSlideIn {{
    from {{ opacity: 0; transform: translateX(-32px); }}
    to {{ opacity: 1; transform: translateX(0); }}
}}
@keyframes geminiSlideOut {{
    from {{ opacity: 1; transform: translateX(0); }}
    to {{ opacity: 0; transform: translateX(-32px); }}
}}
.gemini-panel.closing {{
    animation: geminiSlideOut 0.2s ease forwards;
}}

/* ── RESPONSIVE ─────────────────────────────────────────────────────────────── */
@media (max-width: 480px) {{
    .block-container {{
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        padding-top: 0.75rem !important;
        padding-bottom: 5rem !important;
        max-width: 100vw !important;
        min-height: calc(100vh - 0.5rem);
    }}
    .greeting {{
        padding: 2.5rem 0.6rem 1rem !important;
    }}
    .greeting h2 {{
        font-size: 1.3rem !important;
    }}
    .greeting .sub {{
        font-size: 0.84rem;
    }}
    .greeting .greeting-sub {{
        font-size: 0.82rem;
        max-width: 90vw;
    }}
    [data-testid="stChatInput"] {{
        border-radius: 24px !important;
        padding: 0.4rem 0.5rem 0.4rem 0.85rem !important;
        min-height: 46px !important;
        margin-top: 0.3rem !important;
    }}
    [data-testid="stChatInput"] button[data-testid*="submit"],
    [data-testid="stChatInput"] button[aria-label*="send" i],
    [data-testid="stChatInput"] button[kind="primary"] {{
        width: 30px !important;
        height: 30px !important;
        min-width: 30px !important;
        max-width: 30px !important;
        border-radius: 50% !important;
        margin: 0 1px 0 3px !important;
    }}
    [data-testid="stChatInputTextArea"] {{
        font-size: 0.9rem !important;
    }}
    /* Mobile: 고정 입력창 하단 배치 + 콘텐츠 여백 */
    .main:has(.greeting) [data-testid="stBottomBlockContainer"] {{
        bottom: 0 !important;
        padding: 0.6rem 0.65rem 1rem !important;
        max-width: 100vw !important;
    }}
    .main:has(.greeting) .greeting {{
        padding-bottom: 5rem !important;
    }}
    .main:has(.greeting) .prompt-chips {{
        gap: 7px;
        padding: 0.2rem 0.4rem 6rem !important;
    }}
    .stChatMessage {{
        font-size: 0.88rem !important;
    }}
    [data-testid="stChatMessageContent"] {{
        padding: 0.7rem 0.85rem !important;
        border-radius: 14px !important;
    }}
    [data-testid="stSidebar"] .stButton button {{
        font-size: 0.68rem !important;
        padding: 8px 4px !important;
        min-height: 40px !important;
        width: 44px !important;
        max-width: 44px !important;
        min-width: 44px !important;
        margin-bottom: 2px !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPopover"] > div:first-child {{
        max-height: 55vh !important;
        max-width: 260px !important;
    }}
    .gemini-panel {{
        max-width: 100% !important;
        border-left: none !important;
        border-right: none !important;
    }}
    .gemini-panel-header {{
        padding: 0.9rem 1rem;
    }}
    .gemini-panel-body {{
        padding: 1rem;
    }}
    .prompt-chip {{
        padding: 0.48rem 0.85rem;
        font-size: 0.81rem;
        border-radius: 20px;
    }}
    .topbar {{
        padding: 0.5rem 0.8rem;
    }}
}}

/* ── iPad 전용 반응형 (768px ~ 1024px) ────────────────────────────────── */
@media (min-width: 481px) and (max-width: 1024px) {{
    .block-container {{
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-bottom: 5rem !important;
        max-width: 680px;
    }}
    .greeting {{
        padding: 3.5rem 1rem 1.5rem !important;
    }}
    .greeting h2 {{
        font-size: 1.6rem !important;
    }}
    .greeting .sub {{
        font-size: 0.9rem !important;
        max-width: 480px;
    }}
    .greeting .greeting-sub {{
        font-size: 0.86rem;
        max-width: 460px;
    }}
    .prompt-chips {{
        gap: 10px;
        padding: 0.3rem 1rem 1.5rem;
        max-width: 680px;
    }}
    .prompt-chip {{
        padding: 0.55rem 1rem;
        font-size: 0.84rem;
        border-radius: 22px;
    }}
    .stChatMessage {{
        font-size: 0.93rem !important;
    }}
    [data-testid="stChatMessageContent"] {{
        padding: 0.8rem 0.95rem !important;
        border-radius: 16px !important;
    }}
    [data-testid="stChatInput"] {{
        border-radius: 26px !important;
        padding: 0.45rem 0.55rem 0.45rem 0.95rem !important;
        min-height: 50px !important;
    }}
    [data-testid="stChatInput"] button[data-testid*="submit"],
    [data-testid="stChatInput"] button[aria-label*="send" i],
    [data-testid="stChatInput"] button[kind="primary"] {{
        width: 32px !important;
        height: 32px !important;
        min-width: 32px !important;
        max-width: 32px !important;
    }}
    .main:has(.greeting) [data-testid="stBottomBlockContainer"] {{
        padding: 0.7rem 1.5rem 1rem !important;
        max-width: 680px !important;
    }}
    .main:has(.greeting) .greeting {{
        padding-bottom: 5.5rem !important;
    }}
    .main:has(.greeting) .prompt-chips {{
        padding-bottom: 6.5rem !important;
    }}
    .gemini-panel {{
        max-width: 680px !important;
    }}
    .gemini-panel-header {{
        padding: 1rem 1.15rem;
    }}
    .gemini-panel-body {{
        padding: 1.15rem;
    }}
    .gemini-panel-card {{
        padding: 1rem;
        margin-bottom: 0.75rem;
    }}
    [data-testid="stSidebar"] .stButton button {{
        font-size: 0.7rem !important;
        padding: 0.55rem 0.4rem !important;
        min-height: 44px !important;
        width: 50px !important;
        max-width: 50px !important;
        min-width: 50px !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPopover"] > div:first-child {{
        max-height: 60vh !important;
        max-width: 280px !important;
    }}
    /* 사이드바 메뉴 버튼 — iPad 터치 영역 */
    [data-testid="stSidebar"] .stButton button {{
        min-height: var(--touch-target-min, 44px) !important;
    }}
    /* 패널 스와이프 영역 보장 */
    [data-st-key="gemini_panel_container"] {{
        -webkit-user-select: none;
        user-select: none;
    }}
    /* 데이터 테이블 — iPad 수평 스와이프 */
    [data-testid="stDataFrame"], .stTable {{
        -webkit-overflow-scrolling: touch !important;
    }}
}}
/* ── 레이아웃 정돈: 데스크톱에서 채팅+랭킹 2칼럼 폭 확보 ── */
@media (min-width:1025px){{
    .block-container{{ max-width:980px !important; }}
}}
/* 반응형: 모바일/좁은 화면에서 칼럼 세로 스택(랭킹이 채팅 아래로) */
@media (max-width:820px){{
    [data-testid="stHorizontalBlock"]{{ flex-wrap:wrap !important; }}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{{ min-width:100% !important; flex:1 1 100% !important; }}
}}

/* ── 실시간 질문 랭킹 (centered card, elegant design) ── */
/* 설계 원칙: 순위 변동 ▲▼ 배지, 메달 이모지, 카드형 레이아웃.
   모노크롬 다크 베이스 + 미니멀 액센트. 12시간 자동 갱신. */

.rank-center-header {{
    display: flex; align-items: baseline; gap: 10px;
    margin-bottom: 8px; padding: 0 4px;
}}
.rank-center-icon {{ font-size: 1.25rem; }}
.rank-center-title {{
    font-weight: 700; font-size: 1rem; color: {t["text"]};
    letter-spacing: .02em;
}}
.rank-center-sub {{
    font-size: .72rem; color: {t["text_muted"]}; opacity: .55;
    margin-left: auto;
}}

.rank-center-panel {{
    background: {t["surface"]};
    border: 1px solid {t["divider"]};
    border-radius: 14px;
    padding: 8px 12px;
    margin-bottom: 12px;
    max-width: 680px;
    margin-left: auto; margin-right: auto;
}}
.rank-center-list {{
    display: flex; flex-direction: column;
}}

.rank-center-item {{
    display: flex; align-items: center; gap: 10px;
    padding: 9px 10px;
    border-radius: 10px;
    cursor: pointer;
    transition: background .15s ease, transform .12s ease;
    border: 1px solid transparent;
}}
.rank-center-item:hover {{
    background: {t["chip_hover"]};
    border-color: {t["divider"]};
    transform: translateX(2px);
}}
.rank-center-item + .rank-center-item {{
    border-top: 1px solid {t["divider"]};
}}

.rank-center-top3 {{
    background: linear-gradient(90deg, {t["accent_glow"]} 0%, transparent 60%);
}}

.rank-center-pos {{
    display: flex; align-items: center; gap: 4px;
    min-width: 52px; flex: 0 0 auto;
}}
.rank-center-num {{
    font-weight: 700; font-size: .85rem; color: {t["text_muted"]};
    opacity: .55; min-width: 18px; text-align: center;
}}
.rank-center-top3 .rank-center-num {{
    color: {t["text_sub"]}; opacity: .85;
}}

.rank-center-q {{
    flex: 1; min-width: 0;
    font-size: .84rem; color: {t["accent_secondary"]};
    line-height: 1.45; word-break: break-word; overflow-wrap: anywhere;
    display: block;
}}
.rank-center-q:hover {{
    color: {t["text"]}; text-decoration: underline;
}}

.rank-center-meta {{
    display: flex; align-items: center; gap: 8px;
    flex: 0 0 auto; margin-left: auto;
}}
.rank-center-cnt {{
    font-size: .68rem; color: {t["text_muted"]}; opacity: .45;
    white-space: nowrap;
}}

/* ── 순위 변동 뱃지 ── */
.rank-chg-badge {{
    font-size: .68rem; font-weight: 700; padding: 2px 7px;
    border-radius: 6px; white-space: nowrap;
    letter-spacing: .02em;
}}
.rank-chg-up {{
    color: #4ade80; background: rgba(74, 222, 128, 0.1);
    border: 1px solid rgba(74, 222, 128, 0.2);
}}
.rank-chg-down {{
    color: #f87171; background: rgba(248, 113, 113, 0.1);
    border: 1px solid rgba(248, 113, 113, 0.2);
}}
.rank-chg-stable {{
    color: {t["text_muted"]}; background: rgba(106, 106, 106, 0.1);
    border: 1px solid rgba(106, 106, 106, 0.15);
    opacity: .5;
}}
.rank-chg-new {{
    color: #60a5fa; background: rgba(96, 165, 250, 0.1);
    border: 1px solid rgba(96, 165, 250, 0.2);
}}

.rank-center-empty {{
    font-size: .78rem; color: {t["text_muted"]};
    padding: 28px 4px; text-align: center; opacity: .45;
    max-width: 680px; margin: 0 auto;
}}

.rank-center-updated {{
    font-size: .60rem; color: {t["text_muted"]}; opacity: .35;
    text-align: right; padding: 4px 8px 0;
    max-width: 680px; margin: 0 auto;
}}

/* 데스크톱 랭킹 카드 최대 폭 */
@media (min-width:1025px){{
    .rank-center-panel {{ max-width: 680px; }}
    .rank-center-empty {{ max-width: 680px; }}
    .rank-center-updated {{ max-width: 680px; }}
}}
/* 모바일(≤820px): 카드 풀폭, 메타 축소 */
@media (max-width:820px){{
    .rank-center-panel {{
        max-width: 100%; border-radius: 10px; padding: 6px 8px;
    }}
    .rank-center-item {{ gap: 6px; padding: 7px 6px; }}
    .rank-center-pos {{ min-width: 40px; }}
    .rank-center-q {{ font-size: .78rem; }}
    .rank-center-cnt {{ display: none; }}
    .rank-chg-badge {{ font-size: .62rem; padding: 1px 5px; }}
}}

/* ── 사이드바 반응형 고정 (72px 슬림 아이콘 레일 유지) ── */
/* 데스크톱: 항상 펼침 + 접기 버튼 숨김(사용자가 접어서 사라지는 문제 방지) */
@media (min-width:1025px){{
    section[data-testid="stSidebar"]{{ min-width:72px !important; max-width:72px !important; width:72px !important; }}
    section[data-testid="stSidebar"][aria-expanded="false"]{{ transform:none !important; margin-left:0 !important; visibility:visible !important; }}
    section[data-testid="stSidebar"][aria-expanded="false"] > div{{ transform:none !important; visibility:visible !important; }}
    button[data-testid="stSidebarCollapseButton"]{{ display:none !important; }}
}}
/* 모바일/태블릿: 접기 허용 + 다시 여는 확장 버튼 항상 노출(못 여는 문제 방지) */
@media (max-width:1024px){{
    [data-testid="stSidebarCollapsedControl"]{{ display:flex !important; visibility:visible !important; opacity:1 !important; z-index:9999 !important; }}
}}

</style>
""",
        unsafe_allow_html=True,
    )


_inject_css(_T)


# ══════════════════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ══════════════════════════════════════════════════════════════════════════════

def _httpx_request_with_retry(fn, max_retries: int = 2, retry_delay: float = 1.0):
    """httpx 요청 재시도 래퍼 — 연결 오류 및 5xx 상태 코드에만 재시도."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except httpx.ConnectError:
            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise


def _send_feedback(iid: str, val: int) -> bool:
    """BUG-02 수정: 로그인 사용자의 auth_token을 Authorization 헤더로 전달.

    게스트(토큰 없음)는 백엔드 /feedback 이 401을 반환하므로 버튼이 무시됨.
    """
    _token = st.session_state.get("auth_token")
    if not _token:
        # 게스트는 피드백 권한 없음 — 호출하지 않고 조용히 False 반환
        return False
    try:
        _headers = {"Authorization": f"Bearer {_token}"}

        def _req():
            with httpx.Client(timeout=15) as c:
                return c.post(
                    f"{API_BASE}/feedback",
                    headers=_headers,
                    json={
                        "interaction_id": iid,
                        "value": val,
                        "user_id": st.session_state.subscriber_id,
                    },
                )
        r = _httpx_request_with_retry(_req)
        return r.status_code < 400
    except Exception:
        return False


def _save_history():
    if not st.session_state.get("remember_conversations", True):
        return # 사용자가 대화 기억을 끈 경우 저장하지 않음
    if not st.session_state.msgs:
        return
    first = next(
        (m["content"] for m in st.session_state.msgs if m["role"] == "user"), ""
    )
    if not first:
        return
    if len(st.session_state.msgs) > 100:
        stored_msgs = st.session_state.msgs[-100:]
    else:
        stored_msgs = list(st.session_state.msgs)
    st.session_state.conversations.insert(
        0,
        {
            "id": uuid.uuid4().hex,
            "title": first[:35] + ("…" if len(first) > 35 else ""),
            "messages": stored_msgs,
            "created_at": datetime.now().strftime("%m/%d %H:%M"),
        },
    )
    if len(st.session_state.conversations) > 50:
        st.session_state.conversations = st.session_state.conversations[:50]


def _new_conv():
    _close_panel()
    _save_history()
    st.session_state.msgs = []
    st.rerun()


def _load_conv(conv: dict):
    _close_panel()
    _save_history()
    st.session_state.msgs = list(conv["messages"])
    st.session_state.conversations = [c for c in st.session_state.conversations if c["id"] != conv["id"]]
    st.rerun()


def _open_panel(panel_id: str) -> None:
    """전체화면 패널 열기."""
    st.session_state.gemini_panel = panel_id
    st.rerun()


def _close_panel() -> None:
    """전체화면 패널 닫기."""
    st.session_state.gemini_panel = None
    st.rerun()


def _panel_help():
    return [
        (T("help_q1"), T("help_a1")),
        (T("help_q2"), T("help_a2")),
        (T("help_q3"), T("help_a3")),
        (T("help_q4"), T("help_a4")),
    ]


def _render_gemini_panel() -> None:
    """메인 영역에 전체화면 패널을 렌더링합니다."""
    panel_id = st.session_state.gemini_panel
    if not panel_id:
        return

    titles = {
        "history": "💬 " + T("panel_recent"),
        "help": "❓ " + T("panel_help"),
        "settings": "⚙️ " + T("panel_settings"),
    }
    if panel_id.startswith("insight:"):
        title = "🧠 " + T("panel_insight")
    else:
        title = titles.get(panel_id, T("panel_menu"))

    # ── 1. 패널 CSS + 백드롭 + 채팅 UI 숨김 ──
    st.markdown(f"""
    <style>
    /* 패널이 열려 있을 때 채팅 UI 요소 숨김 (chat_input은 DOM 유지를 위해 visibility만 숨김) */
    .greeting, .prompt-chips, .stChatMessage {{
        display: none !important;
    }}
    [data-testid="stBottomBlockContainer"] {{
        visibility: hidden !important;
        pointer-events: none !important;
    }}
    /* 어두운 백드롭 — 패널 뒤 배경을 어둡게 하여 집중도 향상 */
    .panel-backdrop {{
        position: fixed !important;
        inset: 0 !important;
        background: rgba(0,0,0,0.5) !important;
        z-index: 9998 !important;
        animation: geminiFadeIn 0.2s ease forwards;
    }}
    /* 패널 컨테이너: 화면 중앙 고정, 완전 불투명 배경, 그림자 */
    [data-st-key="gemini_panel_container"] {{
        position: fixed !important;
        top: 0 !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 9999 !important;
        width: 100% !important;
        max-width: 720px !important;
        height: 100vh !important;
        background: {_T["app_bg"]} !important;
        border-right: 1px solid {_T["divider"]} !important;
        border-left: 1px solid {_T["divider"]} !important;
        box-shadow: none !important;
        overflow-y: auto !important;
        padding: 0 !important;
        animation: geminiSlideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }}
    @media (max-width: 480px) {{
        [data-st-key="gemini_panel_container"] {{
            max-width: 100% !important;
            left: 0 !important;
            transform: none !important;
            border-left: none !important;
            border-right: none !important;
        }}
    }}
    </style>
    <div class="panel-backdrop"></div>
    """, unsafe_allow_html=True)

    # ── 2. 패널 콘텐츠 (Streamlit 위젯 사용 가능) ──
    panel = st.container(key="gemini_panel_container")
    with panel:
        # 헤더: 제목 + 닫기 버튼 (st.columns 비율 개선)
        _hdr_c1, _hdr_c2 = st.columns([8, 1])
        with _hdr_c1:
            st.markdown(
                f'<div style="padding:1.1rem 0;border-bottom:1px solid {_T["divider"]};">'
                f'<span style="font-size:1.15rem;font-weight:500;color:{_T["text"]};">{title}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with _hdr_c2:
            if st.button("✕", key="gemini_close", help=T("panel_close")):
                _close_panel()

        # 본문
        st.markdown(
            f'<div style="padding:1.25rem;flex:1 1 auto;overflow-y:auto;">',
            unsafe_allow_html=True,
        )

        if panel_id == "history":
            convs = st.session_state.conversations
            if not convs:
                st.markdown(
                    f'<div class="gemini-panel-card"><p class="muted">{T("no_history")}</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                for conv in convs[:30]:
                    with st.container():
                        st.markdown(
                            f'<div class="gemini-panel-card"><h4>{conv["title"]}</h4>'
                            f'<p class="muted">{conv["created_at"]}</p></div>',
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            T("continue_chat"),
                            key=f"ph_{conv['id']}",
                            use_container_width=True,
                        ):
                            _load_conv(conv)

        elif panel_id == "help":
            for h_title, body in _panel_help():
                st.markdown(
                    f'<div class="gemini-panel-card"><h4>{h_title}</h4><p>{body}</p></div>',
                    unsafe_allow_html=True,
                )

        elif panel_id.startswith("insight:"):
            _sid = panel_id.split(":", 1)[1]
            st.markdown(
                f'<div class="gemini-panel-card">'
                        f'<h4>🧠 {T("panel_insight")}</h4>'
                        f'<p class="muted">{T("insight_sub")}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
            try:
                with httpx.Client(timeout=15) as _ic:
                    _ir = _ic.get(f"{API_BASE}/insight/{_sid}")
                    if _ir.status_code < 400:
                        _data = _ir.json()
                        _q = _data.get("question", "?")
                        _stats = _data.get("question_stats", {})
                        _sections = _data.get("insight_sections", {})

                        # 질문 + 통계
                        st.markdown(
                            f'<div class="gemini-panel-card">'
                            f'<p style="font-size:1.05rem;font-weight:500;">{_q}</p>'
                            f'<p class="muted">📊 {_stats.get("total_count", 0)}회 질문됨 · '
                            f'👍 {_stats.get("positive_feedback", 0)} · '
                            f'점수 {_stats.get("trend_score", 0):.0f}</p>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # 통찰 섹션
                        for _sec_key, _sec_label in [
                            ("root_cause", "🔍 " + T("sec_root_cause")),
                            ("ai_diagnosis", "🩺 " + T("sec_ai_diagnosis")),
                            ("best_answer_why", "💡 " + T("sec_best_why")),
                            ("reflection", "🙏 " + T("sec_reflection")),
                        ]:
                            _sec_content = _sections.get(_sec_key)
                            if _sec_content:
                                with st.expander(_sec_label, expanded=(_sec_key == "root_cause")):
                                    st.markdown(_sec_content)

                        # 베스트 답변
                        _best = _sections.get("best_answer")
                        if _best:
                            with st.expander("✨ " + T("best_answer"), expanded=True):
                                st.markdown(_best.get("text", ""))
                                st.caption(_best.get("why", ""))
                    else:
                        st.warning(T("insight_data_err"))
            except Exception:
                st.warning(T("insight_conn_err"))

        elif panel_id == "settings":
            # ── 계정 정보 ──
            _logged = bool(st.session_state.auth_token)
            _name = st.session_state.get("user_display_name") or "게스트"
            _sub = st.session_state.subscriber_id

            st.markdown(
                f'<div class="gemini-panel-card">'
                f'<h4>👤 {T("account_info")}</h4>'
                f'<p>{T("login_status")}: {T("logged_in") if _logged else T("not_logged_in")}</p>'
                f'<p>{T("display_name")}: {_name}</p>'
                f'<p style="font-size:0.78rem;color:{_T["text_muted"]};">ID: {_sub}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if _logged:
                if st.button(T("logout"), key="panel_logout", use_container_width=True):
                    _save_history()
                    st.session_state.auth_token = None
                    st.session_state.user_display_name = None
                    _close_panel()
            else:
                if st.button(
                    T("go_login_signup"),
                    key="panel_login",
                    use_container_width=True,
                ):
                    _close_panel()
                    st.toast(T("login_toast"))

            st.markdown(
                '<hr style="border-color:#30363d;margin:1.2rem 0;">',
                unsafe_allow_html=True,
            )

            # ── 대화 설정 ──
            st.markdown(
                f'<h4 style="color:{_T["text"]};margin:0 0 0.5rem;">💬 {T("chat_settings")}</h4>',
                unsafe_allow_html=True,
            )

            remember = st.toggle(
                T("remember_conv"),
                value=st.session_state.remember_conversations,
                key="toggle_remember",
                help=T("remember_help"),
            )
            st.session_state.remember_conversations = remember
            st.caption(T("remember_caption"))

            st.markdown(
                '<hr style="border-color:#30363d;margin:1.2rem 0;">',
                unsafe_allow_html=True,
            )

            # ── 나의 정보 설정 (Gemini 스타일) ──
            st.markdown(
                f'<h4 style="color:{_T["text"]};margin:0 0 0.5rem;">'
                f'📝 {T("my_info")}</h4>',
                unsafe_allow_html=True,
            )
            st.caption(T("my_info_desc"))

            saved_info = st.text_area(
                T("remember_info_label"),
                value=st.session_state.saved_user_info,
                key="saved_info_input",
                height=160,
                placeholder=T("remember_info_ph"),
                label_visibility="collapsed",
            )
            st.session_state.saved_user_info = saved_info

            if saved_info.strip():
                st.success(T("saved_ok"))
            else:
                st.info(T("saved_info"))

            # 초기화 버튼
            if saved_info.strip():
                _, _reset_col = st.columns([3, 1])
                with _reset_col:
                    if st.button(T("reset"), key="reset_saved_info", use_container_width=True):
                        st.session_state.saved_user_info = ""
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True) # 본문 패딩 div 닫기

    # 패널이 열린 상태에서는 아래 채팅 UI를 숨기기 위해 중단
    st.stop()



# ══════════════════════════════════════════════════════════════════════════════
# 모드 분기 (관리자 모드는 ?admin 쿼리 파라미터로 진입)
# ══════════════════════════════════════════════════════════════════════════════
if "admin" in st.query_params and st.session_state.mode == "chat":
    if APP_PASSWORD and APP_PASSWORD != "change-me":
        st.session_state.mode = "admin_login"
    else:
        st.session_state.mode = "admin"
        st.session_state.auth_ok = True

_mode = st.session_state.mode # "chat" | "admin_login" | "admin"

# ── iPad Safari 스와이프 & 터치 최적화 주입 ────────────────────────────
inject_ipad_optimizations(include_admin_js=(_mode == "admin"))


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
            st.Page("admin/pages/1_📚_Library.py", title="자료실", icon="📚"),
            st.Page("admin/pages/2_📥_Upload.py", title="자료 업로드", icon="📥"),
            st.Page("admin/pages/11_🎵_미디어업로드.py", title="미디어 업로드", icon="🎵"),
            st.Page("admin/pages/13_📖_성경관리.py", title="콘텐츠 관리", icon="📜"),
            st.Page("admin/pages/3_🔎_Search.py", title="검색 테스트", icon="🔎"),
            st.Page("admin/pages/14_📚_용어집.py", title="용어집", icon="📖"),
            st.Page("admin/pages/15_📥_자료흐름.py", title="자료 흐름", icon="🔄"),
        ],
        "모니터링": [
            st.Page("admin/pages/4_📊_Status.py", title="상태 모니터", icon="📊"),
            st.Page("admin/pages/5_💭_대화기록.py", title="대화 기록", icon="💭"),
        ],
        "시스템": [
            st.Page("admin/pages/6_📝_프롬프트.py", title="프롬프트", icon="📝"),
            st.Page("admin/pages/7_🏷_분류관리.py", title="분류 관리", icon="🏷"),
            st.Page("admin/pages/9_👥_사람.py", title="사람", icon="👥"),
            st.Page("admin/pages/10_⚙️_설정.py", title="설정", icon="⚙️"),
        ],
    }

    # --- Admin 사이드바 하단 버튼 ---
    with st.sidebar:
        st.markdown("---")
        if st.button(
            "💬 " + T("admin_chat_back"),
            key="back_to_chat",
            use_container_width=True,
            help=T("admin_chat_back_help"),
        ):
            st.session_state.mode = "chat"
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
        if st.button(T("admin_back"), key="cancel_login", use_container_width=True):
            st.session_state.mode = "chat"
            st.rerun()

    st.markdown("---")
    st.markdown(f"### {T('admin_auth')}")
    st.caption(T("admin_caption"))
    with st.form("admin_login_form"):
        pw = st.text_input(T("password"), type="password", placeholder=T("password"))
        col_ok, col_cancel = st.columns([1, 1])
        with col_ok:
            submitted = st.form_submit_button(T("admin_confirm"), type="primary", use_container_width=True)
        with col_cancel:
            cancel_clicked = st.form_submit_button(T("admin_cancel"), use_container_width=True)
        if cancel_clicked:
            st.session_state.mode = "chat"
            st.rerun()
        if submitted:
            if hmac.compare_digest(pw, APP_PASSWORD):
                st.session_state.mode = "admin"
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error(T("admin_pw_wrong"))
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# ③ 채팅 모드 (기본)
# ══════════════════════════════════════════════════════════════════════════════

# ── 사이드바 ────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── 언어 전환 (지구본 단일 버튼: KO → ZH → EN) ──
    _cur_lang = st.session_state.get("target_lang", "ko")
    if _cur_lang not in UI_LANGS:
        _cur_lang = "ko"
    _picked = _render_lang_globe(_cur_lang)
    if _picked is not None and _picked in UI_LANGS and _picked != _cur_lang:
        st.session_state.target_lang = _picked
        st.rerun()
    st.markdown("---")

    # 새 대화 버튼
    st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
    if st.button("✨", key="btn_new", help=T("new_chat"), use_container_width=True):
        _new_conv()
    st.markdown("</div>", unsafe_allow_html=True)

    # Gemini 스타일 메뉴 — 아이콘 레일 (narrow sidebar용)
    if st.button("💬", key="menu_history", help=T("recent"), use_container_width=True):
        _open_panel("history")
    if st.button("❓", key="menu_help", help=T("help"), use_container_width=True):
        _open_panel("help")
    if st.button("⚙️", key="menu_settings", help=T("settings"), use_container_width=True):
        _open_panel("settings")

    # 대화 기록
    convs = st.session_state.conversations
    if convs:
        st.markdown(
            f'<p class="sidebar-section-label">{T("recent")}</p>',
            unsafe_allow_html=True,
        )
        for conv in convs[:30]:
            if st.button(
                conv["title"], key=f"h_{conv['id']}", use_container_width=True
            ):
                _load_conv(conv)

    # 하단 — 계정 + 긴급 전화
    _logged_in = bool(st.session_state.auth_token)
    _uname = st.session_state.get("user_display_name") or ""

    st.markdown("---")
    if _logged_in and _uname:
        if st.button("👤", key="btn_logout_sb", help=f"{_uname} · {T('logout')}", use_container_width=True):
            _save_history()
            st.session_state.auth_token = None
            st.session_state.user_display_name = None
            st.rerun()
    else:
        with st.popover("👤", use_container_width=True):
            _t = st.radio(T("login") + "/" + T("signup"), [T("login"), T("signup")], horizontal=True, key="auth_tab", label_visibility="collapsed")
            if _t == T("login"):
                _lem = st.text_input(T("email"), key="li_em", placeholder=T("email"), label_visibility="collapsed")
                _lpw = st.text_input(T("password"), key="li_pw", type="password", placeholder=T("password"), label_visibility="collapsed")
                if st.button(T("login"), key="btn_login", use_container_width=True):
                    if _lem and _lpw:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/login", json={"email": _lem, "password": _lpw})
                            if r.status_code < 400:
                                d = r.json()
                                st.session_state.auth_token = d["token"]
                                st.session_state.subscriber_id = d["sub_id"]
                                # BUG-05 수정: 백엔드 display_name 우선, 없으면 이메일 접두사 폴백
                                st.session_state.user_display_name = (
                                    d.get("display_name") or _lem.split("@")[0]
                                )
                                st.rerun()
                            else:
                                st.error(T("login_err"))
                        except Exception as e:
                            st.error(f"오류: {e}")
            else:
                _em = st.text_input(T("email"), key="su_em", placeholder=T("email"), label_visibility="collapsed")
                _pw = st.text_input(T("password"), key="su_pw", type="password", placeholder=T("password") + " (8+)", label_visibility="collapsed")
                _nm = st.text_input(T("name"), key="su_nm", placeholder=T("name"), label_visibility="collapsed")
                if st.button(T("signup"), key="btn_signup", use_container_width=True):
                    if _em and _pw:
                        try:
                            with httpx.Client(timeout=15) as c:
                                r = c.post(f"{API_BASE}/auth/signup", json={"email": _em, "password": _pw, "display_name": _nm or None, "guest_sub_id": st.session_state.subscriber_id})
                            if r.status_code < 400:
                                d = r.json()
                                st.session_state.auth_token = d["token"]
                                st.session_state.subscriber_id = d["sub_id"]
                                st.session_state.user_display_name = _nm or _em.split("@")[0]
                                st.success(T("signup_done"))
                                st.rerun()
                            else:
                                st.error(r.json().get("detail", "가입 실패"))
                        except Exception as e:
                            st.error(f"오류: {e}")
                    else:
                        st.warning(T("enter_email_pw"))


# ── 상단 바: Gemini-style user avatar + settings ─────────────────────────
_logged_in = bool(st.session_state.auth_token)
_uname = st.session_state.get("user_display_name") or "U"
_user_initial = _uname[0].upper() if _uname else "U"
st.markdown(
    f"""
<div class="topbar">
  <button class="topbar-settings" id="topbar-settings-btn" title="{T('settings')}" aria-label="{T('settings')}">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
  </button>
  <button class="topbar-user" id="topbar-user-btn" title="{_uname}">{_user_initial}</button>
</div>
""",
    unsafe_allow_html=True,
)

# ── Gemini 스타일 전체화면 패널 ───────────────────────────────────────────
_render_gemini_panel()

# ── 상단 바 버튼 + 사이드바 토글 동기화 ─────────────────────────────────────
# 주의: st.markdown(unsafe_allow_html=True) 는 프론트엔드 DOMPurify 로 sanitize
# 되어 <script>/onclick 가 제거됨. 인라인 JS 는 반드시 components.html (iframe,
# 미 sanitize) 로 주입해야 하며, 부모 DOM 접근은 window.parent.document 로 처리.
_injector_html = """
<style>html,body{margin:0;padding:0;height:0;overflow:hidden;}</style>
<script>
(function(){
  function q(sel){ try { return window.parent.document.querySelector(sel); } catch(e){ return null; } }
  function byId(id){ try { return window.parent.document.getElementById(id); } catch(e){ return null; } }
  function bind(){
    var s=byId('topbar-settings-btn');
    if(s && !s._tb){ s._tb=1; s.addEventListener('click', function(){
      var b=q('[data-testid="stSidebar"] button[key="menu_settings"]'); if(b) b.click();
    }); }
    var u=byId('topbar-user-btn');
    if(u && !u._tb){ u._tb=1; u.addEventListener('click', function(){
      var p=q('[data-testid="stSidebar"] [data-testid="stPopover"] > button');
      if(p){ p.click(); } else { var lo=q('[key="btn_logout_sb"]'); if(lo) lo.click(); }
    }); }
    var sidebar=q('[data-testid="stSidebar"]');
    var toggle=q('[data-testid="stSidebarCollapsedControl"]');
    if(toggle){
      var expanded = sidebar && sidebar.getAttribute('aria-expanded')==='true';
      toggle.style.display = expanded ? 'none' : 'flex';
      toggle.style.visibility = expanded ? 'hidden' : 'visible';
    }
  }
  // 프롬프트 칩 클릭 위임 (data-q 값을 입력창에 주입)
  function bindChips(){
    var pd=window.parent.document;
    if(!pd || pd._chipBound) return;
    pd._chipBound=1;
    pd.addEventListener('click', function(ev){
      var chip = ev.target && ev.target.closest ? ev.target.closest('.prompt-chip') : null;
      if(!chip) return;
      var qval = chip.getAttribute('data-q');
      var t = q('[data-testid=stChatInputTextArea]');
      if(t && qval!=null){ t.value=qval; t.dispatchEvent(new Event('input',{bubbles:true})); t.focus(); }
    });
  }
  bind();
  bindChips();
  // 방어적 제거: 브라우저 확장 프로그램 등 외부가 주입한 "가입 혜택" 요소 자동 삭제
  (function stripInjected(){
    var pd=window.parent.document;
    if(!pd) return;
    var targets=['가입 혜택','가입혜택','회원 가입','무료 가입','지금 가입'];
    function clean(){
      var all=pd.querySelectorAll('*');
      for(var i=0;i<all.length;i++){
        var t=(all[i].textContent||'').trim();
        for(var j=0;j<targets.length;j++){
          if(t===targets[j]||t.indexOf(targets[j])===0){ all[i].remove(); break; }
        }
      }
    }
    clean();
    setInterval(clean, 3000);
  })();
  var t=setInterval(function(){ bind(); bindChips(); }, 400);
  setTimeout(function(){ clearInterval(t); }, 8000);
})();
</script>
"""
def _render_question_ranking():
    """정중앙 랭킹 패널 — 카드형 디자인, 순위 변동 표시, 12시간 캐시 자동 갱신.

    - interaction 테이블을 백엔드가 실시간 집계한 순위를 노출
    - 항목 클릭 시 추천 칩과 동일 메커니즘(.prompt-chip + data-q)으로 채팅 입력창에 주입
    - 12시간 TTL 캐시로 불필요한 API 호출 방지
    """
    import time as _time

    CACHE_TTL = 12 * 3600  # 12시간
    _now_ts = _time.time()

    # ── 12시간 캐시: session_state 에 ranking 데이터 보관 ──
    if "ranking_cache" not in st.session_state:
        st.session_state.ranking_cache = {"data": None, "fetched_at": 0}
    _cache = st.session_state.ranking_cache

    _rank = _cache.get("data")
    if _rank is None or (_now_ts - _cache.get("fetched_at", 0)) > CACHE_TTL:
        try:
            with httpx.Client(timeout=8) as _rc:
                _rr = _rc.get(f"{API_BASE}/ranking/questions?limit=10&period=7d")
                _rank = _rr.json().get("rankings", []) if _rr.status_code < 400 else []
        except Exception:
            _rank = _cache.get("data") or []  # 폴백: 기존 캐시 유지
        else:
            _cache["data"] = _rank
            _cache["fetched_at"] = _now_ts

    # ── 주간 메시지 캐시 (1시간 TTL, 어드민에서 변경 즉시 반영 희망 시 새로고침) ──
    if "greeting_sub_cache" not in st.session_state:
        st.session_state.greeting_sub_cache = {"msg": "", "fetched_at": 0, "lang": ""}
    _gsc = st.session_state.greeting_sub_cache
    if (
        _gsc.get("lang") != target_lang
        or (_now_ts - _gsc.get("fetched_at", 0)) > 3600
    ):
        try:
            with httpx.Client(timeout=4) as _gc:
                _gr = _gc.get(f"{API_BASE}/chat/greeting-sub?lang={target_lang}")
                if _gr.status_code < 400:
                    _gsc["msg"] = _gr.json().get("greeting_sub", "")
                else:
                    _gsc["msg"] = ""
        except Exception:
            _gsc["msg"] = ""  # API 실패 시 빈 문자열
        _gsc["fetched_at"] = _now_ts
        _gsc["lang"] = target_lang

    st.session_state.greeting_sub_msg = _gsc.get("msg", "")

    # ── 헤더 ──
    st.markdown(
        f'<div class="rank-center-header">'
        f'<span class="rank-center-icon">📊</span>'
        f'<span class="rank-center-title">{T("ranking_title")}</span>'
        f'<span class="rank-center-sub">{T("ranking_sub")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 새로고침 버튼 (캐시 무시하고 즉시 갱신) ──
    _refresh_clicked = st.button("↻ " + T("ranking_refresh"), key="rank_center_refresh",
                                  help=T("ranking_refresh"), use_container_width=False)
    if _refresh_clicked:
        _cache["fetched_at"] = 0  # 캐시 만료 → 다음 호출 시 재조회
        st.rerun()

    if not _rank:
        st.markdown(
            f'<div class="rank-center-empty">{T("ranking_empty")}</div>',
            unsafe_allow_html=True,
        )
        return

    # ── 순위 변동 뱃지 매핑 ──
    # rank_change: 양수=순위상승, 음수=순위하락, None=신규진입
    def _change_badge(rc) -> str:
        if rc is None:
            return '<span class="rank-chg-badge rank-chg-new">NEW</span>'
        if rc > 0:
            return f'<span class="rank-chg-badge rank-chg-up">▲{rc}</span>'
        if rc < 0:
            return f'<span class="rank-chg-badge rank-chg-down">▼{abs(rc)}</span>'
        return '<span class="rank-chg-badge rank-chg-stable">−</span>'

    _medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    _items = []
    for _it in _rank:
        _rn = _it.get("rank", 0)
        _q = (_it.get("question") or "").strip()
        if not _q:
            continue
        _q = _q[:120]
        _cnt = _it.get("count", 0)
        _rc = _it.get("rank_change")  # None | int
        _badge = _change_badge(_rc)
        _medal = _medals.get(_rn, "")
        _is_top3 = _rn <= 3
        _top_cls = "rank-center-top3" if _is_top3 else ""

        _items.append(
            f'<div class="rank-center-item {_top_cls}" data-rank="{_rn}">'
            f'<span class="rank-center-pos">'
            f'{_medal}<span class="rank-center-num">{_rn}</span>'
            f'</span>'
            f'<span class="rank-center-q prompt-chip" data-q="{html.escape(_q, quote=True)}">'
            f'{html.escape(_q, quote=False)}</span>'
            f'<span class="rank-center-meta">'
            f'<span class="rank-center-cnt">{_cnt}회</span>'
            f'{_badge}'
            f'</span>'
            f'</div>'
        )

    if not _items:
        st.markdown(
            f'<div class="rank-center-empty">{T("ranking_empty")}</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="rank-center-panel">'
        f'<div class="rank-center-list">{"".join(_items)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 마지막 업데이트 시각 ──
    _fetched = _cache.get("fetched_at")
    if _fetched:
        from datetime import datetime as _dt
        _ago_sec = int(_now_ts - _fetched)
        if _ago_sec < 60:
            _ago_str = "방금 전"
        elif _ago_sec < 3600:
            _ago_str = f"{_ago_sec // 60}분 전"
        else:
            _ago_str = f"{_ago_sec // 3600}시간 전"
        st.markdown(
            f'<div class="rank-center-updated">{_ago_str} 업데이트 · 12시간마다 자동 갱신</div>',
            unsafe_allow_html=True,
        )


components.html(_injector_html, height=1)

has_msgs = bool(st.session_state.msgs)

# ── 정중앙 랭킹 패널 ──
_render_question_ranking()

# ── 메인 채팅 영역 ──
if not has_msgs:
    _hour = datetime.now().hour
    _greet = (
        T("greet_morning")
        if _hour < 12
        else T("greet_afternoon")
        if _hour < 18
        else T("greet_evening")
    )
    _gs = st.session_state.get("greeting_sub_msg", "")
    _gs_html = f'<p class="greeting-sub">{_gs}</p>' if _gs else ""
    st.markdown(
        f"""
<div class="greeting">
    <h2>{_greet}, {T('greeting_title')}</h2>
    {_gs_html}
</div>
""",
        unsafe_allow_html=True,
    )

for idx, m in enumerate(st.session_state.msgs):
    _av = "💙" if m["role"] == "assistant" else "🙋"
    with st.chat_message(m["role"], avatar=_av):
        st.markdown(m["content"])
        iid = m.get("interaction_id")
        # BUG-02 수정: 게스트(토큰 없음)는 /feedback API가 401을 반환하므로 버튼 자체를 숨김
        _can_feedback = (
            m["role"] == "assistant"
            and iid
            and m.get("feedback") is None
            and bool(st.session_state.get("auth_token"))
        )
        if _can_feedback:
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
        else:
            # BUG-02 후속(보안 점검): 게스트는 /feedback 이 401 을 반환하므로
            # 버튼을 숨기는 대신, 익명 로컬 기록 + 로그인 유도 대체 수단을 제공.
            if not st.session_state.get("auth_token"):
                _gf = st.session_state.setdefault("guest_feedback", {"up": 0, "down": 0})
                c1, c2, c3 = st.columns([1, 1, 6])
                with c1:
                    if st.button("👍", key=f"gup_{idx}", help="도움됐어요 (로그인 시 서버 전송)"):
                        _gf["up"] += 1
                        st.toast("피드백을 저장했어요. 로그인하면 서버에 기록돼요.")
                        st.rerun()
                with c2:
                    if st.button("👎", key=f"gdn_{idx}", help="아쉬워요 (로그인 시 서버 전송)"):
                        _gf["down"] += 1
                        st.toast("피드백을 저장했어요. 로그인하면 서버에 기록돼요.")
                        st.rerun()
                with c3:
                    st.caption(
                        f"💡 로그인하면 피드백이 서버에 기록돼요 "
                        f"(로컬: 👍{_gf['up']} 👎{_gf['down']})"
                    )


# ── 채팅 입력 ────────────────────────────────────────────────────────────────
_ph = T("input_empty") if not has_msgs else T("input_msg")
prompt = st.chat_input(_ph)

if prompt:
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🙋"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="💙"):
        full_text = ""
        sources: list = []
        interaction_id = None
        _stream_interaction_id = None
        _stream_sources: list = []
        ph = st.empty()

        if st.session_state.streaming_mode:
            # 스트리밍 모드
            try:
                with httpx.stream(
                    "POST",
                    f"{API_BASE}/chat/stream",
                    json={
                        "query": prompt,
                        "history": [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.msgs[:-1]
                        ],
                        "user_id": st.session_state.subscriber_id,
                        "user_context": st.session_state.get("saved_user_info", ""),
                        "target_lang": st.session_state.target_lang,
                    },
                    timeout=180,
                ) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if not line:
                            continue
                        # SSE 라인 파싱
                        if line.startswith("data: "):
                            data = line[6:] # "data: " 제거
                            if data == "done":
                                break
                            # JSON 메타데이터 (sources, interaction_id) 추출
                            try:
                                import json as _json
                                parsed = _json.loads(data)
                                if isinstance(parsed, dict) and "interaction_id" in parsed:
                                    _stream_interaction_id = parsed.get("interaction_id")
                                    _stream_sources = parsed.get("sources", [])
                                    continue
                            except Exception:
                                pass
                            # 일반 텍스트 조각
                            if data.strip():
                                full_text += data
                                ph.markdown(full_text + "▌")
                        elif line.startswith("event: done"):
                            break
                    ph.markdown(full_text)
                    # 스트리밍 모드에서 추출한 메타데이터 적용
                    if _stream_interaction_id:
                        interaction_id = _stream_interaction_id
                    if _stream_sources:
                        sources = _stream_sources
                    # 출처 표시
                    if sources:
                        with st.expander(f"📚 참고 문헌 ({len(sources)}개)", expanded=False):
                            for i, s in enumerate(sources[:5]):
                                title = s.get("title", "문서") if isinstance(s, dict) else "문서"
                                st.caption(f"{i+1}. **{title}**")
            except Exception as e:
                import logging as _log

                _log.error("스트리밍 오류: %s", e)
                st.error(T("stream_err"))
                full_text = T("stream_fail")
                ph.markdown(full_text)
        else:
            # 일반 모드
            with st.spinner(""):
                try:
                    with httpx.Client(timeout=180) as c:
                        r = c.post(
                            f"{API_BASE}/chat",
                            json={
                                "query": prompt,
                                "history": [
                                    {"role": m["role"], "content": m["content"]}
                                    for m in st.session_state.msgs[:-1]
                                ],
                                "user_id": st.session_state.subscriber_id,
                                "user_context": st.session_state.get("saved_user_info", ""),
                                "target_lang": st.session_state.target_lang,
                            },
                        )
                    if r.status_code < 400:
                        data = r.json()
                        full_text = data.get("answer", "")
                        sources = data.get("sources", [])
                        interaction_id = data.get("interaction_id")
                        ph.markdown(full_text)
                        # 출처 표시
                        if sources:
                            with st.expander(f"📚 참고 문헌 ({len(sources)}개)", expanded=False):
                                for i, s in enumerate(sources[:5]):
                                    title = s.get("title", "문서") if isinstance(s, dict) else "문서"
                                    st.caption(f"{i+1}. **{title}**")
                    elif r.status_code == 429:
                        st.warning(T("free_used"))
                        full_text = ""
                    else:
                        st.error(T("err_generic"))
                        full_text = ""
                except Exception:
                    st.error(T("conn_err"))
                    full_text = ""

    if full_text:
        st.session_state.msgs.append(
            {
                "role": "assistant",
                "content": full_text,
                "sources": sources,
                "interaction_id": interaction_id,
                "feedback": None,
            }
        )
        st.rerun()

