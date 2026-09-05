"""프롬프트 - AI의 어조/지시를 운영자가 직접 편집."""
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

from admin.lib.api_client import get_prompt, save_prompt, reset_prompt, prompt_history
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.title("📝 프롬프트 (AI 어조 편집)")
st.caption("이 텍스트가 AI에게 매번 보내는 '지침서'입니다. 톤·말투·금지사항을 여기서 정하세요.")

cur = get_prompt()
if cur is None:
    st.error("API 연결 실패")
    st.stop()

st.info(
    f"**현재 사용 중**: {cur['name']}  ·  "
    f"{'운영자 편집본' if cur.get('is_custom') else '코드 기본값 (아직 편집 안 함)'}"
    + (f"  ·  마지막 수정: {cur['updated_at'][:19].replace('T', ' ')}" if cur.get('updated_at') else "")
)

st.markdown("### ✏️ 편집")
new_content = st.text_area(
    "프롬프트 내용",
    value=cur["content"],
    height=400,
    key="prompt_edit",
)

note = st.text_input("변경 메모 (선택)", placeholder="예: 더 따뜻한 톤으로", key="prompt_note")

c1, c2, c3 = st.columns([1, 1, 4])
with c1:
    if st.button("💾 저장", type="primary", key="save_prompt", help="새 프롬프트 활성화. 이전 버전은 이력에 보존, 다음 질문부터 즉시 적용"):
        if len(new_content) < 20:
            st.error("프롬프트가 너무 짧습니다 (최소 20자)")
        else:
            r = save_prompt(new_content, note=note or None)
            if r:
                st.success("✅ 저장 완료. 다음 질문부터 적용됩니다.")
                st.rerun()
with c2:
    if st.button("↩️ 기본값 복원", key="reset_prompt", help="코드에 박힌 원래 시스템 프롬프트로 복원 (편집 이력은 보존)"):
        r = reset_prompt()
        if r:
            st.success("✅ 코드 기본값으로 복원됨")
            st.rerun()
with c3:
    st.caption("⚠ 너무 길거나 추상적인 지침은 답변을 오히려 떨어뜨릴 수 있어요.")

st.divider()
st.markdown("### 📜 편집 이력")
hist = prompt_history() or []
if not hist:
    st.caption("이력 없음 (아직 한 번도 저장 안 됨)")
else:
    for h in hist:
        active = "🟢 활성" if h["active"] else "⚪ 옛 버전"
        when = h["updated_at"][:19].replace("T", " ")
        with st.expander(f"{active}  ·  {when}  ·  {h.get('note') or '메모 없음'}"):
            st.code(h["content"], language="text")
