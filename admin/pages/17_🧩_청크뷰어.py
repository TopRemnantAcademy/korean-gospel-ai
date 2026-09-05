"""🧩 청크 뷰어 — Qdrant 청크 브라우저 + 관리 도구 (임베디드/서버 모드 통합).

탭 구성 (작업 CC):
  📋 뷰어     — 컬렉션 선택 → 페이지 탐색 → 청크 클릭(expand) → 전문·메타 보기
  🔎 검색 테스트 — 시맨틱 검색: RAG가 실제로 반환하는 청크/점수 확인 (RAG 디버깅)
  📊 통계     — 청크 품질 통계 (빈 텍스트 / 공백 오염율 등)
  🛠 관리     — 품질 불량 청크 즉시 수정(재임베딩) 또는 삭제

※ 백엔드가 보유한 동일 Qdrant 인스턴스를 재사용하는 /admin/chunks* 를 통해
  임베디드/서버 모드 모두 정상 동작한다.
"""
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
    list_chunks,
    search_chunks,
    delete_chunk,
    patch_chunk,
    chunk_stats,
)
from admin.lib.auth import gate

# set_page_config MUST be the first Streamlit command on the page (multipage rule).
# gate() itself issues st.* commands, so it must run AFTER this call.
st.set_page_config(page_title="청크 뷰어", page_icon="🧩", layout="wide")
gate(os.getenv("APP_PASSWORD", ""))
st.title("🧩 청크 뷰어 · Chunk Browser & Manager")
st.caption(
    "컬렉션 → 페이지 이동 → 청크를 클릭하면 전문과 메타데이터가 열립니다. "
    "검색/통계/관리 탭으로 RAG 품질을 디버깅하고 불량 청크를 즉시 수정·삭제할 수 있습니다."
)

LIMIT = 25

# ── 세션 상태 ───────────────────────────────────────────────
for _k, _v in {"cv_collection": None, "cv_stack": [None], "cv_search": "",
               "cv_edit": None}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _load_collections():
    try:
        d = list_chunks(limit=1)
    except Exception as e:
        return None, f"백엔드 호출 실패: {e}"
    if not isinstance(d, dict):
        return None, "백엔드 응답이 올바르지 않습니다 (연결/인증 확인)."
    return d.get("collections", []), d.get("warning")


collections, _warn = _load_collections()
if not collections:
    st.info("Qdrant에 컬렉션이 없거나 백엔드에 연결할 수 없습니다.")
    st.stop()
if _warn:
    st.warning(f"⚠️ {_warn}")
if not st.session_state.cv_collection or st.session_state.cv_collection not in collections:
    st.session_state.cv_collection = collections[0]

current = st.session_state.cv_collection

# ── 공용: 컬렉션 선택 (세션 공유) ───────────────────────────
def _collection_selector():
    def _on_collection_change():
        st.session_state.cv_stack = [None]

    sel = st.selectbox(
        "컬렉션 (Collection)",
        options=collections,
        index=collections.index(current),
        key="cv_collection_sel",
        on_change=_on_collection_change,
    )
    if sel != st.session_state.cv_collection:
        st.session_state.cv_collection = sel
        st.rerun()
    return st.session_state.cv_collection


# ── 탭 구성 ─────────────────────────────────────────────────
tab_v, tab_s, tab_t, tab_m = st.tabs(
    ["📋 뷰어", "🔎 검색 테스트", "📊 통계", "🛠 관리"]
)

# ════════════════════ 탭 1: 뷰어 ════════════════════
with tab_v:
    current = _collection_selector()

    current_cursor = st.session_state.cv_stack[-1]
    try:
        data = list_chunks(
            collection=current,
            limit=LIMIT,
            offset=current_cursor,
        )
    except Exception as e:
        st.error(f"❌ 백엔드 호출 실패: {e}")
        st.stop()

    if not isinstance(data, dict):
        st.error("❌ 백엔드 응답이 올바르지 않습니다 (연결/인증 확인).")
        st.stop()
    if data.get("warning"):
        st.warning(f"⚠️ {data['warning']}")

    total = data.get("total", 0)
    points = data.get("points", [])
    next_cursor = data.get("next_offset")
    page_no = len(st.session_state.cv_stack)

    c1, c2, c3 = st.columns(3)
    c1.metric("컬렉션", current)
    c2.metric("전체 청크", f"{total:,}")
    c3.metric("페이지", f"{page_no}")

    st.session_state.cv_search = st.text_input(
        "🔍 청크 검색 (현재 페이지 · 텍스트/문서ID/제목)",
        value=st.session_state.cv_search,
    )
    q = st.session_state.cv_search.strip().lower()

    def _match(p: dict) -> bool:
        if not q:
            return True
        keys = ("text", "doc_id", "document_id", "title", "doc_title", "source")
        hay = " ".join(str(p.get(k, "")) for k in keys).lower()
        return q in hay

    filtered = [p for p in points if _match(p)]

    has_prev = page_no > 1
    has_next = next_cursor is not None

    nav1, nav2, nav3 = st.columns([1, 1, 3])
    with nav1:
        if st.button("← 이전", key="cv_prev") and has_prev:
            st.session_state.cv_stack.pop()
            st.rerun()
    with nav2:
        if st.button("다음 →", key="cv_next") and has_next:
            st.session_state.cv_stack.append(next_cursor)
            st.rerun()
    with nav3:
        st.caption(
            f"페이지 {page_no} · 페이지당 {LIMIT} · 검색 결과 "
            f"{len(filtered)}/{len(points)}개 (전체 {total:,})"
        )

    if not filtered:
        st.info("표시할 청크가 없습니다.")
    else:
        for i, p in enumerate(filtered):
            pid = p.get("id", "?")
            text = p.get("text", "")
            payload = p.get("payload", {}) or {}
            doc_id = (
                payload.get("doc_id")
                or payload.get("document_id")
                or payload.get("source")
                or "-"
            )
            title = payload.get("title") or payload.get("doc_title") or ""
            preview = (text[:90] + "…") if len(text) > 90 else text
            head = (
                f"#{i + 1} · {doc_id}"
                + (f" · {title}" if title else "")
                + f" · {len(text)}자"
            )
            with st.expander(head):
                st.markdown(f"**청크 ID:** `{pid}`")
                st.markdown("**전문:**")
                st.text_area(
                    f"chunk_text_{pid}",
                    text,
                    height=min(360, max(120, len(text) // 2)),
                    disabled=True,
                    label_visibility="collapsed",
                )
                meta = {k: v for k, v in payload.items() if k != "text"}
                if meta:
                    st.markdown("**메타데이터:**")
                    st.json(meta)
                if st.button("🛠 관리에서 열기", key=f"vm_{pid}"):
                    st.session_state.cv_edit = {
                        "id": pid, "text": text, "payload": payload,
                    }
                    st.rerun()

# ════════════════════ 탭 2: 검색 테스트 ════════════════════
with tab_s:
    st.markdown("**시맨틱 검색** — 운영자가 질의를 입력하면 RAG가 실제로 "
                "어떤 청크를 반환하는지, 점수가 얼마인지 즉시 확인 (RAG 디버깅).")
    st.caption(f"대상 컬렉션: `{current}`")

    sq = st.text_input("질의 (query)", key="cv_s_query",
                       placeholder="예: 구원")
    scol1, scol2 = st.columns([1, 2])
    with scol1:
        slim = st.number_input("결과 수", 1, 50, 10, key="cv_s_lim")
    with scol2:
        st.write("")
        sgo = st.button("🔎 검색", key="cv_s_btn", use_container_width=True)

    if sgo and sq.strip():
        with st.spinner("임베딩 + 검색 중..."):
            res = search_chunks(
                sq, collection=current, limit=int(slim),
            )
        if not res or res.get("error"):
            st.error(res.get("error") if res else "호출 실패")
        elif res.get("warning"):
            st.warning(f"⚠️ {res['warning']}")
        else:
            pts = res.get("points", [])
            st.success(f"{len(pts)}개 결과 · 컬렉션 `{res.get('collection')}`")
            for p in pts:
                pid = p.get("id")
                score = p.get("score", 0.0)
                with st.expander(f"score={score:.4f} · `{pid}`"):
                    st.markdown(f"**청크 ID:** `{pid}`")
                    st.text_area(
                        f"s_text_{pid}", p.get("text", ""), height=160,
                        disabled=True, label_visibility="collapsed",
                    )
                    meta = {k: v for k, v in (p.get("payload") or {}).items() if k != "text"}
                    if meta:
                        st.json(meta)
                    if st.button("🛠 관리에서 열기", key=f"sm_{pid}"):
                        st.session_state.cv_edit = {
                            "id": pid, "text": p.get("text", ""),
                            "payload": p.get("payload", {}),
                        }
                        st.rerun()

# ════════════════════ 탭 3: 통계 ════════════════════
with tab_t:
    st.markdown("**청크 품질 통계** — 빈 텍스트 / 단어 중간 공백 오염율 등 운영 지표.")
    st.caption(f"대상 컬렉션: `{current}`")
    with st.spinner("집계 중..."):
        res = chunk_stats(collection=current)
    if not res or res.get("error"):
        st.error(res.get("error") if res else "호출 실패")
    elif res.get("warning"):
        st.warning(f"⚠️ {res['warning']}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("전체 청크", f"{res.get('total', 0):,}")
        c2.metric("검사한 청크", f"{res.get('examined', 0):,}")
        c3.metric("빈 텍스트", res.get("empty_text", 0))
        c4.metric("공백오염 의심", res.get("high_space_ratio_ge0_35", 0))
        st.markdown(
            f"- 5자 미만 초단문: **{res.get('very_short_lt5', 0)}**\n"
            f"- 연속 공백/탭 포함: **{res.get('multi_space_or_tab', 0)}**"
        )
        st.markdown("**상위 소스 (소스별 청크 수):**")
        st.json(res.get("top_sources", {}))

# ════════════════════ 탭 4: 관리 ════════════════════
with tab_m:
    st.markdown("**청크 수정 / 삭제**")
    st.caption("뷰어/검색에서 '관리에서 열기'를 누르면 아래에 자동 로드됩니다. "
               "직접 ID·텍스트를 입력해도 됩니다. 텍스트 수정 시 dense 벡터가 "
               "자동 재계산되어 검색 품질이 즉시 개선됩니다.")

    ed = st.session_state.get("cv_edit") or {}
    mcid = st.text_input("청크 ID", value=ed.get("id", ""), key="cv_m_id")
    mtext = st.text_area(
        "텍스트 (수정 시 입력)", value=ed.get("text", ""),
        height=240, key="cv_m_text",
    )

    mcol1, mcol2 = st.columns(2)
    with mcol1:
        if st.button("💾 텍스트 수정 저장", key="cv_m_save",
                     use_container_width=True) and mcid.strip():
            with st.spinner("수정 + 재임베딩 중..."):
                res = patch_chunk(
                    mcid, text=mtext, collection=current,
                )
            if res and res.get("ok"):
                st.success(f"✅ 수정 완료 — 갱신: {res.get('updated')}")
                if res.get("warning"):
                    st.warning(res["warning"])
            elif res and res.get("warning"):
                st.warning(f"⚠️ {res['warning']}")
            else:
                st.error(res.get("error") if res else "호출 실패")
    with mcol2:
        if st.button("🗑 삭제", key="cv_m_del",
                     use_container_width=True) and mcid.strip():
            if st.checkbox("정말 삭제하시겠습니까?", key="cv_m_conf"):
                res = delete_chunk(mcid, collection=current)
                if res and res.get("ok"):
                    st.success("✅ 삭제 완료")
                    st.session_state.cv_edit = None
                elif res and res.get("warning"):
                    st.warning(f"⚠️ {res['warning']}")
                else:
                    st.error(res.get("error") if res else "호출 실패")
