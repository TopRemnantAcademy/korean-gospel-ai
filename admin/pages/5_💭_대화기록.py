"""대화기록 - 사용자가 이전에 했던 모든 Q/A 기록."""
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

from admin.lib.api_client import list_memory, memory_stats, delete_memory
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="대화기록", page_icon="💭", layout="wide")
st.title("💭 대화기록")
st.caption("이전에 했던 모든 질문과 답변. 시스템이 이걸 기억해서 다음 답변에 활용합니다.")

# 통계
stats = memory_stats() or {}
c1, c2 = st.columns(2)
c1.metric("전체 대화 수", stats.get("total", 0))
c2.metric("최근 7일", stats.get("last_7_days", 0))

st.divider()

# 검색/필터
sc1, sc2 = st.columns([3, 1])
with sc1:
    search = st.text_input(
        "🔍 검색 (질문 또는 답변에 들어간 단어)",
        key="mem_search",
        placeholder="예: 구원, 회개, 사랑...",
    )
with sc2:
    if st.button("🔄 새로고침", use_container_width=True, key="mem_refresh", help="최신 대화 기록 다시 불러옴"):
        st.rerun()

# 데이터 로드
items = list_memory(search=search if search else None, limit=200) or []

if not items:
    if search:
        st.info(f"'{search}' 와 일치하는 대화가 없습니다.")
    else:
        st.info(
            "아직 대화 기록이 없습니다.\n\n"
            "🔎 **Search** 페이지에서 질문을 하면 여기에 자동으로 쌓입니다."
        )
    st.stop()

st.caption(f"총 **{len(items)}건** 표시 중 (최신순)")

# 대화 카드 표시
for it in items:
    when = (it.get("created_at") or "")[:19].replace("T", " ")
    q = it["question"]
    a = it["answer"]
    cited = it.get("cited_versions") or []
    elapsed = it.get("elapsed_ms", 0)

    # 카드 형태 (expander)
    title = f"📅 {when}  ·  {q[:80]}{'...' if len(q) > 80 else ''}"
    with st.expander(title):
        st.markdown(f"**🙋 질문:** {q}")
        st.markdown(f"**✝ 답변:**")
        st.markdown(a)

        if cited:
            with st.expander(f"📎 참고한 자료 {len(cited)}개"):
                for j, c in enumerate(cited, 1):
                    title_src = c.get("title") or c.get("doc_id") or "(제목 없음)"
                    ver = c.get("version_number", "?")
                    score = c.get("score", 0)
                    st.markdown(f"{j}. **{title_src}** v{ver} · 관련도 `{score:.2f}`")

        bot_c1, bot_c2, bot_c3 = st.columns([1, 1, 4])
        with bot_c1:
            st.caption(f"⏱ {elapsed} ms")
        with bot_c2:
            fb = it.get("feedback")
            fb_label = "👍 좋음" if fb == 1 else ("👎 안좋음" if fb == -1 else "(평가 없음)")
            st.caption(fb_label)
        with bot_c3:
            if st.button("🗑 삭제", key=f"del_{it['interaction_id']}", help="이 대화 한 건을 영구 삭제"):
                r = delete_memory(it["interaction_id"])
                if r:
                    st.success("삭제됨")
                    st.rerun()
