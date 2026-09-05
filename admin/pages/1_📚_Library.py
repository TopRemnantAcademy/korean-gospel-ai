"""Library - 자료실 (문서/버전 관리)."""
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

import time
from admin.lib.api_client import (
    list_documents, get_document, patch_meta, patch_body,
    validate_version, publish_version, publish_version_async, get_job,
    archive_document, get_audit, bulk_action,
)
from admin.lib.auth import gate

gate(os.getenv("APP_PASSWORD", ""))

st.title("📚 자료실")
st.caption("올린 자료를 검토하고 검색에 공개합니다.")

STATE_KR = {
    "draft": "🟡 임시 (Draft)",
    "validated": "🟠 검증완료",
    "published": "🟢 공개됨",
    "superseded": "⚪ 옛 버전",
    "archived": "🗄 보관됨",
}

TYPE_KR = {
    "sermon": "설교", "book": "책", "bible": "성경",
    "testimony": "간증", "prayer": "기도문",
    "healing": "치유자료", "other": "기타",
}


def _render_doc_detail(doc_id: str, key_suffix: str = ""):
    doc = get_document(doc_id)
    if not doc:
        st.error("자료를 불러올 수 없습니다.")
        return

    st.divider()
    st.subheader(f"📄 {doc['doc_key']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("종류", TYPE_KR.get(doc.get("doc_type", ""), doc.get("doc_type", "-")))
    c2.metric("시리즈", doc.get("series") or "-")
    c3.metric("저자/화자", doc.get("speaker") or "-")
    c4.metric("대표문서", "Yes" if doc.get("is_canonical") else "No")

    versions = doc.get("versions", [])
    if not versions:
        st.warning("버전이 없습니다.")
        return

    labels = [f"v{v['version_number']} · {STATE_KR.get(v['state'], v['state'])}" for v in versions]
    chosen = st.radio("버전 선택", labels, horizontal=True, key=f"verpick_{doc_id}_{key_suffix}")
    v = versions[labels.index(chosen)]

    sub = st.tabs(["📝 정보 수정", "📄 본문", "✅ 검증/공개", "🕒 이력"])

    # ----- 정보 -----
    with sub[0]:
        is_draft = v["state"] == "draft"
        if not is_draft:
            st.info(f"이 버전은 `{STATE_KR.get(v['state'], v['state'])}` 상태로 수정할 수 없습니다.")
        new_title = st.text_input("제목", value=v["title"], key=f"title_{v['version_id']}", disabled=not is_draft)
        new_summary = st.text_area("요약", value=v.get("summary") or "", height=100,
                                    key=f"summary_{v['version_id']}", disabled=not is_draft)
        tags_csv = ",".join(v.get("topic_tags") or [])
        new_tags = st.text_input("주제 태그 (쉼표)", value=tags_csv,
                                  key=f"tags_{v['version_id']}", disabled=not is_draft)
        refs_csv = ",".join(v.get("scripture_refs") or [])
        new_refs = st.text_input("본문 구절 (쉼표)", value=refs_csv,
                                  key=f"refs_{v['version_id']}", disabled=not is_draft)
        if is_draft and st.button("💾 저장", key=f"savemeta_{v['version_id']}", type="primary"):
            r = patch_meta(doc_id, v["version_id"], {
                "title": new_title, "summary": new_summary,
                "topic_tags": [t.strip() for t in new_tags.split(",") if t.strip()],
                "scripture_refs": [r.strip() for r in new_refs.split(",") if r.strip()],
            })
            if r:
                st.success("저장 완료")
                st.rerun()

    # ----- 본문 -----
    with sub[1]:
        q = v.get("extraction_quality_score", 0)
        q_label = "좋음 ✅" if q >= 80 else ("보통" if q >= 50 else "낮음 ⚠")
        st.caption(f"추출 품질: **{q}/100** ({q_label}) · 길이 미리보기: {len(v['extracted_text_preview'])}자")
        if v.get("extraction_warnings"):
            with st.expander(f"⚠ 추출 경고 ({len(v['extraction_warnings'])}개)"):
                st.json(v["extraction_warnings"])

        if v["state"] == "draft":
            st.caption("💡 작은 수정만 여기서. 큰 수정은 외부 편집 후 다시 업로드(=새 버전).")
            current = v.get("body_patch") or v["extracted_text_preview"]
            edited = st.text_area("본문 (마이크로 패치)", value=current, height=400,
                                   key=f"body_{v['version_id']}")
            if st.button("💾 본문 저장", key=f"savebody_{v['version_id']}", help="마이크로 패치만. 큰 수정은 외부 편집 후 재업로드(=새 버전)"):
                r = patch_body(doc_id, v["version_id"], edited)
                if r:
                    st.success("저장됨")
        else:
            st.text_area("본문 (읽기 전용)", value=v.get("body_patch") or v["extracted_text_preview"],
                          height=400, disabled=True, key=f"body_ro_{v['version_id']}")

    # ----- 검증/공개 -----
    with sub[2]:
        cl = v.get("checklist") or {}
        st.markdown("**공개 전 체크리스트** — 4개 모두 확인 후 공개")

        if v["state"] == "draft":
            ch1 = st.checkbox("✔ 신학적으로 검토했습니다", value=cl.get("theology_ok", False), key=f"ch_th_{v['version_id']}")
            ch2 = st.checkbox("✔ 출처를 명시했습니다", value=cl.get("source_cited", False), key=f"ch_src_{v['version_id']}")
            ch3 = st.checkbox("✔ 인용한 성경 구절이 정확합니다", value=cl.get("scripture_verified", False), key=f"ch_sc_{v['version_id']}")
            ch4 = st.checkbox("✔ 어조/표현을 검토했습니다", value=cl.get("tone_ok", False), key=f"ch_tn_{v['version_id']}")

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("💾 체크리스트 저장", key=f"save_cl_{v['version_id']}", help="신학·출처·구절·톤 체크 상태 저장"):
                    patch_meta(doc_id, v["version_id"], {"checklist": {
                        "theology_ok": ch1, "source_cited": ch2,
                        "scripture_verified": ch3, "tone_ok": ch4,
                    }})
                    st.rerun()
            with bc2:
                if st.button("🔬 검증 실행", key=f"validate_{v['version_id']}", help="체크리스트 4개 + 기본 검증. 통과해야 공개 가능"):
                    r = validate_version(doc_id, v["version_id"])
                    if r:
                        if r["passed"]:
                            st.success("✅ 검증 통과! 아래 '검색에 공개하기'를 누르세요.")
                        else:
                            st.error("❌ 검증 실패")
                            st.json(r["report"])

            st.divider()
            st.markdown("##### 🟢 검색에 공개하기")
            st.caption("공개하면 🔎 Search 페이지의 답변에 이 자료가 인용될 수 있습니다.")

            # ── 공개 진행 상태 폴링 ──────────────────────────────────────────
            _pub_job_key = f"publish_job_{v['version_id']}"
            _pub_job_id = st.session_state.get(_pub_job_key)

            if _pub_job_id:
                pub_job = get_job(_pub_job_id)
                if pub_job.get("__error__") or pub_job.get("__not_found__"):
                    _etype = pub_job.get("error_type", "unknown")
                    _emsg  = pub_job.get("message", "연결 실패")
                    if _etype == "timeout":
                        st.error("⏱ 서버 응답 없음 — 터미널에서 재시작 후 다시 시도하세요")
                    elif _etype == "connection":
                        st.error("🔌 서버 연결 불가 — API 서버가 실행 중인지 확인하세요")
                    else:
                        st.error(f"❌ 작업 정보 조회 실패: {_emsg}")
                    if st.button("다시 조회", key=f"pub_retry_conn_{v['version_id']}"):
                        st.rerun()
                    st.session_state[_pub_job_key] = None
                elif pub_job.get("status") == "failed":
                    err_msg = (pub_job.get("error_json") or {}).get("error", "알 수 없는 오류")
                    st.error(f"❌ 공개 실패: {err_msg}")
                    with st.expander("📋 오류 상세"):
                        st.code((pub_job.get("error_json") or {}).get("traceback", "없음"), language="python")
                    if st.button("다시 시도", key=f"pub_retry_{v['version_id']}"):
                        st.session_state[_pub_job_key] = None
                        st.rerun()
                elif pub_job["status"] == "done":
                    pub_r = pub_job.get("result_json") or {}
                    st.success(f"✅ 공개 완료! {pub_r.get('chunks', '?')}개 청크가 검색에 등록되었습니다.")
                    st.session_state[_pub_job_key] = None
                    st.balloons()
                    st.rerun()
                else:
                    # running / pending
                    pct = pub_job.get("progress_pct", 0)
                    stage = pub_job.get("current_stage") or "처리 중..."
                    detail = pub_job.get("stage_detail") or ""
                    st.progress(pct / 100, text=f"⏳ {stage}  {pct}%")
                    if detail:
                        st.caption(detail)
                    _pub_stages = [
                        ("📝 청킹", 10), ("🧮 임베딩", 80),
                        ("🗂 인덱싱", 90), ("💾 저장", 95), ("✅ 완료", 100),
                    ]
                    _pcols = st.columns(len(_pub_stages))
                    for i, (sl, sp) in enumerate(_pub_stages):
                        with _pcols[i]:
                            if pct >= sp:
                                st.success(f"✅ {sl}")
                            elif pct >= sp - 15:
                                st.warning(f"⏳ {sl}")
                            else:
                                st.caption(f"⬜ {sl}")
                    time.sleep(2)
                    st.rerun()
            else:
                if st.button("🟢 검색에 공개하기", type="primary", key=f"publish_{v['version_id']}"):
                    resp = publish_version_async(doc_id, v["version_id"])
                    if resp and resp.get("job_id"):
                        st.session_state[_pub_job_key] = resp["job_id"]
                        st.rerun()
                    else:
                        st.error("공개 시작에 실패했습니다. API 서버가 실행 중인지 확인하세요.")
        else:
            for k, ok in (cl or {}).items():
                label = {
                    "theology_ok": "신학 검토",
                    "source_cited": "출처 명시",
                    "scripture_verified": "본문구절 검증",
                    "tone_ok": "톤 검토",
                }.get(k, k)
                st.markdown(f"- {label}: {'✅' if ok else '❌'}")
            if v.get("validation_report"):
                with st.expander("검증 리포트"):
                    st.json(v["validation_report"])
            if v["state"] == "published":
                st.success(f"🟢 검색 공개 중 (공개 시각: {v.get('published_at', '-')})")

        st.divider()
        st.markdown("##### 🗄 자료 관리")
        _confirm = st.checkbox("정말 아카이브하시겠습니까? (검색에서 숨겨지나 데이터는 보존됩니다)", key=f"archconf_{doc_id}_{v['version_id']}")
        if st.button("🗄 이 자료 아카이브 (검색에서 숨김)", key=f"arch_{doc_id}_{v['version_id']}", help="검색에서 제외. 데이터는 보존됨", disabled=not _confirm, type="primary"):
            archive_document(doc_id)
            st.success("아카이브됨")
            st.rerun()

    # ----- 이력 -----
    with sub[3]:
        logs = get_audit(doc_id) or []
        if not logs:
            st.caption("아직 이력이 없습니다.")
        else:
            for log in logs:
                when = (log["when"] or "")[:19].replace("T", " ")
                line = f"`{when}` · **{log['action']}** · {log['who']}"
                if log.get("from_state") or log.get("to_state"):
                    line += f"  ({log.get('from_state') or '-'} → {log.get('to_state') or '-'})"
                st.markdown(line)


# ========== 본문 ==========
all_docs = list_documents() or []

if not all_docs:
    st.info(
        "📭 **자료실이 비어있습니다.**\n\n"
        "왼쪽 사이드바에서 **📥 Upload** 페이지로 가서 첫 자료를 올려보세요."
    )
    st.stop()

# 탭 (한국어)
tab_all, tab_draft, tab_pub, tab_arch = st.tabs([
    f"전체 ({len(all_docs)})",
    f"🟡 임시 ({sum(1 for d in all_docs if d.get('latest_state') == 'draft')})",
    f"🟢 공개됨 ({sum(1 for d in all_docs if (d.get('published_version') or 0) > 0)})",
    "🗄 보관됨",
])

for tab, st_filter in zip([tab_all, tab_draft, tab_pub, tab_arch],
                            [None, "draft", "published", "archived"]):
    with tab:
        docs = list_documents(state=st_filter) or []
        if not docs:
            if st_filter == "draft":
                st.info("임시 상태인 자료가 없습니다. 모두 공개됐거나 아직 올린 게 없어요.")
            elif st_filter == "published":
                st.info("아직 공개된 자료가 없습니다. 임시 자료를 열어 '검색에 공개하기'를 누르세요.")
            elif st_filter == "archived":
                st.info("보관된 자료가 없습니다.")
            else:
                st.info("자료가 없습니다.")
            continue

        df = pd.DataFrame(docs)
        # 친근한 컬럼명
        if 'doc_type' in df.columns:
            df['종류'] = df['doc_type'].map(lambda x: TYPE_KR.get(x, x))
        if 'latest_state' in df.columns:
            df['상태'] = df['latest_state'].map(lambda x: STATE_KR.get(x, x))

        show_cols = []
        for c in ['title', '종류', 'series', 'latest_version', '상태', 'published_version', 'updated_at']:
            if c in df.columns:
                show_cols.append(c)
        st.dataframe(
            df[show_cols].rename(columns={
                'title': '제목', 'series': '시리즈',
                'latest_version': '최신 v', 'published_version': '공개 v',
                'updated_at': '수정 시각',
            }),
            use_container_width=True, height=300,
        )

        # === Bulk action ===
        with st.expander(f"⚡ 일괄 작업 ({len(docs)}개 자료 대상)"):
            opts = {f"{d['title']} ({STATE_KR.get(d['latest_state'], d['latest_state'])})": d['doc_id']
                    for d in docs}
            picked = st.multiselect("자료 선택", list(opts.keys()),
                                      key=f"bulk_pick_{st_filter or 'all'}")
            colA, colB = st.columns(2)
            with colA:
                if st.button("🟢 선택 자료 일괄 공개", key=f"bulk_pub_{st_filter or 'all'}",
                              disabled=not picked, help="선택한 자료를 한 번에 공개"):
                    ids = [opts[k] for k in picked]
                    with st.spinner(f"{len(ids)}개 자료 공개 처리 중..."):
                        r = bulk_action(ids, "publish")
                    if r:
                        st.success(f"성공 {r['ok_count']}/{len(ids)}")
                        with st.container(border=True):
                            st.caption("상세")
                            st.json(r["results"])
                        st.rerun()
            with colB:
                if st.button("🗄 선택 자료 일괄 아카이브", key=f"bulk_arch_{st_filter or 'all'}",
                              disabled=not picked, help="선택한 자료를 한 번에 검색에서 숨김"):
                    ids = [opts[k] for k in picked]
                    r = bulk_action(ids, "archive")
                    if r:
                        st.success(f"아카이브 {r['ok_count']}/{len(ids)}")
                        st.rerun()

        choices = {f"{d['title']}  ·  v{d['latest_version']}  ·  {STATE_KR.get(d['latest_state'], d['latest_state'])}": d["doc_id"] for d in docs}
        label = st.selectbox(
            "자료 선택 → 아래에 상세보기",
            [""] + list(choices.keys()),
            key=f"sel_{st_filter or 'all'}",
        )
        if label:
            _render_doc_detail(choices[label], key_suffix=str(st_filter or "all"))
