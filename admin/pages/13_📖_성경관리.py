"""성경 관리 — 본문 파일 업로드 + 장/절 미리보기.

운영자가 성경 책 텍스트(.txt)를 올리면 앱 성경 탭에서 책→장→절 선택으로 읽을 수 있어요.
업로드 형식: 각 줄이 '절:본문' (예: 1:태초에 말씀이 계시니라). 파일명이 책명 (예: 요한.txt).
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
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    admin_upload_bible, admin_list_bible_books, admin_delete_bible_book,
    get_bible_passage,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.title("📖 성경 관리")
st.caption("성경 본문 파일을 올리고, 앱에서 책→장→절로 읽히는지 미리 확인하세요.")

# ── 1) 업로드 ─────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("#### ⬆ 성경 책 본문 업로드")
    st.caption(
        "파일명이 책명이 됩니다 (예: `요한.txt`). "
        "내용 형식: 각 줄 `절:본문` — `1:태초에 말씀이 계시니라`"
    )
    bfile = st.file_uploader(
        "성경 텍스트 (.txt / .md)",
        type=["txt", "md"],
        key="bible_up",
    )
    if bfile:
        st.success(f"✅ {bfile.name} · {bfile.size:,} bytes")
        if st.button("📤 업로드", type="primary", key="bible_submit", use_container_width=True):
            with st.spinner("업로드 중..."):
                resp = admin_upload_bible(bfile.name, bfile.getvalue())
            if resp and resp.get("book"):
                st.success(
                    f"✅ {resp['book']} 업로드 완료 — "
                    f"{resp.get('total_chapters', 0)}장 / {resp.get('total_verses', 0)}절"
                )
                st.rerun()
            else:
                st.error("❌ 업로드 실패 (서버 로그 확인).")

st.markdown("---")

# ── 2) 책 목록 ─────────────────────────────────────────────────────
data = admin_list_bible_books() or {"books": []}
books = data.get("books", [])
books_sorted = sorted(books, key=lambda b: b.get("name", ""))

col_head, col_refresh = st.columns([3, 1])
with col_head:
    st.markdown("#### 📚 등록된 성경 책")
with col_refresh:
    if st.button("🔄 새로고침", key="bible_refresh", use_container_width=True):
        st.rerun()

if not books_sorted:
    st.info("아직 등록된 성경 책이 없어요. 위에서 .txt 파일을 올려보세요.")
    st.stop()

with st.expander("📋 전체 책 목록 / 삭제", expanded=False):
    for b in books_sorted:
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(
                f"**{b['name']}** — {b.get('total_chapters', 0)}장 / "
                f"{b.get('total_verses', 0)}절"
            )
        with c2:
            _confirm = st.checkbox("정말 삭제?", key=f"bdelconf_{b['id']}")
            if st.button("🗑", key=f"bdel_{b['id']}", use_container_width=True, disabled=not _confirm, type="primary"):
                res = admin_delete_bible_book(b["id"])
                if res and res.get("ok"):
                    st.success(f"{b['name']} 삭제됨")
                    st.rerun()

# ── 3) 장/절 미리보기 (시중 성경 앱과 동일한 선택기) ──────────────────
st.markdown("---")
st.markdown("#### 🔎 장 / 절 미리보기 (앱 사용자 화면과 동일)")

book_names = [b["name"] for b in books_sorted]
sel_book = st.selectbox("책", book_names, key="pv_book")

# 선택된 책 구조 찾기
cur = next((b for b in books_sorted if b["name"] == sel_book), None)
if not cur:
    st.stop()

total_chapters = cur.get("total_chapters", 0)

c_ch, c_vs, c_ve = st.columns([1, 1, 1])
with c_ch:
    chapter = st.number_input("장", min_value=1, max_value=max(total_chapters, 1),
                              value=1, key="pv_chapter")
with c_vs:
    verse_start = st.number_input("시작 절", min_value=1, value=1, key="pv_vs")
with c_ve:
    verse_end = st.number_input("끝 절 (장 전체는 시작절만)", min_value=1,
                                value=verse_start, key="pv_ve")

use_range = st.checkbox("절 범위로 보기 (체크 해제 시 장 전체)", value=False,
                        key="pv_userange")

col_prev, col_next = st.columns(2)
with col_prev:
    if st.button("◀ 이전 장", key="pv_prev", use_container_width=True):
        if chapter > 1:
            st.session_state.pv_chapter = chapter - 1
            st.rerun()
with col_next:
    if st.button("다음 장 ▶", key="pv_next", use_container_width=True):
        if chapter < total_chapters:
            st.session_state.pv_chapter = chapter + 1
            st.rerun()

vs = verse_start if use_range else None
ve = verse_end if use_range else None

with st.spinner("본문 불러오는 중..."):
    passage = get_bible_passage(sel_book, chapter, vs, ve)

if not passage or not passage.get("available"):
    st.warning(passage.get("message", "본문을 불러올 수 없습니다.") if passage else "본문을 불러올 수 없습니다.")
else:
    st.markdown(f"### {passage.get('reference', sel_book)}")
    verses = passage.get("verses", [])
    if not verses:
        st.caption("해당 범위에 절이 없습니다. 절 번호를 확인하세요.")
    for v in verses:
        st.markdown(
            f"<sup style='color:#4ADE80;font-weight:600;margin-right:6px;'>{v['v']}</sup>"
            f"{v['t']}",
            unsafe_allow_html=True,
        )
    st.caption(
        f"이 책 총 {passage.get('chapter_count', 0)}장 · "
        f"현재 장 절 수: {passage.get('verse_count', 0)}"
    )
