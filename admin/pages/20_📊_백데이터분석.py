"""📊 백데이터 분석 — 질문/인용/키워드 트렌드 + 피드백 통계 (콜라보 파일 V 구현)."""
from __future__ import annotations

import sys
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
_ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import csv
import io
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from admin.lib.api_client import get_interaction_analytics
from admin.lib.auth import gate

st.set_page_config(page_title="백데이터 분석", page_icon="📊", layout="wide")
gate(os.getenv("APP_PASSWORD", ""))
st.title("📊 백데이터 분석 (interaction 소스)")

st.caption(
    "사용자 질문·답변 로그에서 질문 트렌드 / 문서 인용 랭킹 / 키워드 트렌드 / "
    "피드백 통계를 집계합니다. 읽기 전용 — 운영 개선 지표로 활용."
)

limit = st.slider("집계 상위 N", min_value=10, max_value=500, value=100, step=10)
if st.button("🔄 분석 실행", use_container_width=False):
    st.rerun()

data = get_interaction_analytics(limit=limit)
if data is None:
    st.error("백데이터 분석을 불러오지 못했습니다 (백엔드 연결/권한 확인).")
    st.stop()

# ── 상단 지표 ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("총 상호작용(표본)", f"{data.get('total_interactions', 0)}")
fb = data.get("feedback", {})
m2.metric("👍 긍정", fb.get("positive", 0))
m3.metric("👎 부정", fb.get("negative", 0))
cov = data.get("coverage", {})
m4.metric("미인용 자료", cov.get("uncited_documents", 0))

# V-4: 검색 커버리지 부족 지표
lc = data.get("low_coverage", {})
st.metric(
    "⚠️ 커버리지 부족(인용 없음) 비율",
    f"{lc.get('pct', 0)}%  ({lc.get('count', 0)}건)",
    help="cited 문서가 없는 상호작용 비율. 높을수록 검색/자료 커버리지 개선 필요.",
)

ld = data.get("language_distribution", {})
if not ld.get("available"):
    st.info(f"ℹ️ {ld.get('reason', '')}")

# ── 탭 구성 ────────────────────────────────────────────────────────────────
t_q, t_doc, t_kw, t_raw = st.tabs(
    ["❓ 질문 트렌드", "📚 문서 인용 랭킹", "🔤 키워드 트렌드", "📦 원시 JSON"]
)

with t_q:
    qt = data.get("question_trends", [])
    if qt:
        st.dataframe(pd.DataFrame(qt), use_container_width=True, height=420)
    else:
        st.info("데이터 없음")

with t_doc:
    dr = data.get("doc_citation_ranking", [])
    if dr:
        st.dataframe(pd.DataFrame(dr), use_container_width=True, height=420)
        st.caption(
            f"전체 자료 {cov.get('total_documents', 0)}개 중 "
            f"{cov.get('cited_documents', 0)}개 인용됨"
        )
    else:
        st.info("인용 기록 없음 (cited_versions 비어있음)")

with t_kw:
    kw = data.get("keyword_trends", [])
    if kw:
        st.dataframe(pd.DataFrame(kw), use_container_width=True, height=420)
    else:
        st.info("데이터 없음")

with t_raw:
    st.json(data)

# ── 내보내기 ────────────────────────────────────────────────────────────────
def _to_csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    return buf.getvalue()


c_col, j_col = st.columns(2)
with c_col:
    csv_q = _to_csv(data.get("question_trends", []), ["question", "count"])
    st.download_button(
        "⬇️ 질문 트렌드 CSV", csv_q, "question_trends.csv", "text/csv"
    )
with j_col:
    st.download_button(
        "⬇️ 전체 JSON",
        json.dumps(data, ensure_ascii=False, indent=2),
        "interaction_analytics.json",
        "application/json",
    )

# ── 원본 내보내기 (SQLite 직접, V-2) ─────────────────────────────────────────
st.divider()
st.subheader("🗄️ 원본 로그 내보내기 (SQLite 직접)")
st.caption(
    "백엔드를 거치지 않고 interaction 원본 행을 CSV로 덤프합니다. "
    "scripts/export_interaction_sources.py 를 서버 측에서 실행합니다."
)
if st.button("📤 원본 CSV 내보내기 실행", type="secondary"):
    import subprocess

    out_dir = _ROOT / "data" / "analytics_export"
    out_dir.mkdir(parents=True, exist_ok=True)
    py = _ROOT / "venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = "python"
    try:
        res = subprocess.run(
            [str(py), "scripts/export_interaction_sources.py", "--limit", "0", "--out", str(out_dir)],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode == 0:
            files = sorted(p.name for p in out_dir.glob("*.csv"))
            st.success(f"내보내기 완료 → {out_dir}")
            st.write("생성 파일:", files)
            with st.expander("실행 로그"):
                st.code(res.stdout or "(없음)")
        else:
            st.error("내보내기 실패")
            st.code(res.stderr or res.stdout)
    except Exception as e:  # noqa: BLE001
        st.error(f"실행 오류: {e}")
