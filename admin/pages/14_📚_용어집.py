"""E-E: 자동 용어집 관리.

- 검토 대기: 자동 추출된 신규 용어 (빈도순) → 승인/거부/신학용어 지정
- 승인 완료: 검색·카테고리 필터
- 신학 용어: is_theology_term=True 목록
- 통계: 전체/승인/신학/대기 카운트
"""
from __future__ import annotations

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.auth import gate
gate(os.getenv("APP_PASSWORD", ""))

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_API_KEY", "local-admin-key")
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

st.set_page_config(page_title="용어집", page_icon="📚", layout="wide")
st.title("📚 자동 용어집 (E-E)")
st.caption("자료 정제 시 추출된 신학 용어·고유명사 통합 관리. 신학 용어로 지정하면 D3 가드레일에 자동 반영됩니다.")


# ── API 헬퍼 ───────────────────────────────────────────────────────────────
def _api(method: str, path: str, **kwargs):
    try:
        fn = getattr(httpx, method)
        r = fn(f"{API_BASE}{path}", headers=HEADERS, timeout=15, **kwargs)
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None


# ── 초기 시드 확인 ─────────────────────────────────────────────────────────
if st.sidebar.button("🌱 신학 용어 시드 (최초 1회)"):
    result = _api("post", "/glossary/seed")
    if result:
        st.sidebar.success(f"시드 완료: {result.get('added', 0)}개 추가")
    else:
        st.sidebar.error("시드 실패 또는 이미 완료")


# ── 통계 카드 ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=15)
def _fetch_stats():
    return _api("get", "/glossary/stats") or {}


stats = _fetch_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 용어", stats.get("total", 0))
c2.metric("승인 완료", stats.get("verified", 0))
c3.metric("신학 용어", stats.get("theology", 0))
c4.metric("검토 대기", stats.get("pending", 0))

st.divider()

# ── 탭 ─────────────────────────────────────────────────────────────────────
tab_pending, tab_verified, tab_theology, tab_search = st.tabs([
    f"⏳ 검토 대기 ({stats.get('pending', 0)})",
    "✅ 승인 완료",
    "🕊 신학 용어",
    "🔍 검색",
])


# ── Tab 1: 검토 대기 ────────────────────────────────────────────────────────
with tab_pending:
    @st.cache_data(ttl=10)
    def _fetch_pending():
        return _api("get", "/glossary/pending?limit=100") or []

    pending = _fetch_pending()
    if not pending:
        st.info("검토 대기 중인 용어가 없습니다. 자료를 정제하면 용어가 자동 추출됩니다.")
    else:
        st.caption(f"총 {len(pending)}개 후보 — 빈도 높은 순")

        # bulk 승인용 체크박스
        bulk_ids = []
        for item in pending:
            with st.container():
                col_check, col_term, col_freq, col_approve, col_theology, col_reject = st.columns(
                    [0.5, 2, 1, 1.5, 2, 1]
                )
                with col_check:
                    if st.checkbox("", key=f"bulk_{item['id']}"):
                        bulk_ids.append(item["id"])
                with col_term:
                    st.markdown(f"**{item['term']}**")
                    if item.get("definition"):
                        st.caption(item["definition"])
                with col_freq:
                    st.caption(f"{item['frequency_count']}회")
                with col_approve:
                    if st.button("✅ 승인", key=f"approve_{item['id']}"):
                        _api("post", f"/glossary/{item['id']}/approve",
                             json={"is_theology": False})
                        st.cache_data.clear()
                        st.rerun()
                with col_theology:
                    if st.button("🕊 신학 용어", key=f"theology_{item['id']}"):
                        _api("post", f"/glossary/{item['id']}/approve",
                             json={"is_theology": True, "category": "doctrine"})
                        st.cache_data.clear()
                        st.rerun()
                with col_reject:
                    if st.button("🗑", key=f"reject_{item['id']}", help="거부 (삭제)"):
                        _api("post", f"/glossary/{item['id']}/reject")
                        st.cache_data.clear()
                        st.rerun()

        if bulk_ids:
            col_ba, col_bb = st.columns([2, 2])
            with col_ba:
                if st.button(f"✅ 선택 {len(bulk_ids)}개 일괄 승인"):
                    for bid in bulk_ids:
                        _api("post", f"/glossary/{bid}/approve", json={"is_theology": False})
                    st.cache_data.clear()
                    st.success(f"{len(bulk_ids)}개 승인 완료")
                    st.rerun()
            with col_bb:
                if st.button(f"🗑 선택 {len(bulk_ids)}개 일괄 거부"):
                    for bid in bulk_ids:
                        _api("post", f"/glossary/{bid}/reject")
                    st.cache_data.clear()
                    st.success(f"{len(bulk_ids)}개 거부 완료")
                    st.rerun()


# ── Tab 2: 승인 완료 ────────────────────────────────────────────────────────
with tab_verified:
    col_q, col_cat = st.columns([3, 1])
    with col_q:
        search_q = st.text_input("🔍 검색", placeholder="용어명...", key="verified_q")
    with col_cat:
        cat_filter = st.selectbox("카테고리", ["전체", "person", "place", "doctrine", "scripture", "event", "other"],
                                  key="verified_cat")

    @st.cache_data(ttl=10)
    def _fetch_verified(q: str, cat: str):
        params = f"?verified_only=true&limit=200&q={q}"
        if cat != "전체":
            params += f"&category={cat}"
        return _api("get", f"/glossary{params}") or []

    verified = _fetch_verified(search_q, cat_filter)
    if not verified:
        st.info("검색 결과 없음")
    else:
        st.caption(f"{len(verified)}개")
        rows = []
        for v in verified:
            rows.append({
                "ID": v["id"],
                "용어": v["term"],
                "표준형": v["canonical_form"],
                "카테고리": v["category"],
                "신학": "✅" if v["is_theology_term"] else "",
                "빈도": v["frequency_count"],
                "별칭": ", ".join(v["aliases"]) if v["aliases"] else "",
            })
        st.dataframe(rows, use_container_width=True, height=400)


# ── Tab 3: 신학 용어 ────────────────────────────────────────────────────────
with tab_theology:
    @st.cache_data(ttl=10)
    def _fetch_theology():
        return _api("get", "/glossary?theology_only=true&verified_only=true&limit=200") or []

    theology_terms = _fetch_theology()
    st.caption(f"총 {len(theology_terms)}개 — D3 가드레일 자동 적용")

    if theology_terms:
        # 카테고리별 그룹
        from collections import defaultdict
        by_cat: dict[str, list] = defaultdict(list)
        for t in theology_terms:
            by_cat[t["category"]].append(t)

        cat_labels = {"doctrine": "교리", "person": "인물", "place": "장소",
                      "scripture": "성경", "event": "사건", "other": "기타"}
        for cat, items in sorted(by_cat.items()):
            with st.expander(f"{cat_labels.get(cat, cat)} ({len(items)}개)"):
                chips = "  ".join([f"`{i['term']}`" for i in items])
                st.markdown(chips)


# ── Tab 4: 검색/편집 ────────────────────────────────────────────────────────
with tab_search:
    st.subheader("용어 상세 편집")
    search_all = st.text_input("용어 검색", key="search_all_q")

    @st.cache_data(ttl=5)
    def _search_all(q: str):
        return _api("get", f"/glossary?q={q}&limit=20") or []

    results = _search_all(search_all) if search_all else []
    if results:
        for item in results:
            with st.expander(f"{item['term']} (빈도 {item['frequency_count']}, {'✅승인' if item['operator_verified'] else '⏳대기'})"):
                with st.form(key=f"edit_{item['id']}"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        new_def = st.text_area("정의", value=item.get("definition") or "", key=f"def_{item['id']}")
                        new_cat = st.selectbox("카테고리",
                                               ["person", "place", "doctrine", "scripture", "event", "other"],
                                               index=["person", "place", "doctrine", "scripture", "event", "other"].index(
                                                   item.get("category", "other")),
                                               key=f"cat_{item['id']}")
                    with col_b:
                        new_canonical = st.text_input("표준형", value=item.get("canonical_form", item["term"]),
                                                      key=f"canonical_{item['id']}")
                        new_theology = st.checkbox("신학 용어", value=item.get("is_theology_term", False),
                                                   key=f"theol_{item['id']}")
                    if st.form_submit_button("💾 저장"):
                        _api("patch", f"/glossary/{item['id']}", json={
                            "definition": new_def or None,
                            "category": new_cat,
                            "canonical_form": new_canonical,
                            "is_theology_term": new_theology,
                        })
                        st.cache_data.clear()
                        st.success("저장 완료")
                        st.rerun()
