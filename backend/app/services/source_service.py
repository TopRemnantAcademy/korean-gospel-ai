"""L1 SourceArtifact 관리.

- hash 기반 중복 즉시 감지
- 추출 + 품질점수
- 원본 파일 로컬 저장 (data/uploads/)
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models.orm import SourceArtifact
from . import extraction_service
from . import audit_service
from .chunker import chunk_text


UPLOADS_DIR = settings.root_dir / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def find_by_hash(session: Session, content_hash: str) -> Optional[SourceArtifact]:
    return session.query(SourceArtifact).filter(SourceArtifact.content_hash == content_hash).first()


def ingest_file(
    session: Session,
    *,
    filename: str,
    raw: bytes,
    uploaded_by: str = "admin",
) -> tuple[SourceArtifact, bool]:
    """파일을 받아 L1 artifact 생성.
    Returns (artifact, is_new) — is_new=False면 같은 hash가 이미 있음.
    """
    content_hash = hashlib.sha256(raw).hexdigest()
    existing = find_by_hash(session, content_hash)
    if existing:
        return existing, False

    # 추출
    res = extraction_service.extract(filename, raw)

    # 원본 파일 저장
    storage_path = UPLOADS_DIR / f"{content_hash[:12]}_{Path(filename).name}"
    storage_path.write_bytes(raw)

    mime = _guess_mime(filename)
    warnings = dict(res.warnings or {})

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in {"txt", "md"} and res.text:
        ok, jsonl_rel, err = _write_jsonl(
            storage_path=storage_path,
            extracted_text=res.text,
            base_metadata={
                "original_filename": filename,
                "content_hash": content_hash,
                "mime_type": mime,
            },
        )
        if ok and jsonl_rel:
            warnings["jsonl_path"] = jsonl_rel
        elif err:
            warnings["jsonl_error"] = err
    artifact = SourceArtifact(
        original_filename=filename,
        content_hash=content_hash,
        mime_type=mime,
        size_bytes=len(raw),
        extracted_text=res.text,
        extraction_quality_score=res.quality_score,
        extraction_warnings=warnings,
        storage_path=str(storage_path.relative_to(settings.root_dir)),
        uploaded_by=uploaded_by,
    )
    session.add(artifact)
    session.flush()


    audit_service.log(
        session,
        action="source.upload",
        entity_type="source_artifact",
        entity_id=artifact.artifact_id,
        who=uploaded_by,
        note={
            "filename": filename,
            "size": len(raw),
            "quality": res.quality_score,
            "warnings": warnings,
        },
    )
    return artifact, True


def _guess_mime(filename: str) -> str:
    s = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "md": "text/markdown",
    }.get(s, "application/octet-stream")


def _write_jsonl(
    *,
    storage_path: Path,
    extracted_text: str,
    base_metadata: dict,
) -> tuple[bool, Optional[str], Optional[str]]:
    try:
        chunks = chunk_text(extracted_text)
        if not chunks:
            return False, None, "no_chunks"

        jsonl_path = storage_path.with_suffix(".jsonl")
        with jsonl_path.open("w", encoding="utf-8") as f:
            for ch in chunks:
                meta = dict(base_metadata)
                meta.update({
                    "chunk_id": ch.chunk_id,
                    "char_start": ch.char_start,
                    "char_end": ch.char_end,
                })
                f.write(json.dumps({"text": ch.text, "metadata": meta}, ensure_ascii=False) + "\n")

        rel = str(jsonl_path.relative_to(settings.root_dir))
        return True, rel, None
    except Exception as e:
        return False, None, str(e)[:200]
