"""E-G3: 공통 UI 컴포넌트 — 모든 admin 페이지에서 재사용."""
from __future__ import annotations

from typing import Callable, Optional
import streamlit as st


def suggestion_card(
    title: str,
    body: str,
    accept_label: str = "✅ 적용",
    reject_label: str = "🗑 무시",
    accept_cb: Optional[Callable] = None,
    reject_cb: Optional[Callable] = None,
    key_prefix: str = "sc",
) -> None:
    """AI 제안 카드 — 제목 + 본문 + 적용/무시 버튼."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(body[:300])
        col_a, col_b, _ = st.columns([1, 1, 4])
        with col_a:
            if st.button(accept_label, key=f"{key_prefix}_accept"):
                if accept_cb:
                    accept_cb()
        with col_b:
            if st.button(reject_label, key=f"{key_prefix}_reject"):
                if reject_cb:
                    reject_cb()


def stepper(stages: list[str], current: int) -> None:
    """진행 단계 표시 — current는 0-based."""
    cols = st.columns(len(stages))
    for i, (col, stage) in enumerate(zip(cols, stages)):
        with col:
            if i < current:
                st.markdown(f"<div style='text-align:center;color:#2d5016;font-weight:bold'>✅ {stage}</div>",
                            unsafe_allow_html=True)
            elif i == current:
                st.markdown(f"<div style='text-align:center;color:#1a7acc;font-weight:bold;font-size:1.05em'>▶ {stage}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center;color:#999'>○ {stage}</div>",
                            unsafe_allow_html=True)


def diff_viewer(before: str, after: str, label_before: str = "이전", label_after: str = "이후") -> None:
    """2분할 diff 뷰어."""
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"**{label_before}**")
        st.code(before[:600], language=None)
    with col_b:
        st.caption(f"**{label_after}**")
        st.code(after[:600], language=None)


def token_meter(daily: int, monthly: int, bonus: int, tier: str = "guest") -> None:
    """토큰 잔량 미터 (사이드바용)."""
    if tier == "guest":
        approx = max(0, daily // 2000)
        st.caption(f"오늘 남은 응답 약 **{approx}건**")
        if approx == 0:
            st.warning("무료 풀 소진 — 가입 시 10만 토큰")
    else:
        st.caption(f"월간 **{monthly:,}** 토큰")
        if bonus > 0:
            st.caption(f"보너스 **{bonus:,}** 토큰")


def empty_state(icon: str, title: str, cta_label: str = "", cta_cb: Optional[Callable] = None) -> None:
    """빈 상태 표시 (데이터 없을 때)."""
    st.markdown(
        f"<div style='text-align:center;padding:3rem;color:#888'>"
        f"<div style='font-size:3rem'>{icon}</div>"
        f"<div style='font-size:1.1rem;margin-top:1rem'>{title}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if cta_label and cta_cb:
        _, col_c, _ = st.columns([2, 2, 2])
        with col_c:
            if st.button(cta_label, use_container_width=True):
                cta_cb()


def draft_status_badge(saved_at: Optional[str], device_id: str = "browser") -> None:
    """임시저장 상태 배지."""
    if saved_at:
        st.caption(f"💾 임시저장됨 — {saved_at[:16].replace('T', ' ')} ({device_id})")
    else:
        st.caption("💾 임시저장 없음")
