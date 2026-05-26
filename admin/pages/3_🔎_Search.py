"""Search - 질문하고 답 받기."""
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

from admin.lib.api_client import chat, list_documents, set_feedback
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="질문하고 답 받기", page_icon="🔎", layout="wide")
st.title("🔎 질문하고 답 받기")
st.caption("올린 자료를 근거로 답합니다. 답변에는 항상 출처가 함께 표시됩니다.")

# === 첫 사용 안내: 공개된 자료가 없으면 ===
docs = list_documents() or []
published_count = sum(1 for d in docs if (d.get("published_version") or 0) > 0)

if published_count == 0:
    st.warning(
        "🛑 **아직 검색 가능한 자료가 없습니다.**\n\n"
        "📥 Upload에서 자료를 올린 다음, 📚 Library에서 **'검색에 공개하기'** 버튼을 눌러야 검색이 가능합니다."
    )
    st.stop()

st.caption(f"💚 현재 검색 가능한 자료: **{published_count}개**")
st.divider()

# === 세션 상태 ===
if "search_msgs" not in st.session_state:
    st.session_state.search_msgs = []

# === 예시 질문 (대화가 비어있을 때만) ===
if not st.session_state.search_msgs:
    st.subheader("💡 이런 질문을 해보세요")
    examples = [
        "죄란 무엇인가요?",
        "어떻게 구원받을 수 있나요?",
        "삶이 힘들 때 위로가 되는 말씀은?",
        "거듭난다는 것은 무엇입니까?",
        "하나님의 사랑이 얼마나 큰가요?",
        "기도는 어떻게 해야 하나요?",
    ]
    cols = st.columns(3)
    for i, ex in enumerate(examples):
        with cols[i % 3]:
            if st.button(ex, key=f"ex_{i}", use_container_width=True, help="이 예시 질문으로 바로 시작"):
                st.session_state._pending_query = ex
                st.rerun()
    st.divider()

# === 대화 영역 ===
main_col, side_col = st.columns([4, 1])

with side_col:
    st.markdown("**설정**")
    if st.button("🗑 대화 지우기", use_container_width=True, key="search_reset", help="화면 표시만 지움. DB의 대화기록은 보존됩니다"):
        st.session_state.search_msgs = []
        st.rerun()
    debug_mode = st.toggle("🔬 디버그 모드", value=False, key="search_debug",
                            help="후보 청크, 정책 점수, 메모리 등 내부 정보 표시")
    st.caption("---")
    st.caption("⚙️ Gemini + KURE-v1")

with main_col:
    # 기존 대화
    for m in st.session_state.search_msgs:
        with st.chat_message(m["role"], avatar="✝" if m["role"] == "assistant" else "🙋"):
            st.markdown(m["content"])
            if m.get("sources"):
                with st.expander(f"📎 참고한 출처 {len(m['sources'])}개 보기"):
                    for j, s in enumerate(m["sources"], 1):
                        meta = s.get("metadata", {})
                        title = meta.get("title", "(제목 없음)")
                        ver = meta.get("version_number", "?")
                        doc_type = meta.get("doc_type", "")
                        # 친근한 라벨
                        type_kr = {
                            "sermon": "설교", "book": "책", "bible": "성경",
                            "testimony": "간증", "prayer": "기도문",
                            "healing": "치유자료", "other": "기타"
                        }.get(doc_type, doc_type)
                        st.markdown(
                            f"**{j}. {title}**  ·  *{type_kr}* v{ver}  ·  관련도 `{s['score']:.2f}`\n\n"
                            f"> {s['text'][:300]}..."
                        )
            if m.get("debug_info"):
                with st.expander("🔬 디버그 정보 (후보 청크/정책/메모리)"):
                    di = m["debug_info"]
                    st.markdown(f"**검색 후보**: {di.get('candidate_count', 0)}개  ·  "
                                f"**메모리 사전 대화 쌍**: {di.get('memory_prior_pairs', 0)}  ·  "
                                f"**시스템 프롬프트 길이**: {di.get('system_prompt_len', 0)}자")
                    if di.get("safety_triggered"):
                        st.warning(f"⚠ 안전망 발동: {di['safety_triggered']}")
                    cands = di.get("candidates", [])
                    if cands:
                        st.markdown("**후보 청크 (rerank 후 순위):**")
                        import pandas as _pd
                        df = _pd.DataFrame([{
                            "순위": k+1,
                            "제목": c["title"],
                            "v": c["version"],
                            "rerank점수": c["score"],
                            "RRF": c["rrf_score"],
                            "미리보기": c["preview"][:80] + "...",
                        } for k, c in enumerate(cands)])
                        st.dataframe(df, use_container_width=True, hide_index=True)
            if m.get("meta"):
                st.caption(f"⚡ {m['meta']}")
            # 👍/👎 피드백
            iid = m.get("interaction_id")
            if iid:
                fbcols = st.columns([1, 1, 8])
                cur_fb = m.get("feedback")
                with fbcols[0]:
                    if st.button("👍" + (" ✓" if cur_fb == 1 else ""),
                                  key=f"up_{iid}", use_container_width=True, help="이 답이 좋았어요. 대화기록에 누적됩니다"):
                        set_feedback(iid, 1)
                        m["feedback"] = 1
                        st.rerun()
                with fbcols[1]:
                    if st.button("👎" + (" ✓" if cur_fb == -1 else ""),
                                  key=f"down_{iid}", use_container_width=True, help="이 답이 좋지 않았어요"):
                        set_feedback(iid, -1)
                        m["feedback"] = -1
                        st.rerun()

    # === 입력 (예시 질문 처리) ===
    pending = st.session_state.pop("_pending_query", None)
    prompt = pending or st.chat_input("질문을 한국어로 입력하세요...")

    if prompt:
        st.session_state.search_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🙋"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="✝"):
            with st.status("처리 중", expanded=False) as status:
                status.update(label="📚 자료에서 관련 청크 검색 중...", state="running")
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.search_msgs[:-1]
                ]
                resp = chat(prompt, history, debug=debug_mode)
                status.update(label="✅ 답변 도착", state="complete")
            if resp:
                st.markdown(resp["answer"])
                pol = resp.get("policy", {})
                meta = f"⏱ {resp.get('elapsed_ms', 0)}ms"
                if not pol.get("output_pass", True):
                    meta += " · ⚠ 정책 검토됨"
                st.caption(meta)
                st.session_state.search_msgs.append({
                    "role": "assistant",
                    "content": resp["answer"],
                    "sources": resp.get("sources", []),
                    "meta": meta,
                    "interaction_id": resp.get("interaction_id"),
                    "feedback": None,
                    "debug_info": resp.get("debug_info"),
                })
                # rerun to show source expander properly
                st.rerun()
