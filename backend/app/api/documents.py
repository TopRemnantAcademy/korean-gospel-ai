"""POST /documents/upload, GET /documents, ..., POST /documents/{id}/publish.

핵심 워크플로우 (사용자가 완성본만 업로드):
  1) POST /documents/upload (file + meta) -> creates L1 + L2 draft
  2) GET  /documents (라이브러리 조회)
  3) GET  /documents/{doc_id} (상세)
  4) PATCH /documents/{doc_id}/versions/{ver_id} (메타 수정 - draft만)
  5) PATCH /documents/{doc_id}/versions/{ver_id}/body (마이크로 패치)
  6) POST /documents/{doc_id}/versions/{ver_id}/validate
  7) POST /documents/{doc_id}/versions/{ver_id}/publish
  8) POST /documents/{doc_id}/new-version (재업로드)
  9) DELETE /documents/{doc_id} (archive)
"""
from __future__ import annotations
import asyncio
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..db import get_session
from ..models.orm import DocVersionState
from ..services import (
    audit_service, document_service, publish_service, source_service, dedup_service,
)
from ..services import job_service

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------- Auth ----------
def _check_admin(authorization: Optional[str]):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin token")


# ---------- Schemas ----------
class DraftMetaIn(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    topic_tags: Optional[list[str]] = None
    scripture_refs: Optional[list[str]] = None
    checklist: Optional[dict] = None


class DocMetaIn(BaseModel):
    """document 레벨 메타 (버전 독립) — speaker / series / doc_type."""
    speaker: Optional[str] = None
    series: Optional[str] = None
    doc_type: Optional[str] = None


class BodyPatchIn(BaseModel):
    body: str


class DocumentSummary(BaseModel):
    doc_id: str
    doc_key: str
    doc_type: str
    title: str
    series: Optional[str]
    speaker: Optional[str]
    is_canonical: bool
    latest_version: int
    latest_state: str
    published_version: Optional[int]
    updated_at: str


class VersionDetail(BaseModel):
    version_id: str
    doc_id: str
    version_number: int
    state: str
    title: str
    summary: Optional[str]
    topic_tags: list[str]
    scripture_refs: list[str]
    body_patch: Optional[str]
    jsonl_path: Optional[str] = None
    extracted_text_preview: str
    extraction_quality_score: int
    extraction_warnings: dict
    checklist: dict
    validation_report: dict
    created_at: str
    published_at: Optional[str]
    dup_hits: list[dict] = []


# ---------- helpers (라우트보다 먼저 정의 — inbox 라우트에서 사용) ----------
def _to_version_detail(v) -> VersionDetail:
    art = v.artifact
    preview = (art.extracted_text or "")[:1200]
    jsonl_path = None
    if isinstance(art.extraction_warnings, dict):
        jsonl_path = art.extraction_warnings.get("jsonl_path")
    return VersionDetail(
        version_id=v.version_id,
        doc_id=v.doc_id,
        version_number=v.version_number,
        state=v.state,
        title=v.title,
        summary=v.summary,
        topic_tags=list(v.topic_tags or []),
        scripture_refs=list(v.scripture_refs or []),
        body_patch=v.body_patch,
        jsonl_path=jsonl_path,
        extracted_text_preview=preview,
        extraction_quality_score=art.extraction_quality_score,
        extraction_warnings=dict(art.extraction_warnings or {}),
        checklist=dict(v.checklist or {}),
        validation_report=dict(v.validation_report or {}),
        created_at=v.created_at.isoformat(),
        published_at=v.published_at.isoformat() if v.published_at else None,
    )


# ---------- inbox 폴더 관리 (⚠ 정적 경로 — /{doc_id} 보다 반드시 먼저 등록해야 shadow 안 됨) ----------
_INBOX_DIR = settings.root_dir / "data" / "inbox"
_PROCESSED_DIR = _INBOX_DIR / "processed"
_SUPPORTED_EXT = {".md", ".txt", ".pdf", ".docx"}


@router.get("/inbox")
def list_inbox(authorization: Optional[str] = Header(default=None)):
    """data/inbox/ 폴더의 처리 대기 파일 목록."""
    _check_admin(authorization)
    _INBOX_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    files = []
    for f in _INBOX_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in _SUPPORTED_EXT:
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_bytes": stat.st_size,
                "ext": f.suffix.lower().lstrip("."),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files, "inbox_path": str(_INBOX_DIR)}


@router.post("/ingest-inbox")
async def ingest_inbox_async(
    filenames: str = Form(...),        # JSON 배열 문자열: '["a.md","b.pdf"]'
    doc_type: str = Form("sermon"),
    authorization: Optional[str] = Header(default=None),
):
    """inbox 폴더의 선택한 파일들을 일괄 비동기 처리."""
    import json as _json
    _check_admin(authorization)
    _INBOX_DIR.mkdir(parents=True, exist_ok=True)
    _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        names = _json.loads(filenames)
    except Exception:
        raise HTTPException(400, "filenames must be JSON array string")

    if not names:
        raise HTTPException(400, "no files selected")

    to_process = []
    for name in names:
        path = _INBOX_DIR / name
        if path.is_file() and path.suffix.lower() in _SUPPORTED_EXT:
            to_process.append(path)

    if not to_process:
        raise HTTPException(404, "no valid files found in inbox")

    job_id = job_service.create_job("ingest_inbox")

    async def _run():
        try:
            total = len(to_process)
            done = []
            errors = []

            def _stage(stage: str, detail: str = "", pct: int = 0):
                job_service.update_stage(job_id, stage, detail, pct)

            for i, fpath in enumerate(to_process):
                pct_base = int((i / total) * 90)
                _stage(f"📂 처리 중 ({i+1}/{total})", fpath.name, pct_base)
                raw = fpath.read_bytes()
                title_guess = fpath.stem.replace("_", " ").replace("-", " ")

                def _sync_one(raw=raw, fname=fpath.name, title=title_guess):
                    with get_session() as s:
                        artifact, _ = source_service.ingest_file(
                            s, filename=fname, raw=raw, progress_cb=None,
                        )
                        _artifact_id    = artifact.artifact_id
                        _content_hash   = artifact.content_hash
                        _extracted_head = (artifact.extracted_text or "")[:500]

                    from ..models.orm import SourceArtifact as _SA
                    with get_session() as s:
                        fresh_art = s.get(_SA, _artifact_id)
                        version = document_service.create_draft_from_artifact(
                            s, artifact=fresh_art,
                            title=title, doc_type=doc_type,
                        )
                        _doc_id = version.doc_id
                        det     = _to_version_detail(version)

                    with get_session() as s:
                        hits = dedup_service.check_on_upload(
                            s, content_hash=_content_hash,
                            proposed_title=title,
                            extracted_head=_extracted_head,
                        )
                        det.dup_hits = [
                            dedup_service.to_dict(h) for h in hits if h.doc_id != _doc_id
                        ]
                    return det.model_dump()

                try:
                    result = await asyncio.to_thread(_sync_one)
                    done.append({
                        "file": fpath.name,
                        "title": result.get("title"),
                        "version_id": result.get("version_id"),
                    })
                    import shutil
                    shutil.move(str(fpath), str(_PROCESSED_DIR / fpath.name))
                except Exception as e:
                    errors.append({"file": fpath.name, "error": str(e)[:200]})

            job_service.complete_job(job_id, {
                "done": done, "errors": errors,
                "total": total, "success_count": len(done),
            })
        except Exception as e:
            import traceback as _tb
            job_service.fail_job(job_id, {
                "error": str(e)[:400],
                "traceback": _tb.format_exc()[:2000],
            })

    asyncio.create_task(_run())
    return {"job_id": job_id, "file_count": len(to_process)}


# ---------- 1) Upload ----------
@router.post("/upload", response_model=VersionDetail)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form("sermon"),
    series: Optional[str] = Form(None),
    speaker: Optional[str] = Form(None),
    topic_tags: Optional[str] = Form(None),  # CSV
    scripture_refs: Optional[str] = Form(None),  # CSV
    summary: Optional[str] = Form(None),
    # D-C17: salvation/darakbang metadata
    target_salvation_stage: Optional[str] = Form(None),  # CSV e.g. "seeker,gospel_core"
    darakbang_tier: Optional[str] = Form(None),
    salvation_focus_score: Optional[float] = Form(None),
    gospel_core_tag: Optional[bool] = Form(None),
    authorization: Optional[str] = Header(default=None),
):
    """완성본 업로드 -> L1 artifact + L2 draft 생성."""
    _check_admin(authorization)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")

    tags = [t.strip() for t in (topic_tags or "").split(",") if t.strip()]
    refs = [r.strip() for r in (scripture_refs or "").split(",") if r.strip()]
    salvation_stages = [s.strip() for s in (target_salvation_stage or "").split(",") if s.strip()] or None

    # extraction_service.extract() 는 순수 동기 블로킹 (pypdf/docx) → 스레드 풀로 분리,
    # 이벤트 루프 차단 없이 대용량 파일도 처리 가능
    def _ingest_sync():
        with get_session() as s:
            artifact, is_new = source_service.ingest_file(
                s, filename=file.filename or "untitled", raw=raw,
            )
            version = document_service.create_draft_from_artifact(
                s,
                artifact=artifact,
                title=title,
                doc_type=doc_type,
                series=series,
                speaker=speaker,
                topic_tags=tags,
                scripture_refs=refs,
                summary=summary,
                target_salvation_stage=salvation_stages,
                darakbang_tier=darakbang_tier or None,
                salvation_focus_score=salvation_focus_score,
                gospel_core_tag=bool(gospel_core_tag) if gospel_core_tag is not None else False,
            )
            hits = dedup_service.check_on_upload(
                s,
                content_hash=artifact.content_hash,
                proposed_title=title,
                extracted_head=(artifact.extracted_text or "")[:500],
            )
            detail = _to_version_detail(version)
            detail.dup_hits = [dedup_service.to_dict(h) for h in hits if h.doc_id != version.doc_id]
            return detail

    return await asyncio.to_thread(_ingest_sync)


# ---------- 1b) Upload-Async — 즉시 job_id 반환, 백그라운드에서 처리 ----------
@router.post("/upload-async")
async def upload_document_async(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form("sermon"),
    series: Optional[str] = Form(None),
    speaker: Optional[str] = Form(None),
    topic_tags: Optional[str] = Form(None),
    scripture_refs: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    target_salvation_stage: Optional[str] = Form(None),
    darakbang_tier: Optional[str] = Form(None),
    salvation_focus_score: Optional[float] = Form(None),
    gospel_core_tag: Optional[bool] = Form(None),
    authorization: Optional[str] = Header(default=None),
):
    """비동기 업로드 — job_id 즉시 반환, GET /jobs/{job_id} 로 폴링."""
    _check_admin(authorization)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")

    tags = [t.strip() for t in (topic_tags or "").split(",") if t.strip()]
    refs = [r.strip() for r in (scripture_refs or "").split(",") if r.strip()]
    salvation_stages = [s.strip() for s in (target_salvation_stage or "").split(",") if s.strip()] or None
    _gospel_core = bool(gospel_core_tag) if gospel_core_tag is not None else False
    _filename = file.filename or "untitled"

    job_id = job_service.create_job("upload")

    async def _run():
        """asyncio task — 스레드 풀에서 블로킹 작업 실행."""
        try:
            def _stage(stage: str, detail: str = "", pct: int = 0):
                job_service.update_stage(job_id, stage, detail, pct)

            def _sync_work():
                # ── 1단계: 파일 수신 (세션 없음) ──────────────────────────────
                _stage("📁 파일 수신 완료", f"{_filename} ({len(raw):,} bytes)", 5)
                _stage("🔍 파일 해시 계산 중...", "", 8)
                _stage("📄 텍스트 추출 중...", "파일 파싱 시작...", 10)

                # ── 2단계: artifact 생성 (독립 세션 — progress_cb 없음) ────────
                # ⚠️ 이유: progress_cb 안에서 job_service.update_stage() 가 별도
                #          get_session() 을 열면 → SQLite 데드락(무한 대기).
                #          세션을 닫은 뒤에만 job_service 쓰기가 안전하다.
                with get_session() as s:
                    artifact, is_new = source_service.ingest_file(
                        s, filename=_filename, raw=raw,
                        progress_cb=None,   # 데드락 방지: 세션 내 중첩 write 금지
                    )
                    # 세션 닫기 전에 필요한 값을 전부 추출 (lazy-load 방지)
                    _artifact_id    = artifact.artifact_id
                    _quality        = artifact.extraction_quality_score
                    _content_hash   = artifact.content_hash
                    _extracted_head = (artifact.extracted_text or "")[:500]
                # ← 세션 커밋+종료. 이후 job_service 쓰기 안전.

                _stage("📊 품질 분석 완료", f"품질 점수: {_quality}/100", 65)
                _stage("💾 초안 생성 중...", "", 75)

                # ── 3단계: 드래프트 생성 (독립 세션) ─────────────────────────
                from ..models.orm import SourceArtifact as _SA
                with get_session() as s:
                    fresh_art = s.get(_SA, _artifact_id)
                    version = document_service.create_draft_from_artifact(
                        s,
                        artifact=fresh_art,
                        title=title,
                        doc_type=doc_type,
                        series=series,
                        speaker=speaker,
                        topic_tags=tags,
                        scripture_refs=refs,
                        summary=summary,
                        target_salvation_stage=salvation_stages,
                        darakbang_tier=darakbang_tier or None,
                        salvation_focus_score=salvation_focus_score,
                        gospel_core_tag=_gospel_core,
                    )
                    _version_id = version.version_id
                    _doc_id     = version.doc_id
                    # _to_version_detail 은 artifact lazy-load 필요 → 세션 내에서 호출
                    detail = _to_version_detail(version)
                # ← 세션 커밋+종료.

                _stage("🔎 중복 감지 중...", "", 85)

                # ── 4단계: 중복 감지 (독립 세션) ──────────────────────────────
                with get_session() as s:
                    hits = dedup_service.check_on_upload(
                        s,
                        content_hash=_content_hash,
                        proposed_title=title,
                        extracted_head=_extracted_head,
                    )
                    detail.dup_hits = [
                        dedup_service.to_dict(h) for h in hits if h.doc_id != _doc_id
                    ]

                return detail.model_dump()

            result = await asyncio.to_thread(_sync_work)
            job_service.complete_job(job_id, result)
        except Exception as e:
            import traceback as _tb
            job_service.fail_job(job_id, {
                "error": str(e)[:400],
                "traceback": _tb.format_exc()[:2000],
            })

    asyncio.create_task(_run())
    return {"job_id": job_id}


# ---------- 2) List ----------
@router.get("", response_model=list[DocumentSummary])
def list_documents(
    state: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        rows = document_service.list_documents(s, state_filter=state)
    return [DocumentSummary(**r) for r in rows]


# ---------- 2b) Patch document-level meta (speaker / series / doc_type) ----------
@router.patch("/{doc_id}")
def patch_document_meta(
    doc_id: str, payload: DocMetaIn,
    authorization: Optional[str] = Header(default=None),
):
    """버전과 무관한 document 레벨 필드 수정 (speaker, series, doc_type)."""
    _check_admin(authorization)
    with get_session() as s:
        doc = document_service.get_document(s, doc_id)
        if not doc:
            raise HTTPException(404, "document not found")
        if payload.speaker is not None:
            doc.speaker = payload.speaker
        if payload.series is not None:
            doc.series = payload.series
        if payload.doc_type is not None:
            doc.doc_type = payload.doc_type
        s.commit()
        return {"ok": True, "doc_id": doc_id}


# ---------- 3) Get detail ----------
@router.get("/{doc_id}")
def get_document(doc_id: str, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        doc = document_service.get_document(s, doc_id)
        if not doc:
            raise HTTPException(404, "document not found")
        versions = sorted(doc.versions, key=lambda v: v.version_number, reverse=True)
        return {
            "doc_id": doc.doc_id,
            "doc_key": doc.doc_key,
            "doc_type": doc.doc_type,
            "series": doc.series,
            "speaker": doc.speaker,
            "is_canonical": doc.is_canonical,
            "archived_at": doc.archived_at.isoformat() if doc.archived_at else None,
            "versions": [_to_version_detail(v).model_dump() for v in versions],
        }


# ---------- 4) Patch meta ----------
@router.patch("/{doc_id}/versions/{version_id}", response_model=VersionDetail)
def patch_version_meta(
    doc_id: str, version_id: str, payload: DraftMetaIn,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        document_service.update_draft_meta(
            s, version=v,
            title=payload.title, summary=payload.summary,
            topic_tags=payload.topic_tags, scripture_refs=payload.scripture_refs,
            checklist=payload.checklist,
        )
        return _to_version_detail(v)


# ---------- 5) Body patch ----------
@router.patch("/{doc_id}/versions/{version_id}/body", response_model=VersionDetail)
def patch_version_body(
    doc_id: str, version_id: str, payload: BodyPatchIn,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        document_service.patch_body(s, version=v, new_body=payload.body)
        return _to_version_detail(v)


# ---------- 6) Validate ----------
@router.post("/{doc_id}/versions/{version_id}/validate")
def validate_version(
    doc_id: str, version_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        ok, report = document_service.validate_version(s, version=v)
        return {"passed": ok, "report": report, "state": v.state}


# ---------- 7) Publish ----------
@router.post("/{doc_id}/versions/{version_id}/publish")
def publish_version(
    doc_id: str, version_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        try:
            snap = publish_service.publish_version(s, version=v)
        except ValueError as e:
            raise HTTPException(400, str(e))

        # 발행 시 자동 용어 추출 (LLM 없음, 빠름)
        _source_text = v.body_patch or (v.artifact.extracted_text if v.artifact else "") or ""
        _terms: list[str] = []
        if _source_text.strip():
            from ..services.cleanup_pipeline import extract_terms
            _terms = extract_terms(_source_text)
            if _terms:
                audit_service.log(
                    s, action="document.terms_extracted", entity_type="document_version",
                    entity_id=version_id, who="system",
                    note={"terms": _terms, "auto": True},
                )

        return {
            "ok": True,
            "snapshot_id": snap.snapshot_id,
            "chunks": snap.chunk_count,
            "collection": snap.collection_name,
            "terms_found": _terms,  # 발행 응답에 용어 목록 포함
        }


# ---------- 7b) Publish-Async — job_id 즉시 반환 ----------
@router.post("/{doc_id}/versions/{version_id}/publish-async")
async def publish_version_async(
    doc_id: str, version_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """비동기 공개 — job_id 즉시 반환, GET /jobs/{job_id} 로 폴링."""
    _check_admin(authorization)

    # 버전 존재 확인 (즉시 — 404는 빠르게)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        cur_state = v.state

    if cur_state not in {"draft", "validated"}:
        raise HTTPException(400, f"Cannot publish version in state {cur_state}")

    job_id = job_service.create_job("publish")

    async def _run():
        try:
            def _sync_work():
                # ⚠️ progress_cb 를 세션 내부에서 쓰면 SQLite 데드락.
                # 단계 업데이트는 세션 밖에서만 호출한다.
                job_service.update_stage(job_id, "📝 청킹 중...", "", 10)
                job_service.update_stage(job_id, "🧮 임베딩 생성 중...", "시작...", 15)

                # 독립 세션 — 내부에서 job_service 호출 없음
                with get_session() as s:
                    v = document_service.get_version(s, version_id)
                    if not v:
                        raise ValueError("version not found")
                    snap = publish_service.publish_version(
                        s, version=v,
                        progress_cb=None,   # 데드락 방지: 세션 내 중첩 write 금지
                    )
                    _source_text = v.body_patch or (v.artifact.extracted_text if v.artifact else "") or ""
                    _result = {
                        "ok": True,
                        "snapshot_id": snap.snapshot_id,
                        "chunks": snap.chunk_count,
                        "collection": snap.collection_name,
                    }

                # ← 세션 커밋+종료. 이후 job_service 쓰기 안전.

                # 자동 용어 추출 (세션 밖 — LLM 없음, 빠름)
                from ..services.cleanup_pipeline import extract_terms as _extract_terms
                _terms: list[str] = []
                if _source_text.strip():
                    _terms = _extract_terms(_source_text)
                    _result["terms_found"] = _terms
                    if _terms:
                        job_service.update_stage(
                            job_id, "🔍 용어 추출 완료",
                            f"{len(_terms)}개 발견", 95,
                        )

                job_service.update_stage(job_id, "🗂 Qdrant 인덱스 저장 완료",
                                         f"{_result['chunks']}개 청크", 90)
                job_service.update_stage(job_id, "💾 DB 상태 업데이트 중...", "", 98)
                return _result

            result = await asyncio.to_thread(_sync_work)
            job_service.complete_job(job_id, result)
        except Exception as e:
            import traceback as _tb
            job_service.fail_job(job_id, {
                "error": str(e)[:400],
                "traceback": _tb.format_exc()[:2000],
            })

    asyncio.create_task(_run())
    return {"job_id": job_id}


# ---------- 8) 용어 추출 (구 Cleanup endpoint — 하위 호환 유지) ----------
# 발행 시 자동 실행되므로 수동 호출은 거의 불필요.
# 텍스트 수정 없음 — 용어 목록만 반환.
class CleanupIn(BaseModel):
    stages: list[int] = [5]   # 용어 추출만 (다른 값 무시)
    dry_run: bool = False


@router.post("/{doc_id}/versions/{version_id}/cleanup")
async def run_cleanup_endpoint(
    doc_id: str, version_id: str, payload: CleanupIn,
    authorization: Optional[str] = Header(default=None),
):
    """용어 추출 실행 (텍스트 변경 없음).
    발행(publish) 시 자동 실행되므로 수동 호출은 선택 사항.
    """
    _check_admin(authorization)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        art = v.artifact
        source_text = v.body_patch or (art.extracted_text if art else "") or ""
        if not source_text.strip():
            raise HTTPException(400, "텍스트가 없습니다 (body_patch/extracted_text 비어있음)")

    from ..services.cleanup_pipeline import extract_terms
    terms = extract_terms(source_text)

    if not payload.dry_run and terms:
        with get_session() as s:
            v = document_service.get_version(s, version_id)
            audit_service.log(
                s, action="document.terms_extracted", entity_type="document_version",
                entity_id=version_id, who="admin",
                note={"terms": terms, "auto": False},
            )

    return {
        "ok": True,
        "terms_found": terms,
        "terms_count": len(terms),
        "note": "텍스트 변경 없음 — 용어 추출만 수행 (발행 시 자동 실행됨)",
    }


# ---------- 9) New version (재업로드) ----------
@router.post("/{doc_id}/new-version", response_model=VersionDetail)
async def new_version(
    doc_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    authorization: Optional[str] = Header(default=None),
):
    _check_admin(authorization)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")

    def _new_version_sync():
        with get_session() as s:
            doc = document_service.get_document(s, doc_id)
            if not doc:
                raise HTTPException(404, "document not found")
            artifact, _ = source_service.ingest_file(
                s, filename=file.filename or "untitled", raw=raw,
            )
            v = document_service.create_new_version(
                s, doc=doc, artifact=artifact, title=title,
            )
            return _to_version_detail(v)

    return await asyncio.to_thread(_new_version_sync)


# ---------- 9) Archive ----------
@router.delete("/{doc_id}")
def archive_document(doc_id: str, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        doc = document_service.get_document(s, doc_id)
        if not doc:
            raise HTTPException(404, "document not found")
        document_service.archive_document(s, doc=doc)
        return {"ok": True}


# ---------- audit log ----------
@router.get("/{doc_id}/audit")
def get_audit(doc_id: str, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    with get_session() as s:
        rows = audit_service.list_for(s, doc_id, limit=200)
        out = []
        for r in rows:
            out.append({
                "when": r.when.isoformat(),
                "who": r.who,
                "action": r.action,
                "from_state": r.from_state,
                "to_state": r.to_state,
                "note": r.note,
            })
    return out


# ---------- Bulk ----------
class BulkActionIn(BaseModel):
    doc_ids: list[str]
    action: str  # "publish" | "archive"


@router.post("/bulk-action")
def bulk_action(payload: BulkActionIn, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    if payload.action not in {"publish", "archive"}:
        raise HTTPException(400, "action must be 'publish' or 'archive'")
    if not payload.doc_ids:
        raise HTTPException(400, "doc_ids empty")
    results = []
    with get_session() as s:
        for doc_id in payload.doc_ids:
            try:
                doc = document_service.get_document(s, doc_id)
                if not doc:
                    results.append({"doc_id": doc_id, "ok": False, "err": "not found"})
                    continue
                if payload.action == "archive":
                    document_service.archive_document(s, doc=doc)
                    results.append({"doc_id": doc_id, "ok": True})
                else:  # publish
                    versions = sorted(doc.versions, key=lambda v: -v.version_number)
                    target = next((v for v in versions if v.state in ("draft", "validated")), None)
                    if not target:
                        results.append({"doc_id": doc_id, "ok": False, "err": "no draft/validated version"})
                        continue
                    snap = publish_service.publish_version(s, version=target)
                    results.append({"doc_id": doc_id, "ok": True, "chunks": snap.chunk_count})
            except Exception as e:
                results.append({"doc_id": doc_id, "ok": False, "err": str(e)[:120]})
    return {"results": results, "ok_count": sum(1 for r in results if r["ok"])}


# ---------- 직접 입력 (텍스트/마크다운 붙여넣기) ----------
@router.post("/ingest-text")
async def ingest_text_async(
    title: str = Form(...),
    content: str = Form(...),          # 마크다운/텍스트 본문
    doc_type: str = Form("sermon"),
    series: Optional[str] = Form(None),
    speaker: Optional[str] = Form(None),
    topic_tags: Optional[str] = Form(None),   # CSV
    scripture_refs: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    authorization: Optional[str] = Header(default=None),
):
    """텍스트를 직접 입력받아 비동기 처리. 파일 업로드 불필요."""
    _check_admin(authorization)
    if not content.strip():
        raise HTTPException(400, "content is empty")

    # 텍스트를 UTF-8 bytes 로 변환 → .md 파일처럼 처리
    raw = content.encode("utf-8")
    _filename = f"{title[:60].strip()}.md"
    tags = [t.strip() for t in (topic_tags or "").split(",") if t.strip()]
    refs = [r.strip() for r in (scripture_refs or "").split(",") if r.strip()]

    job_id = job_service.create_job("ingest_text")

    async def _run():
        try:
            def _stage(stage: str, detail: str = "", pct: int = 0):
                job_service.update_stage(job_id, stage, detail, pct)

            def _sync_work():
                _stage("📝 텍스트 파싱 중...", f"{len(raw):,} bytes", 10)

                with get_session() as s:
                    artifact, is_new = source_service.ingest_file(
                        s, filename=_filename, raw=raw,
                        progress_cb=None,
                    )
                    _artifact_id    = artifact.artifact_id
                    _quality        = artifact.extraction_quality_score
                    _content_hash   = artifact.content_hash
                    _extracted_head = (artifact.extracted_text or "")[:500]

                _stage("📊 품질 분석 완료", f"품질 점수: {_quality}/100", 65)
                _stage("💾 초안 생성 중...", "", 75)

                from ..models.orm import SourceArtifact as _SA
                with get_session() as s:
                    fresh_art = s.get(_SA, _artifact_id)
                    version = document_service.create_draft_from_artifact(
                        s,
                        artifact=fresh_art,
                        title=title,
                        doc_type=doc_type,
                        series=series,
                        speaker=speaker,
                        topic_tags=tags,
                        scripture_refs=refs,
                        summary=summary,
                    )
                    _version_id = version.version_id
                    _doc_id     = version.doc_id
                    detail      = _to_version_detail(version)

                _stage("🔎 중복 감지 중...", "", 85)
                with get_session() as s:
                    hits = dedup_service.check_on_upload(
                        s,
                        content_hash=_content_hash,
                        proposed_title=title,
                        extracted_head=_extracted_head,
                    )
                    detail.dup_hits = [
                        dedup_service.to_dict(h) for h in hits if h.doc_id != _doc_id
                    ]
                return detail.model_dump()

            result = await asyncio.to_thread(_sync_work)
            job_service.complete_job(job_id, result)
        except Exception as e:
            import traceback as _tb
            job_service.fail_job(job_id, {
                "error": str(e)[:400],
                "traceback": _tb.format_exc()[:2000],
            })

    asyncio.create_task(_run())
    return {"job_id": job_id}


