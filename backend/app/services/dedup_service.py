"""Dedup service - 중복 자료 자동 감지.

3단계 신호:
  1) content_hash 완전 일치  -> identical (즉시 차단 추천)
  2) 같은 doc_key            -> version (같은 자료의 새 버전)
  3) 제목 + 추출텍스트 앞부분 유사 -> similar (정황)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..models.orm import SourceArtifact, Document, DocumentVersion


@dataclass
class DupHit:
    kind: str             # "identical" | "version" | "similar"
    doc_id: Optional[str]
    doc_key: Optional[str]
    title: str
    reason: str           # 사람에게 설명할 한국어 문구


def _norm_title(t: str) -> str:
    return "".join(c.lower() for c in (t or "") if c.isalnum() or 0xAC00 <= ord(c) <= 0xD7A3)


def check_on_upload(
    session: Session,
    *,
    content_hash: str,
    proposed_title: str,
    extracted_head: str,
) -> list[DupHit]:
    hits: list[DupHit] = []

    # 1) 동일 해시 -> 운영자가 이미 올린 파일
    existing = session.query(SourceArtifact).filter(
        SourceArtifact.content_hash == content_hash
    ).first()
    if existing:
        # 그 artifact 로 만들어진 doc/version 찾기
        v = session.query(DocumentVersion).filter(
            DocumentVersion.artifact_id == existing.artifact_id
        ).order_by(DocumentVersion.version_number.desc()).first()
        if v:
            hits.append(DupHit(
                kind="identical",
                doc_id=v.doc_id,
                doc_key=v.document.doc_key,
                title=v.title,
                reason="완전히 같은 파일이 이미 올라가 있습니다 (해시 일치).",
            ))

    # 2) 같은 제목 -> 새 버전 후보
    nt = _norm_title(proposed_title)
    if nt:
        candidates = session.query(DocumentVersion).all()
        seen_docs = set()
        for v in candidates:
            if v.doc_id in seen_docs:
                continue
            if _norm_title(v.title) == nt and not any(h.doc_id == v.doc_id for h in hits):
                seen_docs.add(v.doc_id)
                hits.append(DupHit(
                    kind="version",
                    doc_id=v.doc_id,
                    doc_key=v.document.doc_key,
                    title=v.title,
                    reason=f"같은 제목의 자료가 이미 있습니다 (v{v.version_number}). 새 버전으로 추가하시겠어요?",
                ))

    # 3) 본문 앞부분 유사 (간단 substring) -> 유사 자료
    if extracted_head and len(extracted_head) >= 100:
        head_key = extracted_head[:200]
        rows = session.query(SourceArtifact).all()
        for art in rows:
            if art.content_hash == content_hash:
                continue
            ex = art.extracted_text or ""
            if not ex:
                continue
            if head_key[:100] in ex[:1000]:
                v = session.query(DocumentVersion).filter(
                    DocumentVersion.artifact_id == art.artifact_id
                ).first()
                if v and not any(h.doc_id == v.doc_id for h in hits):
                    hits.append(DupHit(
                        kind="similar",
                        doc_id=v.doc_id,
                        doc_key=v.document.doc_key,
                        title=v.title,
                        reason="본문의 앞부분이 비슷합니다. 같은 자료의 다른 형식일 수 있어요.",
                    ))

    return hits


def to_dict(hit: DupHit) -> dict:
    return {
        "kind": hit.kind,
        "doc_id": hit.doc_id,
        "doc_key": hit.doc_key,
        "title": hit.title,
        "reason": hit.reason,
    }
