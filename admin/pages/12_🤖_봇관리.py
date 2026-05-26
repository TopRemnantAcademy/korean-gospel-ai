"""E-B4: 봇 관리 Admin 페이지."""
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
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="봇 관리", page_icon="🤖", layout="wide")
st.title("🤖 봇 관리 (E-B)")
st.caption("의심 봇 감지 · 수동 차단/해제 · IP 모니터링")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "local-admin-key")

import httpx


def _headers():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _get_flagged():
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/list", headers=_headers())
        if r.status_code >= 400:
            return []
        subs = r.json() or []
        return [s for s in subs if s.get("flagged_as_bot") or (s.get("bot_score") or 0) >= 0.5]
    except Exception as e:
        st.error(f"API 오류: {e}")
        return []


def _toggle_bot_flag(sub_id: str, flag: bool):
    try:
        with httpx.Client(timeout=10) as c:
            r = c.patch(
                f"{API_BASE}/admin/subscribers/{sub_id}",
                headers=_headers(),
                json={"flagged_as_bot": flag, "bot_score": 1.0 if flag else 0.0},
            )
        return r.status_code < 400
    except Exception:
        return False


# ─────── 탭 ───────
tab1, tab2 = st.tabs(["🚨 의심 사용자", "📊 봇 점수 현황"])

with tab1:
    st.subheader("의심·차단된 사용자")
    if st.button("🔄 새로고침", key="refresh_flagged"):
        st.rerun()

    flagged = _get_flagged()
    if not flagged:
        st.success("현재 의심 사용자 없음.")
    else:
        st.warning(f"**{len(flagged)}명** 의심/차단 중")
        for sub in flagged:
            sid = sub.get("subscriber_id", "?")
            score = sub.get("bot_score", 0.0)
            flag = sub.get("flagged_as_bot", False)
            email = sub.get("email") or "(이메일 없음)"
            with st.expander(f"{'🔴' if flag else '🟡'} {sid[:12]}...  점수={score:.2f}  {email}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.json({
                        "subscriber_id": sid,
                        "bot_score": score,
                        "flagged_as_bot": flag,
                        "subscription_tier": sub.get("subscription_tier"),
                        "total_questions": sub.get("total_questions"),
                    })
                with col2:
                    if flag:
                        if st.button("✅ 차단 해제", key=f"unblock_{sid}"):
                            if _toggle_bot_flag(sid, False):
                                st.success("차단 해제됨")
                                st.rerun()
                    else:
                        if st.button("🚫 차단 처리", key=f"block_{sid}"):
                            if _toggle_bot_flag(sid, True):
                                st.warning("차단 처리됨")
                                st.rerun()

with tab2:
    st.subheader("봇 점수 분포")
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{API_BASE}/admin/subscribers/list", headers=_headers())
        if r.status_code < 400:
            all_subs = r.json() or []
            scores = [s.get("bot_score", 0.0) for s in all_subs]
            buckets = {"0.0~0.2": 0, "0.2~0.5": 0, "0.5~0.8": 0, "0.8~1.0": 0}
            for sc in scores:
                if sc < 0.2:
                    buckets["0.0~0.2"] += 1
                elif sc < 0.5:
                    buckets["0.2~0.5"] += 1
                elif sc < 0.8:
                    buckets["0.5~0.8"] += 1
                else:
                    buckets["0.8~1.0"] += 1

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("정상 (0~0.2)", buckets["0.0~0.2"])
            col2.metric("주의 (0.2~0.5)", buckets["0.2~0.5"])
            col3.metric("위험 (0.5~0.8)", buckets["0.5~0.8"])
            col4.metric("차단 대상 (0.8~1.0)", buckets["0.8~1.0"], delta_color="inverse")

            st.caption(f"전체 {len(all_subs)}명 기준")
        else:
            st.error("API 오류")
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
