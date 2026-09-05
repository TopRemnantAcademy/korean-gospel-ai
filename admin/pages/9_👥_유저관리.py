"""👥 유저관리 — 사용자의 모든 정보(프로필·활동·구독) 통합 관리."""
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
    list_subscribers, update_subscriber,
    spiritual_stats,
    toggle_assume_saved,
    resend_verification, verify_override, set_tier,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.title("👥 유저관리")
st.caption("사용자의 모든 정보(프로필·활동·구독)를 한 곳에서 확인·관리합니다.")

if st.button("🔄 새로고침", key="sub_refresh"):
    st.rerun()

tab_list, tab_dist = st.tabs([
    "📋 사용자 관리", "📊 영적 분포",
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
    else:
        # ── 요약 통계
        now_utc = datetime.utcnow()
        df_all = pd.DataFrame(subs)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("전체 사용자", len(subs))
        _total_q = int(df_all.get("total_questions", pd.Series(dtype=int)).sum()) if "total_questions" in df_all else 0
        m2.metric("총 질문", _total_q)

        # 종교 분포 (있는 경우만)
        if "religion" in df_all.columns:
            top_rel = df_all["religion"].dropna().value_counts().head(1)
            m3.metric("최다 종교", top_rel.index[0] if len(top_rel) else "—")
        else:
            m3.metric("기독교", sum(1 for s in subs if s.get("religion") == "기독교"))

        # BUG-06 수정: m4 가 m2 와 동일한 "총 질문"을 중복 표시하던 버그.
        # → "회원가입 사용자" (auth_status == 'email' 또는 'google') 로 교체.
        if "auth_status" in df_all.columns:
            _member_count = int(df_all["auth_status"].isin(["email", "google"]).sum())
        else:
            _member_count = sum(1 for s in subs if s.get("auth_status") in ("email", "google"))
        m4.metric("회원가입 사용자", _member_count)

        if "faith_stage" in df_all.columns:
            st.write("신앙 단계 분포")
            st.bar_chart(df_all["faith_stage"].value_counts())

        st.divider()

        # ── 사용자 선택
        st.subheader("📋 사용자 프로필 관리")

        def _sub_label(s: dict) -> str:
            name = s.get("display_name") or s.get("subscriber_id", "?")[:12]
            tq   = s.get("total_questions", 0) or 0
            return f"{name}  질문 {tq}회"

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
                    rel_opts = list(RELIGIONS)
                    if cur_religion not in rel_opts:
                        rel_opts.append(cur_religion)
                    rel_idx  = rel_opts.index(cur_religion)
                    religion = st.selectbox("종교", rel_opts, index=rel_idx, key="f_religion")

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

            # ── 우: 활동 정보 + 구독 통합
            with col_r:
                st.markdown("#### 📊 활동 정보")
                first_seen = (user.get("first_seen_at") or "")[:19].replace("T", " ")
                last_act   = (user.get("last_active_at") or "")[:19].replace("T", " ")
                st.write(f"**첫 방문:** {first_seen or '—'}")
                st.write(f"**최근 활동:** {last_act or '—'}")
                st.write(f"**총 대화:** {user.get('total_questions', 0)}회")
                st.write(f"**구원 상태:** {user.get('salvation_status') or '—'}")
                st.write(f"**인증 상태:** {user.get('auth_status') or '—'} · "
                         f"**연령대:** {user.get('age_group') or '—'} · "
                         f"**성별:** {user.get('gender') or '—'}")

                # ── 구독 현황 + 잔여 기간 (2026-07-29 통합) ──
                st.divider()
                st.markdown("#### 💳 구독 현황")
                _tier = user.get("subscription_tier") or "free"
                _life = bool(user.get("is_lifetime_member"))
                _exp  = user.get("subscription_expires_at")  # ISO(YYYY-MM-DDTHH:MM:SS) 또는 None

                if _life or _tier == "lifetime":
                    st.success("💎 평생 구독 회원")
                elif _tier != "free":
                    if _exp:
                        try:
                            _rem = (datetime.fromisoformat(_exp) - datetime.utcnow()).days
                        except Exception:
                            _rem = None
                        if _rem is not None and _rem > 0:
                            st.info(f"⏳ **{_tier}** 구독 — 잔여 **{_rem}일**")
                        elif _rem is not None:
                            st.warning(f"⌛ **{_tier}** 구독 만료 ({abs(_rem)}일 경과)")
                        else:
                            st.info(f"⏳ **{_tier}** 구독 (만료일 미설정)")
                    else:
                        st.info(f"⏳ **{_tier}** 구독 (만료일 미설정)")
                else:
                    st.caption("🆓 무료 사용자")

                # ── 구독 편집 (통합: 티어 + 만료일 한 번에 저장) ──
                _tiers = ["free", "standard", "premium", "lifetime"]
                _cur = _tier if _tier in _tiers else "free"
                _new_tier = st.selectbox("티어", _tiers, index=_tiers.index(_cur), key="sel_tier")

                _allow_exp = _new_tier not in ("free", "lifetime")
                _default_exp = None
                if _exp:
                    try:
                        _default_exp = datetime.fromisoformat(_exp).date()
                    except Exception:
                        _default_exp = None
                _new_exp = st.date_input(
                    "구독 만료일",
                    value=_default_exp,
                    disabled=not _allow_exp,
                    key="sel_exp",
                    help="standard/premium 구독 만료일(YYYY-MM-DD). free/lifetime 는 미사용",
                )
                if st.button("💾 구독 저장", key="btn_sub", use_container_width=True):
                    _exp_iso = _new_exp.isoformat() if (_allow_exp and _new_exp) else None
                    if set_tier(selected_sid, _new_tier, expires_at=_exp_iso):
                        st.success("구독 정보 저장됨")
                        st.rerun()
                    else:
                        st.error("저장 실패")

                # ── 이메일 인증 ──
                st.divider()
                st.markdown("#### 📧 이메일 인증")
                _verified = bool(user.get("email_verified", False))
                st.write(f"**상태:** {'✅ 인증됨' if _verified else '⏳ 미인증'}")
                cva, cvb = st.columns(2)
                if cva.button("✉️ 인증메일 재발송", key="btn_resend"):
                    if resend_verification(selected_sid):
                        st.success("재발송 완료")
                    else:
                        st.error("실패")
                if cvb.button("✅ 수동 인증완료", key="btn_verify"):
                    if verify_override(selected_sid):
                        st.success("인증 처리됨")
                        st.rerun()
                    else:
                        st.error("실패")


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
# (탭 3 여정 흐름 / 탭 4 관심 필요 — 2026-07-29 기능 삭제)
# ─────────────────────────────────────────────────────────────────────────────
