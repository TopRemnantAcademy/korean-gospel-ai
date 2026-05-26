"""Status - 시스템 현황."""
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
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import get_collections, list_documents, run_regression
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="시스템 현황", page_icon="📊", layout="wide")
st.title("📊 시스템 현황")
st.caption("자료/검색 데이터의 전체 통계입니다.")

if st.button("🔄 새로고침", key="status_refresh", help="최신 자료/인덱스 통계 다시 불러옴"):
    st.rerun()

st.divider()

# ===== 자료 통계 =====
st.subheader("📚 자료 통계")
docs = list_documents() or []
if not docs:
    st.info("아직 올린 자료가 없습니다. 📥 Upload 페이지에서 첫 자료를 올려보세요.")
else:
    states = {}
    for d in docs:
        s = d.get("latest_state", "?")
        states[s] = states.get(s, 0) + 1

    KR = {
        "draft": "임시", "validated": "검증완료",
        "published": "공개됨", "superseded": "옛 버전",
        "archived": "보관됨",
    }
    chart_data = pd.DataFrame({"개수": {KR.get(k, k): v for k, v in states.items()}})
    st.bar_chart(chart_data)

# ===== 검색 인덱스 (Qdrant) =====
st.divider()
st.subheader("🗂 검색 인덱스 (벡터 DB)")
st.caption("실제 검색에 사용되는 텍스트 조각(chunk) 통계.")

info = get_collections()
if info is None:
    st.error("API 연결 실패")
elif info.get("warning"):
    st.warning(f"안내: {info['warning']}")
    st.caption("아직 자료를 공개한 적이 없으면 정상입니다.")
else:
    cols = info.get("collections", [])
    if not cols:
        st.info("아직 검색 인덱스에 등록된 자료가 없습니다. 📚 Library에서 자료를 공개해 보세요.")
    else:
        df = pd.DataFrame(cols).rename(columns={
            "name": "컬렉션",
            "points_count": "청크 수",
            "vectors_count": "벡터 수",
            "status": "상태",
        })
        st.dataframe(df, use_container_width=True)



# ===== 평가셋 회귀 =====
st.divider()
st.subheader("🧪 평가셋 검증 (회귀 테스트)")
st.caption("data/eval/questions.json 의 질문들을 현재 검색 시스템으로 돌려봅니다.")
if st.button("▶️ 평가 실행", key="run_eval", help="data/eval/questions.json의 질문들을 현재 검색으로 돌려 품질 점검"):
    with st.spinner("평가 실행 중..."):
        res = run_regression()
    if res and res.get("ok"):
        st.success(f"통과 {res['passed']}/{res['total']}건")
        rows = []
        for it in res["items"]:
            rows.append({
                "질문": it["query"],
                "상위3 자료": ", ".join(it["top_titles"]),
                "top1 점수": round(it.get("top1_score", 0), 3),
                "기대 일치": "✅" if it.get("expected_match") else ("❌" if it.get("expected_match") is False else "-"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    elif res:
        st.error(res.get("reason", "평가 실패"))
