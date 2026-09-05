"""L2 Document + DocumentVersion lifecycle 관리.

상태 전이:
  draft → validated → published → superseded
                    ↘ archived

API:
- create_draft_from_artifact: L1 -> 새 doc + v1 (draft)
- create_new_version: 기존 doc에 새 버전 추가 (재업로드)
- update_draft_meta: draft 상태일 때만 메타데이터 수정
- patch_body: 마이크로 패치 (draft만)
- validate_version: draft -> validated (체크리스트 통과 시)
- archive_doc / archive_version
"""
from __future__ import annotations
import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models.orm import (
    Document, DocumentVersion, DocVersionState, SourceArtifact,
)
from . import audit_service


REQUIRED_CHECKLIST_KEYS = ["theology_ok", "source_cited", "scripture_verified", "tone_ok"]


def slugify(s: str) -> str:
    s = re.sub(r"\s+", "-", s.strip().lower())
    s = re.sub(r"[^\w가-힣\-]", "", s)
    return s[:80] or "doc"


def list_documents(session: Session, *, state_filter: Optional[str] = None) -> list[dict]:
    """Admin 라이브러리용 — 문서 + 현재 active version 요약."""
    docs = session.query(Document).order_by(Document.updated_at.desc()).all()
    out = []
    for d in docs:
        if d.archived_at:
            continue
        # 가장 최근 버전
        versions = sorted(d.versions, key=lambda v: v.version_number, reverse=True)
        if not versions:
            continue
        latest = versions[0]
        published = next((v for v in versions if v.state == DocVersionState.published.value), None)
        if state_filter:
            states = {v.state for v in versions}
            if state_filter not in states:
                continue
        out.append({
            "doc_id": d.doc_id,
            "doc_key": d.doc_key,
            "doc_type": d.doc_type,
            "series": d.series,
            "speaker": d.speaker,
            "is_canonical": d.is_canonical,
            "latest_version": latest.version_number,
            "latest_state": latest.state,
            "published_version": published.version_number if published else None,
            "title": (published or latest).title,
            "updated_at": d.updated_at.isoformat(),
        })
    return out


def get_document(session: Session, doc_id: str) -> Optional[Document]:
    return session.query(Document).filter(Document.doc_id == doc_id).first()


def get_version(session: Session, version_id: str) -> Optional[DocumentVersion]:
    return session.query(DocumentVersion).filter(DocumentVersion.version_id == version_id).first()


def create_draft_from_artifact(
    session: Session,
    *,
    artifact: SourceArtifact,
    title: str,
    doc_type: str = "sermon",
    doc_key: Optional[str] = None,
    series: Optional[str] = None,
    speaker: Optional[str] = None,
    topic_tags: Optional[list[str]] = None,
    scripture_refs: Optional[list[str]] = None,
    summary: Optional[str] = None,
    # D-C17: salvation/darakbang metadata
    target_salvation_stage: Optional[list[str]] = None,
    darakbang_tier: Optional[str] = None,
    salvation_focus_score: Optional[float] = None,
    gospel_core_tag: bool = False,
    who: str = "admin",
) -> DocumentVersion:
    """새 Document + 첫 버전 (draft) 생성."""
    if not doc_key:
        doc_key = f"{doc_type}-{slugify(title)}"
    # doc_key 충돌 시 suffix
    base = doc_key
    n = 1
    while session.query(Document).filter(Document.doc_key == doc_key).first():
        n += 1
        doc_key = f"{base}-{n}"

    doc = Document(
        doc_key=doc_key,
        doc_type=doc_type,
        series=series,
        speaker=speaker,
    )
    session.add(doc)
    session.flush()

    version = DocumentVersion(
        doc_id=doc.doc_id,
        version_number=1,
        artifact_id=artifact.artifact_id,
        state=DocVersionState.draft.value,
        title=title,
        summary=summary,
        scripture_refs=scripture_refs or [],
        topic_tags=topic_tags or [],
        chunking_policy={"preset": doc_type},
        checklist={k: False for k in REQUIRED_CHECKLIST_KEYS},
        target_salvation_stage=target_salvation_stage,
        darakbang_tier=darakbang_tier,
        salvation_focus_score=salvation_focus_score if salvation_focus_score is not None else 0.0,
        gospel_core_tag=gospel_core_tag,
    )
    session.add(version)
    session.flush()

    audit_service.log(
        session, action="document.create", entity_type="document",
        entity_id=doc.doc_id, who=who, to_state="draft",
        note={"doc_key": doc_key, "version": 1},
    )
    return version


def create_new_version(
    session: Session,
    *,
    doc: Document,
    artifact: SourceArtifact,
    title: Optional[str] = None,
    who: str = "admin",
) -> DocumentVersion:
    """기존 문서에 새 버전 추가 (재업로드)."""
    versions = sorted(doc.versions, key=lambda v: -v.version_number)
    last_num = versions[0].version_number if versions else 0
    base_title = title or (versions[0].title if versions else doc.doc_key)

    v = DocumentVersion(
        doc_id=doc.doc_id,
        version_number=last_num + 1,
        artifact_id=artifact.artifact_id,
        state=DocVersionState.draft.value,
        title=base_title,
        chunking_policy={"preset": doc.doc_type},
        checklist={k: False for k in REQUIRED_CHECKLIST_KEYS},
    )
    session.add(v)
    session.flush()

    audit_service.log(
        session, action="version.create", entity_type="document_version",
        entity_id=v.version_id, who=who, to_state="draft",
        note={"version": v.version_number},
    )
    return v


def update_draft_meta(
    session: Session,
    *,
    version: DocumentVersion,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    topic_tags: Optional[list[str]] = None,
    scripture_refs: Optional[list[str]] = None,
    checklist: Optional[dict] = None,
    who: str = "admin",
) -> DocumentVersion:
    if version.state != DocVersionState.draft.value:
        raise ValueError(f"Cannot edit non-draft version ({version.state})")
    if title is not None: version.title = title
    if summary is not None: version.summary = summary
    if topic_tags is not None: version.topic_tags = topic_tags
    if scripture_refs is not None: version.scripture_refs = scripture_refs
    if checklist is not None:
        merged = dict(version.checklist or {})
        merged.update(checklist)
        version.checklist = merged
    session.flush()
    audit_service.log(
        session, action="version.update_meta", entity_type="document_version",
        entity_id=version.version_id, who=who,
    )
    return version


def patch_body(session: Session, *, version: DocumentVersion, new_body: str, who: str = "admin") -> DocumentVersion:
    """마이크로 패치 — draft 상태에서만."""
    if version.state != DocVersionState.draft.value:
        raise ValueError("body patch only allowed in draft state")
    version.body_patch = new_body
    session.flush()
    audit_service.log(
        session, action="version.patch_body", entity_type="document_version",
        entity_id=version.version_id, who=who,
        note={"len": len(new_body)},
    )
    return version


def validate_version(session: Session, *, version: DocumentVersion, who: str = "admin") -> tuple[bool, dict]:
    """체크리스트 + 기본 검증 통과 시 draft -> validated."""
    report: dict = {"checks": {}, "errors": []}

    # 체크리스트 필수
    cl = version.checklist or {}
    for k in REQUIRED_CHECKLIST_KEYS:
        ok = bool(cl.get(k))
        report["checks"][k] = ok
        if not ok:
            report["errors"].append(f"체크리스트 미통과: {k}")

    # 기본 필드
    if not version.title or len(version.title) < 2:
        report["errors"].append("title 누락")
    if not version.topic_tags:
        report["errors"].append("topic_tags 최소 1개 필요")

    report["passed"] = not report["errors"]
    version.validation_report = report

    if report["passed"]:
        version.state = DocVersionState.validated.value
        audit_service.log(
            session, action="version.validate", entity_type="document_version",
            entity_id=version.version_id, who=who,
            from_state="draft", to_state="validated", note=report,
        )
    session.flush()
    return report["passed"], report


def archive_document(session: Session, *, doc: Document, who: str = "admin"):
    from datetime import datetime, timezone
    doc.archived_at = datetime.now(timezone.utc)
    for v in doc.versions:
        if v.state == DocVersionState.published.value:
            v.state = DocVersionState.archived.value
    session.flush()
    audit_service.log(
        session, action="document.archive", entity_type="document",
        entity_id=doc.doc_id, who=who, to_state="archived",
    )


def get_effective_body(version: DocumentVersion, session: Session | None = None) -> str:
    """body_patch 가 있으면 그것, 없으면 artifact의 추출 텍스트.

    version.artifact 는 lazy 관계라 세션이 닫힌 상태(detached)에서 접근하면
    DetachedInstanceError 가 난다. 가능하면 인자로 받은 세션 또는 첨부 세션을
    사용해 artifact 를 명시적으로 조회한다(항상 로드된 상태 보장).
    """
    if version.body_patch:
        return version.body_patch
    if session is None:
        from sqlalchemy import inspect as _inspect

        session = _inspect(version).session
    if session is not None:
        art = session.get(SourceArtifact, version.artifact_id)
        if art is not None:
            return art.extracted_text or ""
    # 폴백: 첨부 세션이 없으면 이미 로드된 관계 사용 (detached+미로드 시 예외 가능)
    if version.artifact is not None:
        return version.artifact.extracted_text or ""
    return ""
