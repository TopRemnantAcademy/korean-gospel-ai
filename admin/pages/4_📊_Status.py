"""📊 모니터링 — 시스템 현황 + 에러 로그."""
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
    get_collections, list_documents,
    get_errors, get_error_stats,
    get_services_health,
    bot_stats, bot_list, bot_toggle_flag,
)
from admin.lib.auth import gate

# set_page_config MUST be the first Streamlit command on the page.
# gate() issues st.* commands, so it runs AFTER this call.
st.set_page_config(page_title="모니터링", page_icon="📊", layout="wide")
gate(os.getenv("APP_PASSWORD", ""))
st.title("📊 모니터링")


# ── VA-2: 봇 관리 헬퍼 (12_🤖_봇관리.py 에서 통합) ──────────────────────────────
def _bot_score_color(score: float) -> str:
    if score >= 0.7:
        return "bot-score-high"
    elif score >= 0.4:
        return "bot-score-mid"
    return "bot-score-low"


def _bot_score_label(score: float) -> str:
    if score >= 0.7:
        return "🔴 높음"
    elif score >= 0.4:
        return "🟡 중간"
    return "🟢 낮음"


def _bot_badge(flagged: bool, score: float) -> str:
    if flagged:
        return '<span class="bot-badge-flagged">🚫 봇 차단</span>'
    elif score >= 0.5:
        return '<span class="bot-badge-suspicious">⚠️ 의심</span>'
    return '<span class="bot-badge-clean">✅ 정상</span>'


def _bot_user_label(users: list, sid: str) -> str:
    u = next((x for x in users if x["subscriber_id"] == sid), None)
    if not u:
        return sid
    name = u.get("display_name") or u["subscriber_id"][:12]
    q = u.get("total_questions", 0)
    score = u.get("bot_score", 0)
    flag = "🚫" if u.get("flagged_as_bot") else ("⚠️" if score >= 0.5 else "  ")
    return f"{flag} {name}  ·  Q:{q}회  ·  점수:{score:.2f}"


def _bot_render_user_detail(selected_sid: str, users: list) -> None:
    user = next((u for u in users if u["subscriber_id"] == selected_sid), None)
    if not user:
        return
    score_val = float(user.get("bot_score", 0) or 0)
    is_flagged = bool(user.get("flagged_as_bot", False))

    col_l, col_r = st.columns([1.5, 1])
    with col_l:
        st.markdown("#### 사용자 정보")
        st.write(f"**ID:** `{selected_sid}`")
        st.write(f"**이름:** {user.get('display_name') or '—'}")
        st.write(f"**총 질문:** {user.get('total_questions', 0)}회")
        st.write(f"**구원 상태:** {user.get('salvation_status') or '—'}")
        first = (user.get("first_seen_at") or "")[:19].replace("T", " ")
        last = (user.get("last_active_at") or "")[:19].replace("T", " ")
        st.write(f"**첫 방문:** {first or '—'}")
        st.write(f"**최근 활동:** {last or '—'}")

        st.markdown("#### 봇 상태")
        st.markdown(
            f"**플래그:** {_bot_badge(is_flagged, score_val)}  \n"
            f"**봇 점수:** <span class='{_bot_score_color(score_val)}'>{score_val:.4f}</span> "
            f"({_bot_score_label(score_val)})",
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown("#### 봇 관리 작업")
        _form_suffix = selected_sid[:8]
        with st.form(f"bot_action_form_{_form_suffix}"):
            new_flagged = st.checkbox(
                "🚫 봇으로 차단",
                value=is_flagged,
                key=f"bot_flag_check_{_form_suffix}",
                help="이 사용자를 봇으로 표시하고 응답 생성에서 차단",
            )
            new_score = st.slider(
                "봇 점수",
                min_value=0.0, max_value=1.0, value=min(score_val, 1.0), step=0.01,
                key=f"bot_score_slider_{_form_suffix}",
                help="0.0 = 확실히 사람, 1.0 = 확실히 봇. 0.5 이상은 의심.",
            )
            reason = st.text_input(
                "변경 사유 (감사 로그)",
                placeholder="예: 반복적인 패턴 질문, 비정상적 응답 속도",
                key=f"bot_reason_{_form_suffix}",
            )
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submitted = st.form_submit_button("💾 저장", use_container_width=True, type="primary")
            with col_btn2:
                score_only = st.form_submit_button("📊 점수만 업데이트", use_container_width=True)
            if submitted:
                result = bot_toggle_flag(selected_sid, new_flagged, new_score)
                if result:
                    st.success(f"✅ '{user.get('display_name') or selected_sid[:12]}' 업데이트 완료")
                    if reason:
                        st.caption(f"사유: {reason}")
                    st.rerun()
                else:
                    st.error("저장 실패 — 백엔드 연결을 확인하세요")
            if score_only:
                result = bot_toggle_flag(selected_sid, is_flagged, new_score)
                if result:
                    st.success(f"✅ 봇 점수 {new_score:.2f}로 업데이트")
                    st.rerun()
                else:
                    st.error("저장 실패 — 백엔드 연결을 확인하세요")


def _bot_render_bulk_actions(users: list, filter_label: str) -> None:
    if not users:
        return
    st.divider()
    st.subheader("📦 일괄 작업")
    st.caption(f"현재 '{filter_label}' 필터의 {len(users)}명에게 일괄 적용합니다.")
    bulk_col1, bulk_col2, bulk_col3 = st.columns(3)
    _btn_suffix = filter_label
    with bulk_col1:
        if st.button("🚫 모두 봇 차단", use_container_width=True, key=f"bulk_flag_{_btn_suffix}",
                      help=f"'{filter_label}' 필터의 {len(users)}명을 봇으로 차단"):
            count, failed = 0, 0
            for u in users:
                if not u.get("flagged_as_bot"):
                    # [P0-12] API 반환값 검증 — 실패(None) 시 성공으로 카운트하지 않는다
                    ok = bot_toggle_flag(u["subscriber_id"], True, max(u.get("bot_score", 0) or 0, 0.8))
                    if ok is not None:
                        count += 1
                    else:
                        failed += 1
            if failed:
                st.warning(f"⚠️ {count}명 차단 완료 / {failed}명 실패(백엔드 API 오류) — 새로고침 후 재시도하세요")
            else:
                st.success(f"✅ {count}명 봇 차단 처리 완료")
                st.rerun()
    with bulk_col2:
        if st.button("✅ 모두 차단 해제", use_container_width=True, key=f"bulk_unflag_{_btn_suffix}",
                      help=f"'{filter_label}' 필터의 {len(users)}명 차단 해제"):
            count, failed = 0, 0
            for u in users:
                if u.get("flagged_as_bot"):
                    ok = bot_toggle_flag(u["subscriber_id"], False, max((u.get("bot_score", 0) or 0) - 0.3, 0.0))
                    if ok is not None:
                        count += 1
                    else:
                        failed += 1
            if failed:
                st.warning(f"⚠️ {count}명 해제 완료 / {failed}명 실패(백엔드 API 오류) — 새로고침 후 재시도하세요")
            else:
                st.success(f"✅ {count}명 차단 해제")
                st.rerun()
    with bulk_col3:
        if st.button("📊 점수 0으로 초기화", use_container_width=True, key=f"bulk_reset_{_btn_suffix}",
                      help=f"'{filter_label}' 필터의 {len(users)}명 bot_score=0"):
            count, failed = 0, 0
            for u in users:
                if (u.get("bot_score", 0) or 0) > 0:
                    ok = bot_toggle_flag(u["subscriber_id"], u.get("flagged_as_bot", False), 0.0)
                    if ok is not None:
                        count += 1
                    else:
                        failed += 1
            if failed:
                st.warning(f"⚠️ {count}명 초기화 완료 / {failed}명 실패(백엔드 API 오류) — 새로고침 후 재시도하세요")
            else:
                st.success(f"✅ {count}명 점수 초기화 완료")
                st.rerun()

col_r, _ = st.columns([1, 5])
with col_r:
    if st.button("🔄 새로고침", use_container_width=True):
        st.rerun()

tab_sys, tab_err, tab_bot = st.tabs(["🗂 시스템 현황", "🚨 에러 로그", "🤖 봇 관리"])


# ─────────────────────────────────────────────────────────────────────────────
# 탭 1: 시스템 현황
# ─────────────────────────────────────────────────────────────────────────────
with tab_sys:
    # VA-3: 서비스 헬스 요약 (한눈에 보기)
    _svc = get_services_health()
    if _svc:
        _overall = _svc.get("overall")
        if _overall == "healthy":
            st.success("✅ 전체 서비스 정상")
        elif _overall == "degraded":
            st.warning("⚠️ 일부 서비스 저하 — 아래 상태 확인")
        elif _overall == "unavailable":
            st.error("❌ 핵심 서비스 사용 불가 — 백엔드 재기동 필요")
        else:
            st.info(f"서비스 상태: {_overall}")
        _svc_items = list(_svc.get("services", {}).items())
        if _svc_items:
            _scols = st.columns(min(4, len(_svc_items)))
            for i, (name, info) in enumerate(_svc_items):
                with _scols[i % len(_scols)]:
                    _ok = info.get("ok")
                    st.markdown(f"{'✅' if _ok else '❌'} **{name}**")
                    st.caption((info.get("message") or "")[:48])
        st.divider()

    st.subheader("📚 자료 통계")
    docs = list_documents() or []
    if not docs:
        st.info("아직 올린 자료가 없습니다. 📥 Upload 페이지에서 첫 자료를 올려보세요.")
    else:
        states: dict = {}
        for d in docs:
            s = d.get("latest_state", "?")
            states[s] = states.get(s, 0) + 1
        KR = {"draft": "임시", "validated": "검증완료", "published": "공개됨",
              "superseded": "옛 버전", "archived": "보관됨"}
        chart_data = pd.DataFrame({"개수": {KR.get(k, k): v for k, v in states.items()}})
        st.bar_chart(chart_data)

    st.divider()
    st.subheader("🗂 검색 인덱스 (벡터 DB)")
    info = get_collections()
    if info is None:
        st.error("API 연결 실패")
    elif info.get("warning"):
        st.warning(f"안내: {info['warning']}")
    else:
        cols = info.get("collections", [])
        if not cols:
            st.info("아직 검색 인덱스에 등록된 자료가 없습니다.")
        else:
            df = pd.DataFrame(cols).rename(columns={
                "name": "컬렉션", "points_count": "청크 수",
                "vectors_count": "벡터 수", "status": "상태",
            })
            st.dataframe(df, use_container_width=True)



# ─────────────────────────────────────────────────────────────────────────────
# 탭 2: 에러 로그
# ─────────────────────────────────────────────────────────────────────────────
with tab_err:
    stats = get_error_stats()
    if stats is None:
        st.error("❌ API 연결 실패")
    else:
        e1h  = stats.get("errors_1h", 0)
        e24h = stats.get("errors_24h", 0)
        c1h  = stats.get("critical_1h", 0)
        s24h = stats.get("slow_24h", 0)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔴 에러 (1시간)", e1h)
        m2.metric("🔴 에러 (24시간)", e24h)
        m3.metric("⚡ CRITICAL (1시간)", c1h)
        m4.metric("🐢 SLOW (24시간)", s24h)

        if e1h + c1h > 0:
            st.error(f"⚠️ 최근 1시간 에러 {e1h + c1h}건 — 아래 목록 확인")
        elif e24h > 0:
            st.warning(f"최근 24시간 에러 {e24h}건")
        else:
            st.success("✅ 최근 24시간 에러 없음")

        st.divider()

        # 필터
        cf1, cf2, cf3, cf4 = st.columns(4)
        with cf1:
            level_f = st.selectbox("레벨", ["전체", "ERROR", "SLOW", "CRITICAL"], key="err_lv")
        with cf2:
            hours_f = st.selectbox("기간", [1, 6, 24, 72, 168], index=2,
                                   format_func=lambda h: f"최근 {h}시간" if h < 24 else f"최근 {h//24}일",
                                   key="err_hr")
        with cf3:
            path_f = st.text_input("경로 포함", key="err_path", placeholder="/chat")
        with cf4:
            limit_f = st.number_input("최대 건수", 10, 500, 200, key="err_lim")

        lvl_param = None if level_f == "전체" else level_f
        rows = get_errors(limit=int(limit_f), level=lvl_param,
                         path=path_f.strip() or None, hours=int(hours_f))

        if not rows:
            st.info("조건에 맞는 에러 로그가 없습니다.")
        else:
            df = pd.DataFrame(rows)
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["시각"] = df["timestamp"].dt.strftime("%m/%d %H:%M:%S")
            EMOJI = {"ERROR": "🔴", "SLOW": "🐢", "CRITICAL": "💀"}
            df["레벨"] = df["level"].map(lambda v: f"{EMOJI.get(v,'⚪')} {v}")

            show = {
                "시각": "시각", "레벨": "레벨", "method": "메서드",
                "path": "경로", "status_code": "상태", "duration_ms": "응답(ms)",
                "error_type": "에러유형", "error_message": "메시지",
            }
            df2 = df.rename(columns={k: v for k, v in show.items() if k in df.columns})
            display = [v for k, v in show.items() if v in df2.columns]
            st.dataframe(df2[display], use_container_width=True, height=380,
                         column_config={"응답(ms)": st.column_config.NumberColumn(format="%d ms"),
                                        "상태": st.column_config.NumberColumn(format="%d")})

            # traceback 상세
            has_tb = [r for r in rows if r.get("traceback")]
            if has_tb:
                st.divider()
                st.subheader("🔍 Traceback 상세")
                for r in has_tb:
                    ts = r.get("timestamp", "")
                    try:
                        r["time_str"] = datetime.fromisoformat(ts).strftime("%m/%d %H:%M:%S")
                    except Exception:
                        r["time_str"] = ts[:19]
                opts = {f"[{r['level']}] {r['time_str']} — {r['path']} ({r.get('error_type','?')})": r
                        for r in has_tb}
                sel_label = st.selectbox("에러 선택", list(opts.keys()), key="tb_sel")
                sel = opts[sel_label]
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.markdown(f"**레벨**: `{sel['level']}`")
                    st.markdown(f"**경로**: `{sel['method']} {sel['path']}`")
                    st.markdown(f"**상태코드**: `{sel['status_code']}`")
                with col_d2:
                    st.markdown(f"**에러유형**: `{sel.get('error_type','—')}`")
                    st.markdown(f"**응답시간**: `{sel['duration_ms']} ms`")
                st.code(sel.get("error_message", ""), language="text")
                if sel.get("traceback"):
                    st.code(sel["traceback"], language="python")


# ── VA-2: 봇 관리 탭 (12_🤖_봇관리.py 에서 통합) ───────────────────────────────
with tab_bot:
    st.markdown(
        """
        <style>
        .bot-badge-flagged { background:#fde2e2; color:#c0392b; padding:3px 8px;
            border-radius:12px; font-size:12px; font-weight:600; }
        .bot-badge-suspicious { background:#fff4e0; color:#d68910; padding:3px 8px;
            border-radius:12px; font-size:12px; font-weight:600; }
        .bot-badge-clean { background:#e8f8ef; color:#1e8449; padding:3px 8px;
            border-radius:12px; font-size:12px; font-weight:600; }
        .bot-score-high { color:#c0392b; font-weight:700; }
        .bot-score-mid { color:#d68910; font-weight:700; }
        .bot-score-low { color:#1e8449; font-weight:700; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _bot_stats = bot_stats()
    if not _bot_stats:
        st.error("봇 통계를 불러오지 못했습니다.")
    else:
        _total = _bot_stats.get("total_subscribers", 0)
        _flagged = _bot_stats.get("flagged_as_bot", 0)
        _suspicious = _bot_stats.get("suspicious", 0)
        _avg = _bot_stats.get("avg_bot_score", 0)
        _hi, _mi, _lo = st.columns(3)
        _hi.metric("봇 차단 사용자", f"🚫 {_flagged}명", help="봇으로 플래그된 사용자 수")
        _mi.metric("의심 사용자", f"⚠️ {_suspicious}명", help="점수 0.5 이상인 사용자 수")
        _lo.metric("전체 사용자", f"👥 {_total}명")
        st.metric("평균 봇 점수", f"{_avg:.4f}", help="0.0=사람, 1.0=봇")

        st.divider()
        st.subheader("🔍 사용자 봇 분석")
        _filter = st.radio("필터", ["전체", "봇 차단만", "의심만", "정상만"],
                           horizontal=True, key="bot_filter_radio")
        if _filter == "봇 차단만":
            _users = bot_list(filter_type="flagged")
        elif _filter == "의심만":
            _users = bot_list(filter_type="suspicious")
        elif _filter == "정상만":
            # [P0-11] bot_list() 는 API 실패 시 None 반환 — 반복 전 or [] 가드 필수
            _users = [u for u in (bot_list() or []) if (u.get("bot_score", 0) or 0) < 0.5 and not u.get("flagged_as_bot")]
        else:
            _users = bot_list()
        _users = _users or []

        _score_th = st.slider("최소 봇 점수 표시", 0.0, 1.0, 0.0, 0.01, key="bot_score_th")
        _users = [u for u in _users if (u.get("bot_score", 0) or 0) >= _score_th]

        if not _users:
            st.info(f"조건에 맞는 사용자가 없습니다. (필터: {_filter})")
        else:
            st.caption(f"🔎 {len(_users)}명 표시 중")
            if len(_users) > 1:
                _options = {_bot_user_label(_users, u["subscriber_id"]): u["subscriber_id"] for u in _users}
                _selected = st.radio("사용자 선택", list(_options.keys()), key="bot_user_radio")
                _selected_sid = _options[_selected]
            else:
                _selected_sid = _users[0]["subscriber_id"]
                st.info(f"선택: {_bot_user_label(_users, _selected_sid)}")
            st.divider()
            _bot_render_user_detail(_selected_sid, _users)
            _bot_render_bulk_actions(_users, _filter)

