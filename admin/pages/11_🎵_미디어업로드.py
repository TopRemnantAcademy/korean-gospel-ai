"""미디어 업로드 — 찬양 음원 / 설교 음성 파일.

관리자가 오디오 파일을 업로드하면 모바일 앱의 찬양/설교 탭에 바로 노출됩니다.
기존 시중 찬양/설교 스트리밍 앱과 동일한 흐름: 파일 업로드 → 메타 입력 → 즉시 공개.
"""
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
import datetime
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    admin_upload_media, admin_list_media, admin_delete_media, API_BASE,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.title("🎵 미디어 업로드")
st.caption("찬양 음원 / 설교 음성을 올리면 앱(찬양·설교 탭)에 바로 반영돼요.")

TAB_META = {
    "worship": {"label": "🎶 찬양 음원", "artist": "가수 / 연주자", "ph": "예: 새 힘 (유해준)"},
    "sermon": {"label": "🎤 설교 음성", "artist": "설교자", "ph": "예: 은혜의 삶 (김목사)"},
}

tab_worship, tab_sermon = st.tabs([TAB_META["worship"]["label"], TAB_META["sermon"]["label"]])


def _render_category(category: str):
    meta = TAB_META[category]

    # ── 업로드 폼 ────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(f"#### ⬆ {meta['label']} 올리기")
        file = st.file_uploader(
            "오디오 파일 (mp3 / wav / m4a / ogg / aac / flac)",
            type=["mp3", "wav", "m4a", "ogg", "aac", "flac"],
            key=f"up_{category}",
        )
        if file:
            st.success(f"✅ {file.name} · {file.size:,} bytes")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            title = st.text_input("제목 *", key=f"title_{category}",
                                  placeholder=meta["ph"])
        with col2:
            artist = st.text_input(meta["artist"], key=f"artist_{category}")
        with col3:
            # BUG-11 수정: order_index 폼 필드 추가 — 기존에는 항상 0으로 업로드됨.
            order_index = st.number_input(
                "정렬 순서",
                min_value=0,
                max_value=9999,
                value=0,
                step=1,
                key=f"order_{category}",
                help="낮을수록 먼저 표시. 기본 0.",
            )

        refs = st.text_input("본문 구절 (쉼표 구분, 선택)", key=f"refs_{category}",
                             placeholder="예: 요한 3:16, 빌립보서 4:13")
        desc = st.text_area("설명 (선택)", key=f"desc_{category}", height=68)
        active = st.checkbox("앱에 공개", value=True, key=f"active_{category}")

        # ── 예약 발행 / 알림 (2026-07-29 미디어 동기화) ──
        st.markdown("**⏰ 발행 예약** — 비워두면 업로드 즉시 공개됩니다.")
        _sched_col1, _sched_col2 = st.columns(2)
        with _sched_col1:
            pubdate = st.date_input(
                "발행 예약일 (비우면 지금)", value=None,
                key=f"pubdate_{category}",
            )
        with _sched_col2:
            pubtime = st.time_input(
                "발행 시각", value=datetime.datetime.now().time(),
                key=f"pubtime_{category}",
            )
        publish_at = None
        if pubdate is not None:
            publish_at = f"{pubdate.isoformat()}T{pubtime.strftime('%H:%M')}"

        notify_mode = st.radio(
            "📲 알림 발송",
            options=["immediate", "batch", "none"],
            format_func=lambda x: {
                "immediate": "즉시 (업로드 후 ~1분 내 푸시)",
                "batch": "저녁 배치 (21:00 KST, 여러 건 묶어 1회)",
                "none": "알림 안 보냄",
            }[x],
            horizontal=True,
            key=f"notify_{category}",
            help="매일 저녁 한 번 올리면 '즉시'로 한 통. "
                 "낮에 여러 번 올리고 저녁에 한 번만 받고 싶으면 '저녁 배치'.",
        )

        can = bool(file and title)
        if not can:
            st.caption("⬆ 파일과 제목을 입력하면 올릴 수 있어요.")

        if st.button("📤 업로드", type="primary", disabled=not can,
                     key=f"submit_{category}", use_container_width=True):
            with st.spinner("업로드 중..."):
                resp = admin_upload_media(
                    file_name=file.name, file_bytes=file.getvalue(),
                    title=title, category=category, artist=artist,
                    description=desc, scripture_refs=refs,
                    order_index=int(order_index), active=active,
                    publish_at=publish_at, notify_mode=notify_mode,
                )
            if resp and resp.get("asset_id"):
                if publish_at:
                    st.success(f"✅ 예약 완료: **{title}** → {publish_at} (KST) 발행")
                else:
                    st.success(f"✅ 업로드 완료: **{title}**")
                st.rerun()
            else:
                st.error("❌ 업로드 실패 (서버 로그를 확인하세요).")

    # ── 목록 ─────────────────────────────────────────────────────
    st.markdown("---")
    col_head, col_refresh = st.columns([3, 1])
    with col_head:
        st.markdown(f"#### 📂 등록된 {meta['label']}")
    with col_refresh:
        if st.button("🔄 새로고침", key=f"refresh_{category}", use_container_width=True):
            st.rerun()

    data = admin_list_media(category=category) or {"items": []}
    items = data.get("items", [])
    if not items:
        st.info("아직 등록된 항목이 없어요.")
        return

    # BUG-12 수정: 항목이 많을 때 전체 렌더링하면 Streamlit 페이지가 느려지는 문제.
    # 페이지네이션 도입 — 기본 20개씩 표시.
    _PAGE_SIZE = 20
    _total_items = len(items)
    _total_pages = max(1, (_total_items + _PAGE_SIZE - 1) // _PAGE_SIZE)

    # 페이지 상태는 카테고리별로 분리
    _page_key = f"media_page_{category}"
    if _page_key not in st.session_state:
        st.session_state[_page_key] = 0
    _cur_page = st.session_state[_page_key]
    # 범위 보정 (삭제 후 페이지 초과 방지)
    if _cur_page >= _total_pages:
        _cur_page = _total_pages - 1
        st.session_state[_page_key] = _cur_page

    # 페이지 컨트롤
    _pcol1, _pcol2, _pcol3 = st.columns([1, 2, 1])
    with _pcol1:
        if st.button("◀ 이전", key=f"prev_{category}", disabled=(_cur_page == 0), use_container_width=True):
            st.session_state[_page_key] = _cur_page - 1
            st.rerun()
    with _pcol2:
        st.caption(f"페이지 {_cur_page + 1} / {_total_pages} · 총 {_total_items}개")
    with _pcol3:
        if st.button("다음 ▶", key=f"next_{category}", disabled=(_cur_page >= _total_pages - 1), use_container_width=True):
            st.session_state[_page_key] = _cur_page + 1
            st.rerun()

    # 현재 페이지 슬라이스
    _start = _cur_page * _PAGE_SIZE
    _end = _start + _PAGE_SIZE
    _page_items = items[_start:_end]

    for it in _page_items:
        aid = it["asset_id"]
        stream_url = f"{API_BASE}/mobile/media/{aid}/stream"
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{it['title']}**")
                sub = []
                if it.get("artist"):
                    sub.append(it["artist"])
                if it.get("scripture_refs"):
                    sub.append(" · ".join(it["scripture_refs"]))
                if sub:
                    st.caption(" · ".join(sub))
                st.caption(f"파일: {it.get('file_name')} · {it.get('size_bytes', 0):,} bytes")
            with c2:
                if not it.get("active"):
                    st.warning("비공개")
                _confirm = st.checkbox("정말 삭제하시겠습니까?", key=f"delconf_{aid}")
                if st.button("🗑 삭제", key=f"del_{aid}", use_container_width=True, disabled=not _confirm, type="primary"):
                    res = admin_delete_media(aid)
                    if res and res.get("ok"):
                        st.success("삭제됨")
                        st.rerun()
                    else:
                        st.error("삭제 실패")
            # 미리듣기
            try:
                st.audio(stream_url)
            except Exception:
                st.caption(f"🔗 스트림: {stream_url}")


with tab_worship:
    _render_category("worship")

with tab_sermon:
    _render_category("sermon")
