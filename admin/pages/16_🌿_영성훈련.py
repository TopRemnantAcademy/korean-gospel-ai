"""📖 영성훈련 콘텐츠 관리 — YouTube 강의, Spotify 찬양, 묵상 링크 등록/수정/삭제."""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent  # project root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import (
    list_content_links, create_content_link, update_content_link, delete_content_link,
)
from admin.lib.auth import gate

# set_page_config MUST be the first Streamlit command on the page.
# gate() issues st.* commands, so it runs AFTER this call.
st.set_page_config(page_title="영성훈련 콘텐츠", page_icon="📖", layout="wide")
gate(os.getenv("APP_PASSWORD", ""))
st.title("📖 영성훈련 콘텐츠 관리")
st.caption("YouTube 강의 · Spotify 찬양 · 묵상 링크를 등록하여 모바일 앱 '영성' 탭에 표시합니다.")

# ── 헬퍼 ───────────────────────────────────────────────────────────────────────
SOURCES = ["youtube", "spotify", "other"]
SOURCE_LABELS = {"youtube": "▶ YouTube", "spotify": "♫ Spotify", "other": "🔗 기타"}
CATEGORIES = ["lecture", "music", "devotion"]
CATEGORY_LABELS = {"lecture": "강의", "music": "찬양", "devotion": "묵상"}
STAGES = ["seeker", "uncertain", "assured", "mature"]


def _reload():
    st.session_state.pop("content_links", None)
    st.rerun()


# ── 목록 조회 ──────────────────────────────────────────────────────────────────
if "content_links" not in st.session_state:
    st.session_state.content_links = list_content_links() or {"items": []}

data = st.session_state.content_links or {"items": []}
items = data.get("items", [])

col1, col2 = st.columns([1, 4])
with col1:
    if st.button("🔄 새로고침", use_container_width=True):
        _reload()
with col2:
    filter_cat = st.selectbox(
        "카테고리 필터",
        ["전체"] + CATEGORIES,
        format_func=lambda x: "전체" if x == "전체" else CATEGORY_LABELS.get(x, x),
    )

# ── 목록 테이블 ────────────────────────────────────────────────────────────────
filtered = [i for i in items if filter_cat == "전체" or i.get("category") == filter_cat]

if not filtered:
    st.info("등록된 콘텐츠가 없습니다. 아래에서 새 콘텐츠를 추가하세요.")
else:
    import pandas as pd
    df = pd.DataFrame([
        {
            "제목": i.get("title", ""),
            "소스": SOURCE_LABELS.get(i.get("source"), i.get("source", "")),
            "카테고리": CATEGORY_LABELS.get(i.get("category"), i.get("category", "")),
            "활성": "✅" if i.get("active") else "⛔",
            "순서": i.get("order_index", 0),
            "URL": i.get("url", ""),
        }
        for i in filtered
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ── 새 콘텐츠 추가 ─────────────────────────────────────────────────────────────
with st.expander("➕ 새 콘텐츠 추가", expanded=not filtered):
    with st.form("add_content", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("제목 *", placeholder="예: 로마서 강해 1강 - 은혜의 말씀")
            source = st.selectbox("소스", SOURCES, format_func=lambda x: SOURCE_LABELS.get(x, x))
            category = st.selectbox(
                "카테고리", CATEGORIES, format_func=lambda x: CATEGORY_LABELS.get(x, x)
            )
            content_lang = st.selectbox("언어", ["ko", "zh", "en", "ja"], index=0, help="중국어 앱은 lang=zh 콘텐츠만 표시합니다.")
        with c2:
            url = st.text_input(
                "URL *",
                placeholder="https://youtu.be/xxx 또는 https://open.spotify.com/track/xxx",
                help="YouTube/Spotify/SoundCloud/Vimeo 링크. https만 허용.",
            )
            order_index = st.number_input("정렬 순서", min_value=0, max_value=999, value=0, step=1)
            active = st.checkbox("활성화 (앱에 표시)", value=True)

        description = st.text_area("설명 (선택)", placeholder="이 콘텐츠에 대한 간단한 설명")
        tags_str = st.text_input("태그 (쉼표 구분)", placeholder="구원, 은혜, 기도")
        stages = st.multiselect("대상 영적 단계", STAGES)

        if st.form_submit_button("저장", type="primary", use_container_width=True):
            if not title.strip() or not url.strip():
                st.error("제목과 URL은 필수입니다.")
            else:
                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str.strip() else None
                result = create_content_link(
                    title=title.strip(),
                    url=url.strip(),
                    source=source if source != "other" else None,  # other는 자동 감지
                    category=category,
                    lang=content_lang,
                    description=description.strip() or None,
                    tags=tags,
                    target_salvation_stage=stages if stages else None,
                    order_index=order_index,
                    active=active,
                )
                if result:
                    st.success(f"✅ '{title}' 콘텐츠가 추가되었습니다.")
                    _reload()

# ── 기존 콘텐츠 수정/삭제 ──────────────────────────────────────────────────────
if filtered:
    st.divider()
    st.subheader("✏️ 수정 / 삭제")

    for item in filtered:
        link_id = item.get("link_id")
        with st.expander(f"{SOURCE_LABELS.get(item.get('source'), '🔗')} {item.get('title', '(제목 없음)')}"):
            with st.form(f"edit_{link_id}"):
                ec1, ec2 = st.columns(2)
                with ec1:
                    new_title = st.text_input("제목", value=item.get("title", ""), key=f"title_{link_id}")
                    new_category = st.selectbox(
                        "카테고리", CATEGORIES,
                        index=CATEGORIES.index(item.get("category", "lecture")) if item.get("category") in CATEGORIES else 0,
                        format_func=lambda x: CATEGORY_LABELS.get(x, x),
                        key=f"cat_{link_id}",
                    )
                    new_lang = st.selectbox(
                        "언어", ["ko", "zh", "en", "ja"],
                        index=["ko", "zh", "en", "ja"].index(item.get("lang", "ko")) if item.get("lang") in ["ko", "zh", "en", "ja"] else 0,
                        key=f"lang_{link_id}",
                    )
                    new_order = st.number_input(
                        "정렬 순서",
                        min_value=0, max_value=999,
                        value=item.get("order_index", 0), step=1,
                        key=f"order_{link_id}",
                    )
                with ec2:
                    new_url = st.text_input("URL", value=item.get("url", ""), key=f"url_{link_id}")
                    new_active = st.checkbox(
                        "활성화", value=item.get("active", True), key=f"active_{link_id}",
                    )
                    new_stages = st.multiselect(
                        "대상 영적 단계", STAGES,
                        default=[s for s in (item.get("target_salvation_stage") or []) if s in STAGES],
                        key=f"stages_{link_id}",
                    )

                new_desc = st.text_area("설명", value=item.get("description") or "", key=f"desc_{link_id}")
                new_tags_str = st.text_input(
                    "태그 (쉼표 구분)",
                    value=", ".join(item.get("tags") or []),
                    key=f"tags_{link_id}",
                )

                bc1, bc2 = st.columns([1, 1])
                with bc1:
                    if st.form_submit_button("수정 저장", use_container_width=True):
                        tags = [t.strip() for t in new_tags_str.split(",") if t.strip()] if new_tags_str.strip() else None
                        result = update_content_link(
                            link_id,
                            title=new_title.strip(),
                            url=new_url.strip(),
                            category=new_category,
                            lang=new_lang,
                            description=new_desc.strip() or None,
                            tags=tags,
                            target_salvation_stage=new_stages if new_stages else None,
                            order_index=new_order,
                            active=new_active,
                        )
                        if result:
                            st.success("✅ 수정되었습니다.")
                            _reload()
                with bc2:
                    _confirm = st.checkbox("정말 삭제하시겠습니까?", key=f"clconf_{link_id}")
                    if st.form_submit_button("🗑 삭제", use_container_width=True, disabled=not _confirm):
                        result = delete_content_link(link_id)
                        if result:
                            st.success("🗑 삭제되었습니다.")
                            _reload()
