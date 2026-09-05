"""💲 원가 단가 관리 — 실제 LLM 단가 + 환율 기준일 직접 입력/조회.

기획 의도 (사용자 요청 ①):
  터미널의 `seed_ccp_rates.py --note` 가 아닌 **Admin Hub UI 에서 직접** LLM 원가 단가를
  등록·관리한다. 등록 시 반드시 "공급자 가격표 출처 / 환율 기준일"을 source_note 로 입력해
  세무·보조금 증빙 근거를 남긴다 (CCP 모듈의 핵심 요구사항).

데이터 정합성:
  - 단가는 SCD Type 2 로 관리 → 같은 (provider, model) 에 신규 단가를 추가하면
    기존 유효 구간은 자동 종료(effective_to 채움)되고 새 구간이 개시된다.
  - 단가는 1,000 토큰 기준(Numeric 18,6)이며 통화(currency)와 적용 시작 시각을 지정한다.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
while _ROOT.name in ("pages", "lib"):
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from admin.lib.api_client import admin_list_ccp_rates, admin_create_ccp_rate
from admin.lib.auth import gate

gate()  # APP_PASSWORD (없으면 로그인 UI)

st.set_page_config(page_title="원가 단가 관리", page_icon="💲", layout="wide")
st.title("💲 원가 단가 관리")
st.caption(
    "실제 LLM 단가와 환율 기준일을 직접 등록·조회합니다. "
    "등록 시 반드시 **공급자 가격표 출처 + 환율 기준일**을 적으세요 (증빙 근거)."
)

# 하드코딩 금지 원칙: 선택지도 상수로 관리하되 운영 환경에 맞춰 자유 입력 가능
KNOWN_PROVIDERS = ["gemini", "nvidia", "tencent", "openai", "claude", "ollama", "deepseek"]
KNOWN_CURRENCIES = ["KRW", "USD", "CNY"]


def _fmt_dt(value) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value)


def _reload():
    return admin_list_ccp_rates()


# --------------------------------------------------------------------------- #
# 1) 현재 유효 단가 목록
# --------------------------------------------------------------------------- #
st.subheader("📋 현재 유효 단가")
if st.button("🔄 새로고침", key="ccp_refresh"):
    st.rerun()

rates = _reload()
if rates is None:
    st.error("단가 조회 실패 — 백엔드/인증을 확인하세요.")
elif not rates:
    st.info("등록된 단가가 없습니다. 아래에서 첫 단가를 등록하세요.")
else:
    rows = []
    for r in rates:
        rows.append(
            {
                "provider": r.get("provider"),
                "model": r.get("model"),
                "입력/1K": r.get("input_price_per_1k"),
                "출력/1K": r.get("output_price_per_1k"),
                "통화": r.get("currency"),
                "적용 시작": _fmt_dt(r.get("effective_from")),
                "출처/환율기준일": r.get("source_note") or "—",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()

# --------------------------------------------------------------------------- #
# 2) 신규 단가 등록
# --------------------------------------------------------------------------- #
st.subheader("➕ 신규 단가 등록")

with st.form("ccp_rate_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox("Provider", KNOWN_PROVIDERS, index=0)
        provider_free = st.text_input("또는 직접 입력 (Provider)", "", placeholder="위 목록 외 provider")
        model = st.text_input("Model", placeholder="예: gemini-2.5-flash, DeepSeek-V4 등")
    with col2:
        currency = st.selectbox("통화", KNOWN_CURRENCIES, index=0)
        input_price = st.number_input(
            "입력 단가 (통화 / 1,000 토큰)", min_value=0.0, value=0.0, step=0.0001, format="%.4f"
        )
        output_price = st.number_input(
            "출력 단가 (통화 / 1,000 토큰)", min_value=0.0, value=0.0, step=0.0001, format="%.4f"
        )

    effective_from = st.text_input(
        "적용 시작 시각 (ISO 8601, 비우면 지금)",
        "",
        placeholder="예: 2026-08-03T00:00:00Z (비우면 등록 시점)",
    )
    source_note = st.text_area(
        "출처 / 환율 기준일 (필수)",
        placeholder="예: Tencent Cloud 가격표 https://... (조회 2026-08-03), 환율 1 USD=1,380 KRW 기준 2026-08-01",
        help="세무·보조금 증빙 근거. 공급자 가격표 URL + 환율 기준일을 명시하세요.",
    )

    submitted = st.form_submit_button("💾 단가 등록", type="primary")

    if submitted:
        _provider = provider_free.strip() or provider
        if not _provider or not model.strip():
            st.error("Provider 와 Model 은 필수입니다.")
        elif not source_note.strip():
            st.error("출처 / 환율 기준일은 필수입니다 (증빙 근거).")
        elif input_price < 0 or output_price < 0:
            st.error("단가는 0 이상이어야 합니다.")
        else:
            with st.spinner("등록 중…"):
                result = admin_create_ccp_rate(
                    provider=_provider,
                    model=model.strip(),
                    input_price_per_1k=input_price,
                    output_price_per_1k=output_price,
                    source_note=source_note.strip(),
                    currency=currency,
                    effective_from=effective_from.strip() or None,
                )
            if result and result.get("rate_card_id"):
                st.success(
                    f"✅ 등록 완료: {_provider}/{model.strip()} "
                    f"(입력 {input_price} / 출력 {output_price} {currency})"
                )
                st.json(result)
                st.rerun()
            else:
                st.error("등록 실패 — 응답을 확인하세요 (중복 구간이거나 권한 문제일 수 있음).")

st.divider()
st.caption(
    "ℹ️ 단가는 SCD Type 2 로 관리됩니다: 같은 (provider, model) 에 신규 단가를 추가하면 "
    "기존 유효 구간은 자동 종료되고 새 구간이 개시됩니다. 과거 이력은 보존됩니다."
)
