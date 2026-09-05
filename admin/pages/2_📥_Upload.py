"""Upload - 자료 등록 (직접 입력 / 파일 업로드)."""
from __future__ import annotations

import sys, time
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
    ingest_text_async, upload_document_async, ingest_clean_chunks,
    get_job, check_backend_health, API_BASE,
    publish_version_async, patch_meta, patch_doc_meta, patch_body, get_document,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

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
def _show_progress_and_poll(job_id: str):
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
    _show_progress_and_poll(_job_id)
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
    st.caption(f"📊 추출 품질 {_q}/100  |  🔓 검색 공개 상태")

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
# 기본 경로 안내 + 탭: [①] 정제 데이터 직행(Fast-Track, 기본) / [②] 보조 도구
# ═══════════════════════════════════════════════════════════════
st.markdown("### 🚀 기본 경로: 정제 청크 파일 바로 업로드")
st.info(
    "외부에서 한국어(원문)·중국어(번역)를 1:1로 **이미 정제·번역해 둔 청크 파일**을 올리면, "
    "LLM 번역·청킹 과정을 건너뛰고 **몇 초 만에** 검색 가능해집니다. "
    "평소 자료 등록은 아래 **① 정제 데이터 업로드** 탭만 사용하세요."
)

tab_fast, tab_aux = st.tabs([
    "① 정제 데이터 업로드 (Fast-Track · 기본)",
    "② 보조 도구 (원시 파일 · 직접 입력)",
])


def _preview_clean_chunks(raw: bytes, filename: str):
    """업로드 파일을 client-side 파싱해 미리보기 행 + 검수 요약 반환."""
    import json as _json
    try:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None, 0, 0, "빈 파일입니다"
        try:
            obj = _json.loads(text)
            docs = obj.get("documents", [obj]) if isinstance(obj, dict) else obj
        except _json.JSONDecodeError:
            docs = []
            for line in text.splitlines():
                line = line.strip()
                if line:
                    docs.append(_json.loads(line))
        rows, missing_zh = [], 0
        for d in docs:
            if not isinstance(d, dict):
                continue
            chunks = d.get("chunks")
            if chunks is None and ("korean_text" in d or "chinese_text" in d):
                chunks = [d]
            if not chunks:
                continue
            for i, ch in enumerate(chunks):
                ci = ch.get("chunk_index", i)
                ko = (ch.get("korean_text") or "").strip()
                zh = (ch.get("chinese_text") or "").strip()
                if not zh:
                    missing_zh += 1
                rows.append({
                    "#": ci,
                    "한국어 (원문)": (ko[:140] + "…") if len(ko) > 140 else ko,
                    "중국어 (번역)": (zh[:140] + "…") if len(zh) > 140 else zh,
                })
        return rows, len(docs), missing_zh, None
    except Exception as e:
        return None, 0, 0, f"파싱 실패: {e}"


# ───────────────────────────────────────────────────────────────
# TAB ①: 정제 데이터 직행 (Fast-Track) — 기본 경로
# ───────────────────────────────────────────────────────────────
with tab_fast:
    st.markdown("#### 📋 업로드 순서")
    st.markdown(
        "1. **파일 준비** — `.json` / `.jsonl` 로, 청크마다 `korean_text`(원문)·`chinese_text`(번역)를 1:1 매핑\n"
        "2. **형식 확인** — 아래 ▶ 샘플 형식 보기 로 예시 확인\n"
        "3. **업로드** — 파일 선택 → 미리보기 검수 → 🚀 바로 적재"
    )
    st.caption("지원 형식: `.json` / `.jsonl` — 청크 단위로 한국어·중국어가 1:1 매핑된 파일")

    with st.expander("▶ 샘플 형식 보기", expanded=False):
        st.code(
            '{\n'
            '  "doc_id": "20260201_전도자의낮",\n'
            '  "title": "전도자의 낮",\n'
            '  "chunks": [\n'
            '    {\n'
            '      "chunk_index": 0,\n'
            '      "korean_text": "그러므로 우리가 믿음으로...",\n'
            '      "chinese_text": "我们既因信称义",\n'
            '      "topic_tags": ["칭의", "믿음"],\n'
            '      "scripture_refs": ["롬 5:1"],\n'
            '      "summary": "믿음으로 얻은 의로움"\n'
            '    }\n'
            '  ]\n'
            '}',
            language="json",
        )

    fast_file = st.file_uploader(
        "정제 청크 파일 선택 (.json / .jsonl)",
        type=["json", "jsonl"],
        accept_multiple_files=False,
        key="fast_file",
    )

    if fast_file:
        raw = fast_file.getvalue()
        st.success(f"✅ {fast_file.name}  ·  {len(raw):,} bytes")
        rows, n_docs, missing_zh, err = _preview_clean_chunks(raw, fast_file.name)
        if err:
            st.error(f"❌ {err}")
        else:
            if missing_zh:
                st.warning(f"⚠ 중국어 누락 {missing_zh}개 — 해당 청크는 원문(한국어)으로 폴백 적재됩니다.")
            else:
                st.success("✅ 중국어 전체 매핑 확인")
            st.markdown(f"🔎 **검수 미리보기**: 문서 **{n_docs}**개 · 청크 **{len(rows)}**개")
            if rows:
                st.dataframe(rows[:20], use_container_width=True, hide_index=True)
                if len(rows) > 20:
                    st.caption(f"… 외 {len(rows)-20}개 청크 (총 {len(rows)}개)")
            if st.button("🚀 바로 적재 (번역 생략)", type="primary",
                         use_container_width=True, key="fast_submit"):
                with st.spinner("임베딩 계산 + 벡터 DB 적재 중..."):
                    resp = ingest_clean_chunks(fast_file.name, raw)
                if resp and resp.get("status") == "ok":
                    st.success(
                        f"✅ 적재 완료 — 컬렉션 `{resp.get('collection')}` 에 "
                        f"청크 **{resp.get('total_chunks')}**개 적재됨"
                    )
                    st.balloons()
                else:
                    _m = (resp or {}).get("message") or "서버 응답 없음"
                    st.error(f"❌ 적재 실패: {_m}")


# ───────────────────────────────────────────────────────────────
# TAB ②: 보조 도구 (원시 파일 · 직접 입력) — 비중 낮춤
# ───────────────────────────────────────────────────────────────
with tab_aux:
    st.warning(
        "🛟 **보조 경로** — Fast-Track 정제 청크를 쓸 수 없는 비상/특수 상황에서만 사용하세요. "
        "원시 파일은 시스템이 자동으로 청킹·LLM 번역을 돌려 **시간이 오래 걸립니다**.",
        icon="🛟",
    )

    # ── 2-a 원시 파일 업로드 (보조) ──────────────────────────────
    st.markdown("##### 📄 원시 파일 업로드 (보조)")
    st.caption("PDF · DOCX · TXT · MD 파일 → 시스템 자동 청킹·번역")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**파일**")
        file = st.file_uploader(
            "PDF · DOCX · TXT · MD",
            accept_multiple_files=False,
            key="up_file",
        )
        if file:
            st.success(f"✅ {file.name}  ·  {file.size:,} bytes")

    with col2:
        st.markdown("**기본 정보**")
        title = st.text_input("제목 *", key="up_title", placeholder="예: 롬5장 — 화평을 누리자")
        doc_type_label = st.selectbox("자료 종류 *", DOC_TYPE_OPTIONS, key="up_type_label")
        doc_type = DOC_TYPE_REV[doc_type_label]

        with st.expander("➕ 추가 정보 (선택)"):
            series  = st.text_input("시리즈명", key="up_series")
            speaker = st.text_input("저자 / 화자", key="up_speaker")
            tags    = st.text_input("주제 태그", key="up_tags", placeholder="쉼표로 구분")
            refs    = st.text_input("본문 구절", key="up_refs")
            summary = st.text_area("요약", height=68, key="up_summary")

    can_submit = bool(file and title)
    if not can_submit:
        st.caption("⬆ 파일과 제목을 모두 입력하면 올릴 수 있어요.")

    if st.button("📤 원시 파일 업로드", disabled=not can_submit,
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

    st.divider()

    # ── 2-b 직접 입력 (보조) ─────────────────────────────────────
    st.markdown("##### 📝 직접 입력 (보조)")
    st.caption("텍스트/마크다운을 붙여넣어 등록 → 즉시 검색 공개")

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
        height=240,
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

    if st.button("📤 직접 입력 등록", disabled=not _can_txt,
                 key="txt_submit", use_container_width=True):
        resp = ingest_text_async(
            title=txt_title, content=txt_content, doc_type=txt_type,
            series=txt_series or "", speaker=txt_speaker or "",
            topic_tags=txt_tags or "", scripture_refs=txt_refs or "",
            summary=txt_summary or "",
        )
        if resp and resp.get("job_id"):
            st.session_state.upload_job_id = resp["job_id"]
            st.rerun()
        else:
            st.error("❌ 서버 연결에 실패했어요. API 서버가 실행 중인지 확인하세요.")
