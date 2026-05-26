"""Upload - 새 자료 올리기 (단순화 + 친근)."""
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

from admin.lib.api_client import upload_document
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="새 자료 올리기", page_icon="📥", layout="wide")
st.title("📥 새 자료 올리기")
st.caption("완성된 자료를 올립니다. 큰 수정은 외부 편집 후 다시 올려주세요. (= 자동으로 새 버전 생성)")

# 친근한 문서 유형 이름 매핑
DOC_TYPE_LABELS = {
    "sermon": "설교",
    "book": "책 / 신학서",
    "bible": "성경",
    "testimony": "간증",
    "prayer": "기도문",
    "healing": "치유 / 상담 자료",
    "other": "기타",
}
DOC_TYPE_OPTIONS = list(DOC_TYPE_LABELS.values())
DOC_TYPE_REV = {v: k for k, v in DOC_TYPE_LABELS.items()}

# === 업로드 성공 결과 표시 ===
if "last_upload" in st.session_state and st.session_state.last_upload:
    r = st.session_state.last_upload
    st.success(f"✅ 업로드 완료: **{r['title']}** (v{r['version_number']}, 상태: `{r['state']}`)")
    q = r.get("extraction_quality_score", 0)
    if q >= 80:
        st.caption(f"📊 추출 품질 {q}/100 (좋음)")
    elif q >= 50:
        st.caption(f"📊 추출 품질 {q}/100 (보통 — 검토 권장)")
    else:
        st.caption(f"⚠ 추출 품질 {q}/100 (낮음 — 자료실에서 본문 확인 필요)")

    # 중복 자료 경고
    hits = r.get("dup_hits") or []
    if hits:
        for h in hits:
            kind = h.get("kind", "")
            label = {"identical": "⚠ 완전 동일", "version": "💡 새 버전 후보", "similar": "🔍 유사 자료"}.get(kind, kind)
            st.warning(f"**{label}** — *{h.get('title','?')}*\n\n{h.get('reason','')}")

    if r.get("extraction_warnings"):
        with st.expander(f"⚠ 추출 경고 ({len(r['extraction_warnings'])}개)"):
            st.json(r["extraction_warnings"])

    if r.get("jsonl_path"):
        st.caption(f"📄 JSONL 생성됨: `{r['jsonl_path']}`")

    # D-C17: 구원 메타 요약 표시
    _stages = r.get("target_salvation_stage") or []
    _tier = r.get("darakbang_tier")
    _score = r.get("salvation_focus_score", 0.0)
    _core = r.get("gospel_core_tag", False)
    if _stages or _tier or _score or _core:
        meta_parts = []
        if _stages:
            meta_parts.append(f"단계: `{', '.join(_stages)}`")
        if _tier:
            meta_parts.append(f"다락방 등급: `{_tier}`")
        if _score:
            meta_parts.append(f"구원 집중도: `{_score:.2f}`")
        if _core:
            meta_parts.append("⭐ 구원 핵심 자료")
        st.caption("🕊 " + " · ".join(meta_parts))

    with st.expander("📄 추출된 본문 미리보기"):
        st.text(r.get("extracted_text_preview", ""))

    st.info(
        "🎯 **다음 단계** — 이 자료는 **임시(Draft)** 상태입니다. 검색에 노출하려면:\n\n"
        "1. 왼쪽 사이드바에서 **📚 Library** 클릭\n"
        "2. 방금 올린 자료 선택\n"
        "3. **'검증/Publish' 탭** → 체크리스트 4개 확인 → **'검색에 공개하기'**"
    )
    if st.button("✖ 결과 닫기", key="close_result", help="결과창을 닫고 새 자료 업로드 폼으로 돌아갑니다"):
        st.session_state.last_upload = None
        st.rerun()
    st.divider()


# === 업로드 폼 ===
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("#### 1️⃣ 파일")
    file = st.file_uploader(
        "PDF · DOCX · TXT · MD 형식 지원",
        accept_multiple_files=False,
        key="up_file",
    )
    if file:
        st.success(f"✅ {file.name}  ·  {file.size:,} bytes")
    else:
        st.caption("👉 클릭하거나 파일을 끌어다 놓으세요")

with col2:
    st.markdown("#### 2️⃣ 기본 정보")
    title = st.text_input(
        "제목 *",
        key="up_title",
        placeholder="예: 롬5장 - 화평을 누리자",
        help="검색 결과에 표시될 자료 제목",
    )
    doc_type_label = st.selectbox(
        "자료 종류 *",
        DOC_TYPE_OPTIONS,
        key="up_type_label",
        help="자료의 성격에 맞게 선택",
    )
    doc_type = DOC_TYPE_REV[doc_type_label]

    with st.expander("➕ 추가 정보 (선택)"):
        series = st.text_input("시리즈명", key="up_series",
                                placeholder="예: 로마서 강해")
        speaker = st.text_input("저자 / 화자", key="up_speaker",
                                 placeholder="예: 홍길동 목사")
        tags = st.text_input(
            "주제 태그",
            key="up_tags",
            placeholder="예: 화평, 칭의, 고난  (쉼표로 구분)",
        )
        refs = st.text_input(
            "본문 구절",
            key="up_refs",
            placeholder="예: 롬 5:1, 롬 5:8, 요 3:16",
        )
        summary = st.text_area("요약", height=80, key="up_summary",
                                placeholder="이 자료의 핵심을 한두 줄로")

    # D-C17: 구원 상태 메타
    with st.expander("🕊 구원 단계 / 다락방 분류 (D-C17)", expanded=False):
        st.caption("검색 시 사용자 구원 상태에 맞는 자료가 우선 노출됩니다.")

        _SALVATION_STAGE_OPTIONS = [
            "seeker", "uncertain", "assured", "mature",
            "gospel_core", "assurance", "discipleship", "leadership", "pastoral",
        ]
        _STAGE_LABELS = {
            "seeker": "전도 대상 (seeker)",
            "uncertain": "구원 불확실 (uncertain)",
            "assured": "구원 확신 (assured)",
            "mature": "성숙한 신자 (mature)",
            "gospel_core": "구원 핵심 자료",
            "assurance": "확신 훈련 자료",
            "discipleship": "제자도 자료",
            "leadership": "리더십 자료",
            "pastoral": "사역자 자료",
        }
        selected_stages = st.multiselect(
            "대상 구원 단계",
            options=_SALVATION_STAGE_OPTIONS,
            format_func=lambda x: _STAGE_LABELS.get(x, x),
            key="up_salvation_stage",
            help="이 자료가 어떤 구원 단계의 사람에게 적합한지 선택 (복수 가능)",
        )

        _DARAKBANG_TIER_OPTIONS = {
            "": "일반 자료 (없음)",
            "darakbang_general": "다락방 일반",
            "darakbang_deep": "다락방 심화",
            "darakbang_leader": "다락방 인도자/사역자",
        }
        darakbang_tier_label = st.selectbox(
            "다락방 자료 등급",
            options=list(_DARAKBANG_TIER_OPTIONS.keys()),
            format_func=lambda x: _DARAKBANG_TIER_OPTIONS[x],
            key="up_darakbang_tier",
            help="다락방 멤버에게만 가중치 적용. 일반 자료면 '없음' 선택.",
        )

        salvation_focus_score = st.slider(
            "구원 집중도 (0.0 ~ 1.0)",
            min_value=0.0, max_value=1.0, step=0.05, value=0.0,
            key="up_salvation_focus",
            help="1.0 = 요한복음 3:16, 로마서 길 같은 직접 구원 자료. 0.0 = 일반 묵상.",
        )

        gospel_core_tag = st.checkbox(
            "⭐ 구원 핵심 자료로 표시 (gospel_core_tag)",
            key="up_gospel_core",
            value=False,
            help="체크 시 seeker/uncertain 사용자에게 fallback으로 최우선 노출됩니다.",
        )

st.markdown("---")

can_submit = bool(file and title)
if not can_submit:
    st.caption("⬆ **파일**과 **제목**을 모두 입력하면 올릴 수 있어요.")

if st.button("📤 업로드", type="primary", disabled=not can_submit, key="up_submit", use_container_width=True, help="파일+메타데이터 분석 → Draft 생성. 검색 노출은 Library에서 Publish 후"):
    with st.spinner("자료를 분석하는 중..."):
        _stages_csv = ",".join(st.session_state.get("up_salvation_stage") or [])
        _tier = st.session_state.get("up_darakbang_tier") or ""
        _focus = st.session_state.get("up_salvation_focus", 0.0)
        _gospel_core = st.session_state.get("up_gospel_core", False)
        result = upload_document(
            file.name, file.getvalue(),
            title=title, doc_type=doc_type,
            series=series if 'series' in locals() else "",
            speaker=speaker if 'speaker' in locals() else "",
            topic_tags=tags if 'tags' in locals() else "",
            scripture_refs=refs if 'refs' in locals() else "",
            summary=summary if 'summary' in locals() else "",
            target_salvation_stage=_stages_csv,
            darakbang_tier=_tier,
            salvation_focus_score=_focus,
            gospel_core_tag="true" if _gospel_core else "false",
        )
    if result:
        st.session_state.last_upload = result
        st.rerun()
