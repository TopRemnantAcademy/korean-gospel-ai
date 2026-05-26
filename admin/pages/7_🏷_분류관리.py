"""분류 관리 - 태그/시리즈/화자/유형/구절 통합 통계."""
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

from admin.lib.api_client import get_taxonomy
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="분류 관리", page_icon="🏷", layout="wide")
st.title("🏷 분류 관리")
st.caption("올린 자료의 태그·시리즈·화자·구절을 한 곳에서 봅니다.")

if st.button("🔄 새로고침", key="tax_refresh", help="모든 자료의 태그·시리즈·화자 통계 재집계"):
    st.rerun()

data = get_taxonomy()
if not data:
    st.error("API 연결 실패")
    st.stop()

tabs = st.tabs(["주제 태그", "시리즈", "저자/화자", "자료 유형", "성경 구절"])
TYPE_KR = {"sermon":"설교","book":"책","bible":"성경","testimony":"간증",
           "prayer":"기도문","healing":"치유자료","other":"기타"}

for tab, key, title in zip(
    tabs,
    ["tags", "series", "speakers", "types", "scripture_refs"],
    ["주제 태그", "시리즈", "저자/화자", "자료 유형", "성경 구절"],
):
    with tab:
        rows = data.get(key) or []
        if not rows:
            st.info(f"{title} 데이터 없음")
            continue
        # 유형은 한국어 라벨
        if key == "types":
            rows = [{"name": TYPE_KR.get(r["name"], r["name"]), "count": r["count"]} for r in rows]
        df = pd.DataFrame(rows).rename(columns={"name": title, "count": "자료 수"})
        st.dataframe(df, use_container_width=True, height=400)
        if len(df) > 1:
            st.bar_chart(df.set_index(title))
