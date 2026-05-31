"""👥 사람 — 사용자 관리 · 영적 분포 · 봇 차단."""
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
from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    list_subscribers, update_subscriber, upgrade_subscription,
    spiritual_stats, spiritual_journey, spiritual_stagnant,
    toggle_assume_saved,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="사람 관리", page_icon="👥", layout="wide")
st.title("👥 사람 관리")

if st.button("🔄 새로고침", key="sub_refresh"):
    st.rerun()

tab_list, tab_dist, tab_journey, tab_stagnant, tab_bot = st.tabs([
    "📋 사용자 관리", "📊 영적 분포", "🔀 여정 흐름", "⏰ 관심 필요", "🤖 봇 관리",
])


# ─────────────────────────────────────────────────────────────────────────────
# 종교 / 교단 / 다락방 계층 상수
# ─────────────────────────────────────────────────────────────────────────────
RELIGIONS = ["(선택안함)", "기독교", "천주교", "불교", "무교", "이슬람", "힌두교", "기타"]

DENOMINATIONS_BY_RELIGION: dict[str, list[str]] = {
    "기독교": ["(선택안함)", "장로교(합동)", "장로교(통합)", "감리교", "침례교",
              "순복음", "성결교", "루터교", "성공회", "개혁교회", "기타"],
    "천주교": ["(선택안함)", "기타"],
    "불교":   ["(선택안함)", "조계종", "태고종", "천태종", "기타"],
}

# 다락방은 기독교 교단 소속에만 해당
DARAKBANG_DENOMS = {
    "장로교(합동)", "장로교(통합)", "감리교", "침례교",
    "순복음", "성결교", "루터교", "기타",
}


def _show_darakbang(religion: str, denom: str) -> bool:
    return religion == "기독교" and denom in DARAKBANG_DENOMS


# ─────────────────────────────────────────────────────────────────────────────
# 탭 1: 사용자 관리
# ─────────────────────────────────────────────────────────────────────────────
with tab_list:
    subs = list_subscribers() or []

    if not subs:
        st.info("현재 등록된 사용자가 없습니다.")
        st.stop()

    # ── 요약 통계
    now_utc = datetime.utcnow()
    df_all = pd.DataFrame(subs)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 사용자", len(subs))
    m2.metric("유료 회원", int(df_all.get("subscription_tier", pd.Series()).isin(["member", "supporter"]).sum()) if "subscription_tier" in df_all else 0)

    # 종교 분포 (있는 경우만)
    if "religion" in df_all.columns:
        top_rel = df_all["religion"].dropna().value_counts().head(1)
        m3.metric("최다 종교", top_rel.index[0] if len(top_rel) else "—")
    else:
        m3.metric("기독교", sum(1 for s in subs if s.get("religion") == "기독교"))

    flagged = sum(1 for s in subs if s.get("flagged_as_bot"))
    m4.metric("🤖 차단된 봇", flagged, delta_color="inverse" if flagged else "off")

    st.divider()

    # ── 사용자 선택
    st.subheader("📋 사용자 프로필 관리")

    def _sub_label(s: dict) -> str:
        name = s.get("display_name") or s.get("subscriber_id", "?")[:12]
        tier = s.get("subscription_tier", "guest")
        tq   = s.get("total_questions", 0) or 0
        return f"{name}  [{tier}]  질문 {tq}회"

    selected_sid = st.selectbox(
        "관리할 사용자",
        options=[s["subscriber_id"] for s in subs],
        format_func=lambda x: _sub_label(next(s for s in subs if s["subscriber_id"] == x)),
        key="people_sel",
    )

    if selected_sid:
        user = next(s for s in subs if s["subscriber_id"] == selected_sid)

        col_l, col_r = st.columns(2)

        # ── 좌: 프로필 편집
        with col_l:
            st.markdown("#### 프로필 편집")
            with st.form("edit_user_form"):
                # 종교 → 교단 → 다락방 계층
                cur_religion = user.get("religion") or "(선택안함)"
                if cur_religion not in RELIGIONS:
                    RELIGIONS.append(cur_religion)
                rel_idx  = RELIGIONS.index(cur_religion)
                religion = st.selectbox("종교", RELIGIONS, index=rel_idx, key="f_religion")

                denom_opts = DENOMINATIONS_BY_RELIGION.get(religion, ["(선택안함)"])
                cur_denom  = user.get("denomination") or "(선택안함)"
                if cur_denom not in denom_opts:
                    denom_opts = list(denom_opts) + [cur_denom]
                denom_idx  = denom_opts.index(cur_denom) if cur_denom in denom_opts else 0
                denomination = st.selectbox("교단", denom_opts, index=denom_idx, key="f_denom")

                is_darakbang = False
                if _show_darakbang(religion, denomination):
                    is_darakbang = st.checkbox(
                        "다락방 멤버",
                        value=bool(user.get("is_darakbang_member", False)),
                        key="f_darakbang",
                        help="기독교 교단 소속자에게만 해당",
                    )

                emotional_state  = st.text_input("감정 상태", value=user.get("emotional_state") or "", key="f_emo")
                current_struggle = st.text_area("현재 어려움/상처", value=user.get("current_struggle") or "", key="f_struggle")

                if st.form_submit_button("💾 저장"):
                    payload: dict = {
                        "religion":         religion if religion != "(선택안함)" else None,
                        "denomination":     denomination if denomination != "(선택안함)" else None,
                        "is_darakbang_member": is_darakbang,
                        "emotional_state":  emotional_state or None,
                        "current_struggle": current_struggle or None,
                    }
                    if update_subscriber(selected_sid, payload):
                        st.success("저장 완료!")
                        st.rerun()
                    else:
                        st.error("저장 실패")

        # ── 우: 활동 정보 + 구독 관리
        with col_r:
            st.markdown("#### 활동 정보")
            first_seen = (user.get("first_seen_at") or "")[:19].replace("T", " ")
            last_act   = (user.get("last_active_at") or "")[:19].replace("T", " ")
            st.write(f"**첫 방문:** {first_seen or '—'}")
            st.write(f"**최근 활동:** {last_act or '—'}")
            st.write(f"**총 대화:** {user.get('total_questions', 0)}회")
            st.write(f"**구원 상태:** {user.get('salvation_status') or '—'}")
            st.write(f"**봇 점수:** {user.get('bot_score', 0):.2f}")

            st.divider()
            st.markdown("#### 💳 구독 관리")

            tier_now    = user.get("subscription_tier", "guest")
            trial_exp   = user.get("trial_expires_at")
            subscribed  = user.get("subscribed_at")

            TIER_LABEL = {"guest": "무료체험", "member": "유료회원", "supporter": "후원회원"}
            tier_color = {"guest": "#888", "member": "#4a9eff", "supporter": "#FFD700"}

            st.markdown(
                f"<span style='background:{tier_color.get(tier_now,'#888')};"
                f"padding:3px 10px;border-radius:12px;color:white;font-size:0.85em'>"
                f"{TIER_LABEL.get(tier_now, tier_now)}</span>",
                unsafe_allow_html=True,
            )

            if tier_now == "guest" and trial_exp:
                try:
                    exp_dt = datetime.fromisoformat(str(trial_exp).split(".")[0])
                    days_left = (exp_dt - now_utc).days
                    if days_left >= 0:
                        st.caption(f"⏳ 체험 만료까지 {days_left}일 ({str(exp_dt.date())})")
                    else:
                        st.caption(f"🔒 체험 만료됨 ({str(exp_dt.date())})")
                except Exception:
                    pass
            elif subscribed:
                st.caption(f"구독 시작: {str(subscribed)[:10]}")

            st.markdown("**티어 변경:**")
            new_tier = st.selectbox(
                "새 티어",
                ["guest", "member", "supporter"],
                index=["guest", "member", "supporter"].index(tier_now) if tier_now in ["guest", "member", "supporter"] else 0,
                format_func=lambda x: TIER_LABEL.get(x, x),
                key="sub_new_tier",
                label_visibility="collapsed",
            )
            ext_days = 0
            if new_tier == "guest":
                ext_days = st.number_input("체험 연장 (일)", 0, 30, 0, key="sub_ext_days")

            if st.button("💳 구독 업데이트", key="sub_upgrade_btn", use_container_width=True):
                result = upgrade_subscription(selected_sid, new_tier, ext_days)
                if result and result.get("ok"):
                    st.success(f"✅ {TIER_LABEL.get(new_tier, new_tier)}으로 변경 완료")
                    st.rerun()
                else:
                    st.error("변경 실패")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 2: 영적 분포
# ─────────────────────────────────────────────────────────────────────────────
with tab_dist:
    st.subheader("구원 상태 분포")
    stats = spiritual_stats()
    if not stats:
        st.warning("API 연결 실패 — 백엔드 서버가 실행 중인지 확인하세요.")
    else:
        total  = stats.get("total", 0)
        dist   = stats.get("salvation_status_dist", {})
        assume_n = stats.get("assume_saved_count", 0)

        c1, c2, c3 = st.columns(3)
        c1.metric("전체 사용자", total)
        c2.metric("assume_saved 활성", assume_n)
        unc_pct = round(dist.get("uncertain", 0) / max(total, 1) * 100, 1)
        c3.metric("uncertain 비율", f"{unc_pct}%",
                  help="확신 없는 사람 비율 — 높을수록 확신 도움이 핵심")

        if dist:
            _ORDER = ["unknown", "seeker", "uncertain", "assured", "mature"]
            _LABEL = {
                "unknown": "🔘 미상", "seeker": "🔍 탐구",
                "uncertain": "❓ 확신없음", "assured": "✅ 확신", "mature": "🌳 성숙",
            }
            ordered = {_LABEL.get(k, k): dist.get(k, 0) for k in _ORDER}
            df_d = pd.DataFrame({"단계": list(ordered.keys()), "인원": list(ordered.values())})
            st.bar_chart(df_d.set_index("단계"))
            st.dataframe(df_d, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# 탭 3: 여정 흐름
# ─────────────────────────────────────────────────────────────────────────────
with tab_journey:
    st.subheader("구원 여정 전환 흐름")
    days = st.slider("조회 기간 (일)", 7, 90, 30, key="journey_days")
    journey = spiritual_journey(days=days)

    if not journey:
        st.warning("API 연결 실패.")
    else:
        total_t = journey.get("total_transitions", 0)
        flows   = journey.get("flows", {})

        c1, c2 = st.columns(2)
        c1.metric(f"최근 {days}일 전환 건수", total_t)
        assured_gain = flows.get("uncertain→assured", 0) + flows.get("seeker→assured", 0)
        c2.metric("✨ 확신으로 전환 (사역 KPI)", assured_gain,
                  help="이번 기간 구원의 확신을 갖게 된 사람 수")

        if flows:
            df_f = pd.DataFrame([
                {"전환": k, "건수": v}
                for k, v in sorted(flows.items(), key=lambda x: -x[1])
            ])
            st.dataframe(df_f, use_container_width=True, hide_index=True)
            st.bar_chart(df_f.set_index("전환"))
        else:
            st.info(f"최근 {days}일 전환 기록이 없습니다.")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 4: 관심 필요 (정체 사용자)
# ─────────────────────────────────────────────────────────────────────────────
with tab_stagnant:
    st.subheader("관심 필요 — 정체된 사용자")
    stagnant_days = st.slider("정체 기준 (일)", 7, 60, 30, key="stagnant_days")
    stagnant = spiritual_stagnant(stagnant_days=stagnant_days)

    if not stagnant:
        st.warning("API 연결 실패.")
    else:
        users = stagnant.get("users", [])
        st.metric(f"{stagnant_days}일+ 정체 사용자", stagnant.get("count", 0))

        if users:
            st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
            st.divider()
            st.subheader("수동 개입")

            sel_id = st.selectbox(
                "사용자 선택",
                options=[u["subscriber_id"] for u in users],
                format_func=lambda x: f"{x} ({next((u['salvation_status'] for u in users if u['subscriber_id'] == x), '?')})",
                key="stagnant_select",
            )
            if sel_id:
                ca, cb = st.columns(2)
                with ca:
                    new_status = st.selectbox(
                        "salvation_status 변경",
                        ["(변경안함)", "unknown", "seeker", "uncertain", "assured", "mature"],
                        key="stagnant_new_status",
                    )
                with cb:
                    assume = st.toggle("assume_saved 활성화", key="stagnant_assume")
                reason = st.text_input("변경 사유 (감사 로그)", key="stagnant_reason")

                if st.button("💾 저장", key="stagnant_save"):
                    also = new_status if new_status != "(변경안함)" else None
                    result = toggle_assume_saved(sel_id, assume, reason=reason, also_set_status=also)
                    if result:
                        st.success(f"✅ 업데이트 완료")
                    else:
                        st.error("저장 실패")
        else:
            st.success(f"🎉 {stagnant_days}일 이상 정체된 사용자가 없습니다!")


# ─────────────────────────────────────────────────────────────────────────────
# 탭 5: 봇 관리
# ─────────────────────────────────────────────────────────────────────────────
with tab_bot:
    st.subheader("🤖 봇 / 의심 사용자 관리")
    st.caption("bot_score ≥ 0.5 또는 flagged_as_bot=True 인 계정을 자동 표시합니다.")

    bot_subs = list_subscribers() or []
    flagged_subs = [s for s in bot_subs if s.get("flagged_as_bot") or (s.get("bot_score") or 0) >= 0.5]

    # 봇 점수 분포
    scores = [s.get("bot_score", 0.0) for s in bot_subs]
    buckets = {"정상 (0~0.2)": 0, "주의 (0.2~0.5)": 0, "위험 (0.5~0.8)": 0, "차단대상 (0.8+)": 0}
    for sc in scores:
        if sc < 0.2:      buckets["정상 (0~0.2)"] += 1
        elif sc < 0.5:    buckets["주의 (0.2~0.5)"] += 1
        elif sc < 0.8:    buckets["위험 (0.5~0.8)"] += 1
        else:             buckets["차단대상 (0.8+)"] += 1

    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.metric("정상 (0~0.2)", buckets["정상 (0~0.2)"])
    bc2.metric("주의 (0.2~0.5)", buckets["주의 (0.2~0.5)"])
    bc3.metric("위험 (0.5~0.8)", buckets["위험 (0.5~0.8)"])
    bc4.metric("차단대상 (0.8+)", buckets["차단대상 (0.8+)"], delta_color="inverse")

    st.divider()

    if not flagged_subs:
        st.success("현재 의심 사용자 없음.")
    else:
        st.warning(f"**{len(flagged_subs)}명** 의심/차단 중")
        for sub in flagged_subs:
            sid   = sub.get("subscriber_id", "?")
            score = sub.get("bot_score", 0.0)
            flag  = sub.get("flagged_as_bot", False)
            email = sub.get("email") or "(이메일 없음)"

            with st.expander(f"{'🔴 차단' if flag else '🟡 의심'}  {sid[:14]}  점수={score:.2f}  {email}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.json({
                        "subscriber_id":   sid,
                        "bot_score":       score,
                        "flagged_as_bot":  flag,
                        "subscription_tier": sub.get("subscription_tier"),
                        "total_questions": sub.get("total_questions"),
                    })
                with c2:
                    if flag:
                        if st.button("✅ 차단 해제", key=f"unblock_{sid}"):
                            if update_subscriber(sid, {"flagged_as_bot": False, "bot_score": 0.0}):
                                st.success("차단 해제됨")
                                st.rerun()
                    else:
                        if st.button("🚫 차단 처리", key=f"block_{sid}"):
                            if update_subscriber(sid, {"flagged_as_bot": True, "bot_score": 1.0}):
                                st.warning("차단 처리됨")
                                st.rerun()
