"""관리자 — 번역 용어집 (Translation Glossary) 관리 페이지.

자동 추출 용어집을 대체한다. KO→ZH(简体)+EN 매핑을 직접 편집하며,
이 데이터는 채팅/문서 번역 프롬프트에 강제 주입되어 번역 일관성을 보장한다.
백엔드 모듈을 import 하지 않고 glossary.json 을 직접 읽고 써서 가볍게 동작한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

GLOSSARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "app"
    / "services"
    / "enhanced_rag"
    / "data"
    / "glossary.json"
)


def load_data() -> dict:
    if not GLOSSARY_PATH.exists():
        return {"version": "v2", "source_lang": "ko", "target_langs": ["zh", "en"], "terms": []}
    return json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))


def save_data(data: dict) -> None:
    GLOSSARY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


st.set_page_config(page_title="번역 용어집", layout="wide")
st.title("📚 번역 용어집 (KO → ZH + EN)")
st.caption(
    "신학 용어의 중국어/영어 대응어를 관리합니다. 채팅·문서 번역 프롬프트에 강제 주입되어 "
    "번역 일관성을 보장합니다. (자동 추출 용어집은 제거됨)"
)

data = load_data()
terms: list[dict] = data.setdefault("terms", [])

# ── 통계 ──
total = len(terms)
missing_en = sum(1 for t in terms if not t.get("en"))
c1, c2, c3 = st.columns(3)
c1.metric("총 용어", total)
c2.metric("중국어 입력", sum(1 for t in terms if t.get("zh")))
c3.metric("영어 미입력", missing_en)

# ── 신규 추가 ──
with st.expander("➕ 신규 용어 추가", expanded=False):
    with st.form("add_term", clear_on_submit=True):
        a1, a2, a3 = st.columns(3)
        ko = a1.text_input("한국어 *")
        zh = a2.text_input("중국어 *")
        en = a3.text_input("영어")
        if st.form_submit_button("추가"):
            if not ko or not zh:
                st.warning("한국어와 중국어는 필수입니다.")
            elif any(t.get("ko") == ko for t in terms):
                st.warning(f"'{ko}' 는 이미 존재합니다.")
            else:
                terms.append({"ko": ko, "zh": zh, "en": en})
                save_data(data)
                st.success(f"'{ko}' 추가됨")
                st.rerun()

# ── 편집 / 삭제 ──
st.subheader("용어 편집 / 삭제")

EDIT_NONE_LABEL = "— 선택 안 함 —"


def _edit_on_select() -> None:
    """편집 대상이 바뀌면 입력란을 해당 용어 값으로 동기화."""
    s = st.session_state.get("edit_sel")
    if s and s in options and s != EDIT_NONE_LABEL:
        tt = terms[options.index(s) - 1]
        st.session_state["edit_ko"] = tt.get("ko", "")
        st.session_state["edit_zh"] = tt.get("zh", "")
        st.session_state["edit_en"] = tt.get("en", "")
    else:
        st.session_state["edit_ko"] = ""
        st.session_state["edit_zh"] = ""
        st.session_state["edit_en"] = ""


if not terms:
    st.info("등록된 용어가 없습니다.")
else:
    options = [EDIT_NONE_LABEL] + [
        f"{t.get('ko','')} → {t.get('zh','')} ({t.get('en','') or 'EN?'})" for t in terms
    ]
    sel = st.selectbox(
        "편집할 용어 선택",
        options,
        index=0,
        key="edit_sel",
        on_change=_edit_on_select,
    )

    if sel == EDIT_NONE_LABEL:
        st.info("편집할 용어를 선택하세요.")
    else:
        idx = options.index(sel) - 1
        with st.form("edit_term"):
            e1, e2, e3 = st.columns(3)
            ko_v = e1.text_input("한국어", key="edit_ko")
            zh_v = e2.text_input("중국어", key="edit_zh")
            en_v = e3.text_input("영어", key="edit_en")
            b1, b2 = st.columns(2)
            save_btn = b1.form_submit_button("💾 저장")
            del_btn = b2.form_submit_button("🗑 삭제", type="secondary")
            if save_btn:
                if not ko_v or not zh_v:
                    st.warning("한국어와 중국어는 필수입니다.")
                else:
                    terms[idx] = {"ko": ko_v, "zh": zh_v, "en": en_v}
                    save_data(data)
                    st.success("저장됨")
                    # 저장 직후 입력란 비우기 + 선택 해제
                    st.session_state["edit_sel"] = EDIT_NONE_LABEL
                    st.session_state["edit_ko"] = ""
                    st.session_state["edit_zh"] = ""
                    st.session_state["edit_en"] = ""
                    st.rerun()
            if del_btn:
                terms.pop(idx)
                save_data(data)
                st.success("삭제됨")
                st.session_state["edit_sel"] = EDIT_NONE_LABEL
                st.session_state["edit_ko"] = ""
                st.session_state["edit_zh"] = ""
                st.session_state["edit_en"] = ""
                st.rerun()

# ── 목록 (검색) ──
st.divider()
st.subheader("전체 목록")
q = st.text_input("검색 (한국어/중국어/영어)", "")
view = terms
if q:
    view = [
        t
        for t in terms
        if q.lower() in (t.get("ko", "") + t.get("zh", "") + t.get("en", "")).lower()
    ]
if view:
    st.dataframe(
        [
            {
                "한국어": t.get("ko", ""),
                "중국어": t.get("zh", ""),
                "영어": t.get("en", "") or "—",
            }
            for t in view
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("검색 결과가 없습니다.")

st.divider()
st.caption(
    f"데이터 파일: {GLOSSARY_PATH} · 버전 {data.get('version','?')} · "
    "수정 즉시 번역에 반영됩니다."
)
