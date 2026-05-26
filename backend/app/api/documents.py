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
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..db import get_session
from ..models.orm import DocVersionState
from ..services import (
    audit_service, document_service, publish_service, source_service, dedup_service,
)

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

    with get_session() as s:
        artifact, is_new = source_service.ingest_file(
            s, filename=file.filename or "untitled", raw=raw,
        )
        # 중복 hash일 경우에도 새 draft 만들지 여부 — MVP는 항상 새 draft.
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
        # 중복 감지
        hits = dedup_service.check_on_upload(
            s,
            content_hash=artifact.content_hash,
            proposed_title=title,
            extracted_head=(artifact.extracted_text or "")[:500],
        )
        detail = _to_version_detail(version)
        detail.dup_hits = [dedup_service.to_dict(h) for h in hits if h.doc_id != version.doc_id]
        return detail


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
        return {
            "ok": True,
            "snapshot_id": snap.snapshot_id,
            "chunks": snap.chunk_count,
            "collection": snap.collection_name,
        }


# ---------- 8) Cleanup pipeline (E-D) ----------
class CleanupIn(BaseModel):
    stages: list[int] = [1, 2, 3, 4, 5]
    dry_run: bool = False  # True → 결과 반환만, DB 저장 안 함


@router.post("/{doc_id}/versions/{version_id}/cleanup")
async def run_cleanup_endpoint(
    doc_id: str, version_id: str, payload: CleanupIn,
    authorization: Optional[str] = Header(default=None),
):
    """E-D: 5단계 정제 파이프라인 실행. dry_run=True 면 저장 없이 결과만 반환."""
    _check_admin(authorization)
    with get_session() as s:
        v = document_service.get_version(s, version_id)
        if not v or v.doc_id != doc_id:
            raise HTTPException(404, "version not found")
        art = v.artifact
        source_text = v.body_patch or art.extracted_text or ""
        if not source_text.strip():
            raise HTTPException(400, "정제할 텍스트가 없습니다 (body_patch/extracted_text 비어있음)")

    from ..services.cleanup_pipeline import run_cleanup
    result = await run_cleanup(source_text, stages=payload.stages)

    if not payload.dry_run:
        with get_session() as s:
            v = document_service.get_version(s, version_id)
            document_service.patch_body(s, version=v, new_body=result.final_text)
            audit_service.log(
                s, action="document.cleanup", entity_type="document_version",
                entity_id=version_id, who="admin",
                note={
                    "stages": payload.stages,
                    "warnings": result.warnings,
                    "theology_violations": result.theology_violations,
                    "terms_count": len(result.terms_found),
                },
            )

    return {
        "ok": True,
        "dry_run": payload.dry_run,
        "original_len": len(result.original_text),
        "final_len": len(result.final_text),
        "diffs": [
            {"stage": d.stage, "reason": d.reason,
             "original": d.original[:200], "modified": d.modified[:200]}
            for d in result.diffs
        ],
        "warnings": result.warnings,
        "theology_violations": result.theology_violations,
        "terms_found": result.terms_found,
        "stage_texts": {str(k): v[:500] for k, v in result.stage_texts.items()},
        "final_text_preview": result.final_text[:800],
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


# ---------- helpers ----------
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
