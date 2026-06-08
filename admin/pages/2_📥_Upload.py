"""Upload - 자료 등록 (직접 입력 / inbox 폴더 / 파일 업로드)."""
from __future__ import annotations

import sys, json, time
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
    ingest_text_async, list_inbox, ingest_inbox_async,
    upload_document_async, get_job, check_backend_health, API_BASE,
    publish_version_async, patch_meta, patch_doc_meta, patch_body, get_document,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.set_page_config(page_title="자료 등록", page_icon="📥", layout="wide")
st.title("📥 자료 등록")

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


# ═══════════════════════════════════════════════════════════════
# 헬퍼: 폴링 진행 상황 표시 (세 가지 방식 공통)
# ═══════════════════════════════════════════════════════════════
def _show_progress_and_poll(job_id: str, is_inbox: bool = False):
    """세션에 job_id 있으면 진행바 표시 → 완료 시 결과 저장 후 rerun."""
    if "upload_poll_start" not in st.session_state:
        st.session_state.upload_poll_start = time.time()
    _poll_sec = int(time.time() - st.session_state.get("upload_poll_start", time.time()))

    job = get_job(job_id)

    # ── 오류 ──────────────────────────────────────────────────────
    if job.get("__error__") or job.get("__not_found__"):
        _err_type = job.get("error_type", "unknown")
        _err_msg  = job.get("message", "알 수 없는 오류")

        if _err_type == "timeout":
            st.error("⏱ 서버가 응답하지 않아요 — 터미널에서 재시작해주세요")
            st.code("uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload", language="bash")
        elif _err_type == "connection":
            st.error(f"🔌 서버 연결 불가 — `{API_BASE}` 실행 중인지 확인")
        else:
            st.error(f"❌ {_err_msg}")

        with st.expander("🔍 상세 진단"):
            st.markdown(f"- URL: `{API_BASE}`  |  오류: `{_err_type}`  |  폴링 경과: `{_poll_sec}초`")
            st.code(_err_msg)
            if st.button("🏥 서버 상태 확인", key="hc_btn"):
                h = check_backend_health()
                st.success(f"✅ {h['latency_ms']}ms") if h["ok"] else st.error(h.get("message"))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("↩ 처음으로", key="poll_reset", type="primary"):
                st.session_state.upload_job_id = None
                st.session_state.pop("upload_poll_start", None)
                st.rerun()
        with col2:
            if st.button("🔄 다시 조회", key="poll_retry"):
                st.rerun()
        return True   # 처리됨

    # ── 실패 ──────────────────────────────────────────────────────
    if job.get("status") == "failed":
        err = (job.get("error_json") or {}).get("error", "알 수 없는 오류")
        st.error(f"❌ 처리 실패: {err}")
        with st.expander("📋 오류 상세"):
            st.code((job.get("error_json") or {}).get("traceback", "없음"), language="python")
        if st.button("다시 시도", key="fail_retry"):
            st.session_state.upload_job_id = None
            st.session_state.pop("upload_poll_start", None)
            st.rerun()
        return True

    # ── 완료 ──────────────────────────────────────────────────────
    if job.get("status") == "done":
        result = job.get("result_json") or {}
        if is_inbox:
            st.session_state.inbox_result = result
        else:
            # ▶ 자동 공개: doc_id + version_id 있으면 즉시 publish 요청
            _doc_id = result.get("doc_id") or result.get("id")
            _ver_id = result.get("version_id")
            if _doc_id and _ver_id and result.get("state") != "published":
                _pub = publish_version_async(_doc_id, _ver_id)
                if _pub and _pub.get("job_id"):
                    result["_auto_publish_job"] = _pub["job_id"]
                result["state"] = "published"  # 낙관적 UI 업데이트
            st.session_state.last_upload = result
        st.session_state.upload_job_id = None
        st.session_state.pop("upload_poll_start", None)
        st.rerun()
        return True

    # ── 진행 중 ────────────────────────────────────────────────────
    pct   = job.get("progress_pct", 0)
    stage = job.get("current_stage") or "처리 중..."
    detail= job.get("stage_detail") or ""

    _STUCK_SEC = 5 * 60
    if job.get("status") == "running" and _poll_sec > _STUCK_SEC:
        st.warning(f"⚠️ {_poll_sec//60}분 이상 진행 중 — 서버가 멈췄을 수 있어요")
        if st.button("↩ 취소", key="poll_stuck_cancel"):
            st.session_state.upload_job_id = None
            st.session_state.pop("upload_poll_start", None)
            st.rerun()

    st.markdown(f"### ⏳ 처리 중... (`{_poll_sec}초` 경과)")
    st.progress(pct / 100, text=f"{pct}%  |  {stage}")
    if detail:
        st.caption(detail)
    time.sleep(2)
    st.rerun()
    return True


# ═══════════════════════════════════════════════════════════════
# 폴링 중이면 진행 화면 표시 후 stop
# ═══════════════════════════════════════════════════════════════
_job_id = st.session_state.get("upload_job_id")
if _job_id:
    is_inbox = st.session_state.get("upload_is_inbox", False)
    _show_progress_and_poll(_job_id, is_inbox=is_inbox)
    st.stop()


# ═══════════════════════════════════════════════════════════════
# 완료 결과 표시 + 인라인 편집 패널
# ═══════════════════════════════════════════════════════════════
if st.session_state.get("last_upload"):
    r = st.session_state.last_upload
    _doc_id = r.get("doc_id") or r.get("id")
    _ver_id = r.get("version_id")
    _q      = r.get("extraction_quality_score", 0)

    # ── 상태 배너 ─────────────────────────────────────────────
    st.success(f"✅ 등록 + 즉시 공개 완료: **{r.get('title')}**  (v{r.get('version_number')})")
    st.caption(f"📊 추출 품질 {_q}/100  |  🔓 검색 공개 상태  |  🔖 용어 자동 추출 완료")

    # ── 중복 경고 ─────────────────────────────────────────────
    for h in (r.get("dup_hits") or []):
        _kind = {"identical": "⚠ 완전 동일", "version": "💡 새 버전 후보", "similar": "🔍 유사"}.get(h.get("kind",""), h.get("kind",""))
        st.warning(f"**{_kind}** — *{h.get('title','?')}*  {h.get('reason','')}")

    # ── body 로딩: body_patch 없으면 API 재조회 (1회만) ──────
    if "_body_loaded" not in st.session_state and _doc_id and _ver_id:
        _raw_body = r.get("body_patch") or ""
        if not _raw_body.strip() and _doc_id:
            with st.spinner("📄 본문 불러오는 중..."):
                _full = get_document(_doc_id) or {}
                _versions = _full.get("versions") or []
                _match = next((v for v in _versions if v.get("version_id") == _ver_id), None)
                if _match:
                    _raw_body = _match.get("body_patch") or _match.get("extracted_text_preview") or ""
                    # document 레벨 필드도 보완
                    r.setdefault("speaker", _full.get("speaker", ""))
                    r.setdefault("series",  _full.get("series",  ""))
        st.session_state.last_upload["body_patch"] = _raw_body
        st.session_state._body_loaded = True
        st.rerun()

    # ── 인라인 편집 패널 ──────────────────────────────────────
    st.markdown("#### ✏️ 내용 수정")
    st.caption("수정 후 **💾 저장** 을 누르면 즉시 반영됩니다.")

    # list → comma string 변환 (topic_tags, scripture_refs)
    _tags_init = r.get("topic_tags", [])
    _refs_init = r.get("scripture_refs", [])
    _tags_str  = ", ".join(_tags_init) if isinstance(_tags_init, list) else (_tags_init or "")
    _refs_str  = ", ".join(_refs_init) if isinstance(_refs_init, list) else (_refs_init or "")

    with st.container(border=True):
        _c1, _c2 = st.columns([2, 1])
        with _c1:
            _e_title = st.text_input("제목", value=r.get("title", ""), key="edit_title")
        with _c2:
            _e_speaker = st.text_input("저자 / 화자", value=r.get("speaker", ""), key="edit_speaker")

        _c3, _c4 = st.columns([2, 1])
        with _c3:
            _e_tags = st.text_input("주제 태그 (쉼표 구분)", value=_tags_str, key="edit_tags")
        with _c4:
            _e_refs = st.text_input("본문 구절", value=_refs_str, key="edit_refs")

        _e_summary = st.text_area("요약", value=r.get("summary", "") or "", height=80, key="edit_summary")
        _e_body    = st.text_area(
            "본문 내용",
            value=st.session_state.last_upload.get("body_patch", "") or "",
            height=400,
            key="edit_body",
        )

        _sc, _cc = st.columns([3, 1])
        with _sc:
            if st.button("💾 저장", type="primary", use_container_width=True, key="edit_save"):
                _errors = []
                # ① version 레벨 — 제목·요약·태그·구절
                if _doc_id and _ver_id:
                    _ok_meta = patch_meta(_doc_id, _ver_id, {
                        "title":          _e_title,
                        "summary":        _e_summary,
                        "topic_tags":     [t.strip() for t in _e_tags.split(",") if t.strip()],
                        "scripture_refs": [s.strip() for s in _e_refs.split(",") if s.strip()],
                    })
                    if not _ok_meta:
                        _errors.append("메타 저장 실패")

                    # ② 본문
                    if _e_body.strip():
                        _ok_body = patch_body(_doc_id, _ver_id, _e_body)
                        if not _ok_body:
                            _errors.append("본문 저장 실패")

                    # ③ document 레벨 — speaker
                    if _e_speaker.strip() != (r.get("speaker") or ""):
                        _ok_doc = patch_doc_meta(_doc_id, {"speaker": _e_speaker})
                        if not _ok_doc:
                            _errors.append("저자 저장 실패")

                if _errors:
                    st.error("❌ " + " / ".join(_errors))
                else:
                    st.session_state.last_upload.update({
                        "title":         _e_title,
                        "speaker":       _e_speaker,
                        "topic_tags":    [t.strip() for t in _e_tags.split(",") if t.strip()],
                        "scripture_refs":[s.strip() for s in _e_refs.split(",") if s.strip()],
                        "summary":       _e_summary,
                        "body_patch":    _e_body,
                    })
                    st.success("✅ 저장 완료")
                    st.rerun()
        with _cc:
            if st.button("✖ 닫기", use_container_width=True, key="close_result"):
                st.session_state.last_upload = None
                st.session_state.pop("_body_loaded", None)
                st.rerun()

    st.divider()


# ═══════════════════════════════════════════════════════════════
# 완료 결과 표시 (inbox 일괄)
# ═══════════════════════════════════════════════════════════════
if st.session_state.get("inbox_result"):
    r = st.session_state.inbox_result
    sc = r.get("success_count", 0)
    total = r.get("total", 0)
    st.success(f"✅ inbox 처리 완료 — {sc}/{total}개 성공")
    for d in (r.get("done") or []):
        st.markdown(f"- ✅ **{d.get('title') or d.get('file')}**")
    for e in (r.get("errors") or []):
        st.markdown(f"- ❌ `{e.get('file')}` — {e.get('error')}")
    st.info("📚 **Library** 에서 검토 후 공개하세요.")
    if st.button("✖ 닫기", key="close_inbox_result"):
        st.session_state.inbox_result = None
        st.rerun()
    st.divider()


# ═══════════════════════════════════════════════════════════════
# 탭 2개 (inbox 제거 — 직접입력 / 파일업로드)
# ═══════════════════════════════════════════════════════════════
tab_text, tab_file = st.tabs(["📝 직접 입력", "⬆ 파일 업로드"])

# ───────────────────────────────────────────────────────────────
# TAB 1: 직접 입력
# ───────────────────────────────────────────────────────────────
with tab_text:
    st.caption("텍스트나 마크다운을 바로 붙여넣어 등록해요. 등록 즉시 검색에 공개됩니다.")

    col1, col2 = st.columns([1, 1])
    with col1:
        txt_title = st.text_input("제목 *", key="txt_title", placeholder="예: 롬5장 — 화평을 누리자")
        txt_type_label = st.selectbox("자료 종류 *", DOC_TYPE_OPTIONS, key="txt_type")
        txt_type = DOC_TYPE_REV[txt_type_label]
    with col2:
        with st.expander("➕ 추가 정보 (선택)"):
            txt_series  = st.text_input("시리즈명", key="txt_series")
            txt_speaker = st.text_input("저자 / 화자", key="txt_speaker")
            txt_tags    = st.text_input("주제 태그 (쉼표 구분)", key="txt_tags")
            txt_refs    = st.text_input("본문 구절", key="txt_refs")
            txt_summary = st.text_area("요약", height=68, key="txt_summary")

    txt_content = st.text_area(
        "본문 내용 *",
        height=300,
        key="txt_content",
        placeholder=(
            "여기에 설교 / 자료 내용을 붙여넣거나 직접 입력하세요.\n\n"
            "마크다운 형식 지원:\n"
            "# 제목\n## 소제목\n**굵게** *기울임*\n\n"
            "일반 텍스트도 됩니다."
        ),
    )

    _can_txt = bool(txt_title and txt_content and txt_content.strip())
    if not _can_txt:
        st.caption("⬆ **제목**과 **본문 내용**을 입력하면 등록할 수 있어요.")

    if st.button("📤 등록 + 즉시 공개", type="primary", disabled=not _can_txt,
                 key="txt_submit", use_container_width=True):
        resp = ingest_text_async(
            title=txt_title, content=txt_content, doc_type=txt_type,
            series=txt_series or "", speaker=txt_speaker or "",
            topic_tags=txt_tags or "", scripture_refs=txt_refs or "",
            summary=txt_summary or "",
        )
        if resp and resp.get("job_id"):
            st.session_state.upload_job_id = resp["job_id"]
            st.session_state.upload_is_inbox = False
            st.rerun()
        else:
            st.error("❌ 서버 연결에 실패했어요. API 서버가 실행 중인지 확인하세요.")

# ───────────────────────────────────────────────────────────────
# TAB 2: 파일 업로드
# ───────────────────────────────────────────────────────────────
with tab_file:
    st.caption("PDF · DOCX · TXT · MD 파일을 직접 업로드해요. (데드락 수정 완료)")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### 파일")
        file = st.file_uploader(
            "PDF · DOCX · TXT · MD",
            accept_multiple_files=False,
            key="up_file",
        )
        if file:
            st.success(f"✅ {file.name}  ·  {file.size:,} bytes")

    with col2:
        st.markdown("#### 기본 정보")
        title = st.text_input("제목 *", key="up_title", placeholder="예: 롬5장 — 화평을 누리자")
        doc_type_label = st.selectbox("자료 종류 *", DOC_TYPE_OPTIONS, key="up_type_label")
        doc_type = DOC_TYPE_REV[doc_type_label]

        with st.expander("➕ 추가 정보 (선택)"):
            series  = st.text_input("시리즈명", key="up_series")
            speaker = st.text_input("저자 / 화자", key="up_speaker")
            tags    = st.text_input("주제 태그", key="up_tags", placeholder="쉼표로 구분")
            refs    = st.text_input("본문 구절", key="up_refs")
            summary = st.text_area("요약", height=68, key="up_summary")

    st.markdown("---")
    can_submit = bool(file and title)
    if not can_submit:
        st.caption("⬆ 파일과 제목을 모두 입력하면 올릴 수 있어요.")

    if st.button("📤 업로드", type="primary", disabled=not can_submit,
                 key="up_submit", use_container_width=True):
        resp = upload_document_async(
            file.name, file.getvalue(),
            title=title, doc_type=doc_type,
            series=series if "series" in locals() else "",
            speaker=speaker if "speaker" in locals() else "",
            topic_tags=tags if "tags" in locals() else "",
            scripture_refs=refs if "refs" in locals() else "",
            summary=summary if "summary" in locals() else "",
        )
        if resp and resp.get("job_id"):
            st.session_state.upload_job_id = resp["job_id"]
            st.session_state.upload_is_inbox = False
            st.session_state.pop("upload_poll_start", None)
            st.rerun()
        else:
            st.error("❌ 업로드 요청 실패")
            with st.expander("🔍 서버 상태 확인", expanded=True):
                h = check_backend_health()
                if h["ok"]:
                    st.success(f"✅ 서버 정상 ({h['latency_ms']}ms) — upload API만 실패")
                else:
                    htype = h.get("error_type", "")
                    st.error(h.get("message", ""))
                    if htype in ("timeout", "connection"):
                        st.code(
                            "uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload",
                            language="bash",
                        )
