"""📣 광고 관리 — create/edit/delete ads, upload banner images.
Ads are stored via backend API (data/ads.json + data/ads_images/).
Mobile public endpoint: GET /ads/list, GET /ads/image/<id>
"""
import base64
import io
import sys
import os
from pathlib import Path
from datetime import datetime

import streamlit as st
from PIL import Image

# Ensure project root is on the path (admin/lib is one level below admin)
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from admin.lib.api_client import (
    admin_list_ads,
    admin_create_ad,
    admin_update_ad,
    admin_delete_ad,
)

st.set_page_config(
    page_title="광고 관리 | Korean Gospel AI",
    page_icon="📣",
    layout="wide",
)

st.title("📣 광고 관리")
st.caption("모바일 앱의 인기QA 화면과 기타 화면에 노출되는 광고 배너를 관리합니다.")

# ── Session state initialization ──
if "ads_reload" not in st.session_state:
    st.session_state.ads_reload = 0


def _refresh():
    st.session_state.ads_reload = (st.session_state.ads_reload or 0) + 1


# ── Load ads from backend ──
resp = admin_list_ads()
ads = (resp.get("ads", []) if resp and "ads" in resp else []) if resp else []

# ── Tabs ──
tab_list, tab_create = st.tabs(["📋 광고 목록", "➕ 새 광고 등록"])

# ═══════════════════════════════════════════════════════
#  TAB 1: 광고 목록
# ═══════════════════════════════════════════════════════
with tab_list:
    if not ads:
        st.info("등록된 광고가 없습니다. 「➕ 새 광고 등록」 탭에서 추가하세요.")
    else:
        slot_labels = {"qa_top": "📌 상단 배너", "qa_feed": "📰 피드 중간", "today_top": "🏠 Today 상단"}
        for ad in ads:
            has_img = ad.get("has_image", False)
            active = ad.get("active", True)

            cols = st.columns([1, 4, 1.5, 1])
            with cols[0]:
                if has_img:
                    # Show thumbnail preview
                    try:
                        import httpx
                        from admin.lib.api_client import API_BASE, _headers
                        img_resp = httpx.Client(timeout=10).get(
                            f"{API_BASE}/ads/image/{ad['id']}", headers=_headers()
                        )
                        if img_resp.status_code == 200:
                            st.image(
                                io.BytesIO(img_resp.content),
                                width=120,
                                caption="",
                                use_container_width=False,
                            )
                        else:
                            st.markdown("🎨 *이미지 없음*")
                    except Exception:
                        st.markdown("🎨 *이미지 로드 실패*")
                else:
                    st.markdown("🎨 *이미지 없음*")

            with cols[1]:
                status_badge = "🟢 활성" if active else "🔴 비활성"
                st.markdown(
                    f"**{ad.get('title', '(제목 없음)')}**  {status_badge}\n\n"
                    f"{ad.get('subtitle', '')}\n\n"
                    f"슬롯: `{ad['slot']}` | 링크: `{ad.get('link_url', '') or '-'}`"
                )
                created = ad.get("created_at", "")
                if created:
                    st.caption(f"생성: {created[:16]}")

            with cols[2]:
                # Edit controls in expander
                with st.expander("✏️ 수정"):
                    new_title = st.text_input("제목", value=ad.get("title", ""), key=f"t_{ad['id']}")
                    new_sub = st.text_input("부제", value=ad.get("subtitle", ""), key=f"s_{ad['id']}")
                    new_link = st.text_input("링크 URL", value=ad.get("link_url", ""), key=f"l_{ad['id']}")
                    new_slot = st.selectbox("슬롯", ["qa_top", "qa_feed", "today_top"],
                                            index=["qa_top", "qa_feed", "today_top"].index(ad.get("slot", "qa_top")),
                                            key=f"sl_{ad['id']}")
                    new_active = st.checkbox("활성화", value=active, key=f"a_{ad['id']}")
                    new_img = st.file_uploader("새 이미지 (PNG/JPG)", type=["png", "jpg", "jpeg", "webp"],
                                               key=f"img_{ad['id']}")
                    remove_img = st.checkbox("이미지 삭제", key=f"rmimg_{ad['id']}")

                    if st.button("저장", key=f"save_{ad['id']}"):
                        changed = False
                        payload = {}
                        if new_title != ad.get("title", ""):
                            payload["title"] = new_title
                            changed = True
                        if new_sub != ad.get("subtitle", ""):
                            payload["subtitle"] = new_sub
                            changed = True
                        if new_link != ad.get("link_url", ""):
                            payload["link_url"] = new_link
                            changed = True
                        if new_slot != ad.get("slot", ""):
                            payload["slot"] = new_slot
                            changed = True
                        if new_active != active:
                            payload["active"] = new_active
                            changed = True

                        if remove_img:
                            payload["image_data"] = ""
                            changed = True
                        elif new_img is not None:
                            raw = new_img.read()
                            b64 = base64.b64encode(raw).decode()
                            ext = (new_img.name or "").rsplit(".", 1)[-1].lower() or "png"
                            payload["image_data"] = f"data:image/{ext};base64,{b64}"
                            changed = True

                        if changed:
                            r = admin_update_ad(ad["id"], **payload)
                            if r and r.get("ok"):
                                st.success("수정 완료!")
                                _refresh()
                                st.rerun()
                            else:
                                st.error("수정 실패: " + str(r))
                        else:
                            st.info("변경사항 없음")

            with cols[3]:
                if st.button("🗑️ 삭제", key=f"del_{ad['id']}"):
                    r = admin_delete_ad(ad["id"])
                    if r and r.get("ok"):
                        st.success("삭제 완료!")
                        _refresh()
                        st.rerun()
                    else:
                        st.error("삭제 실패: " + str(r))

            st.divider()

# ═══════════════════════════════════════════════════════
#  TAB 2: 새 광고 등록
# ═══════════════════════════════════════════════════════
with tab_create:
    st.subheader("➕ 새 광고 등록")

    col1, col2 = st.columns(2)
    with col1:
        new_title = st.text_input("광고 제목 *", key="n_title", placeholder="예: 성경 통독 챌린지")
        new_sub = st.text_input("부제", key="n_sub", placeholder="지금 시작하세요!")
        new_link = st.text_input("링크 URL", key="n_link", placeholder="https://...")
    with col2:
        new_slot = st.selectbox("노출 슬롯", ["qa_top", "qa_feed", "today_top"],
                                format_func=lambda x: {"qa_top": "📌 상단 배너", "qa_feed": "📰 피드 중간", "today_top": "🏠 Today 상단"}[x],
                                key="n_slot")
        new_active = st.checkbox("바로 활성화", value=True, key="n_active")
        new_img = st.file_uploader("배너 이미지 (권장: PNG/JPG)", type=["png", "jpg", "jpeg", "webp"],
                                   key="n_img")

    if new_img:
        try:
            st.image(new_img, caption="미리보기", width=300)
        except Exception:
            pass

    if st.button("🚀 등록", key="n_create", type="primary"):
        if not new_title.strip():
            st.error("제목은 필수입니다.")
        else:
            img_data = None
            if new_img:
                raw = new_img.read()
                b64 = base64.b64encode(raw).decode()
                ext = (new_img.name or "").rsplit(".", 1)[-1].lower() or "png"
                img_data = f"data:image/{ext};base64,{b64}"

            r = admin_create_ad(
                title=new_title.strip(),
                slot=new_slot,
                subtitle=new_sub.strip(),
                link_url=new_link.strip(),
                active=new_active,
                image_data=img_data,
            )
            if r and r.get("ok"):
                st.success(f"광고 '{new_title}' 등록 완료!")
                _refresh()
                # clear form
                for key in ["n_title", "n_sub", "n_link", "n_slot", "n_active", "n_img"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            else:
                st.error("등록 실패: " + str(r))
