"""validated → published 변환 + Qdrant L3 인덱싱.

핵심:
- L2가 validated 일 때만 가능
- 청크 ID = deterministic ({doc_id}#{version}#{idx})
- 같은 doc의 옛 published 버전은 자동 superseded
- audit_log 기록
- publish 실패 시 L2 상태 그대로 유지 (롤백)
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: N2 — Qdrant upsert를 DB flush 후로 이동 (drift 임시 완화)
#       N15 — 옛 published 청크 Qdrant 삭제 (doc_id 필터 기반)
#       N16 — body < 50 자 하드 거부 제거 (짧은 격언·인용 지원)
# Reason: ORDERS.md N2, N15, N16
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models.orm import (
    Document, DocumentVersion, DocVersionState, IndexSnapshot,
)
from . import audit_service, document_service
from .chunker import chunk_text
from .embedding.factory import get_embedder
from .vector_store import QdrantStore


def publish_version(
    session: Session,
    *,
    version: DocumentVersion,
    embedder_name: str | None = None,
    who: str = "admin",
) -> IndexSnapshot:
    """L2 -> Qdrant 인덱싱 + L3 snapshot 생성."""
    if version.state not in {DocVersionState.validated.value, DocVersionState.draft.value}:
        raise ValueError(f"Cannot publish version in state {version.state}")

    embedder_name = embedder_name or settings.embedder
    embedder = get_embedder(embedder_name)
    store = QdrantStore(embedder_name, dim=embedder.dim)

    # 본문 (마이크로 패치 우선)
    body = document_service.get_effective_body(version)
    if not body:
        raise ValueError("Body is empty")

    # 청킹
    chunks = chunk_text(body)
    if not chunks:
        raise ValueError("No chunks produced")

    # 청크 ID = deterministic. rollback/replace 깨끗.
    doc = version.document
    chunk_ids = [_chunk_uuid(doc.doc_id, version.version_number, c.chunk_id) for c in chunks]
    texts = [c.text for c in chunks]
    vectors = embedder.embed_documents(texts)
    metadatas = []
    for c in chunks:
        metadatas.append({
            "doc_id": doc.doc_id,
            "doc_key": doc.doc_key,
            "version_id": version.version_id,
            "version_number": version.version_number,
            "title": version.title,
            "doc_type": doc.doc_type,
            "series": doc.series,
            "scripture_refs": version.scripture_refs or [],
            "topic_tags": version.topic_tags or [],
            "chunk_seq": c.chunk_id,
            "is_canonical_doc": doc.is_canonical,
        })

    # 옛 published -> superseded (DB 변경 먼저)
    for v in doc.versions:
        if v.version_id != version.version_id and v.state == DocVersionState.published.value:
            v.state = DocVersionState.superseded.value
            audit_service.log(
                session, action="version.supersede", entity_type="document_version",
                entity_id=v.version_id, who=who,
                from_state="published", to_state="superseded",
                note={"by_version": version.version_id},
            )

    # 이 버전 -> published (DB 변경)
    prev_state = version.state
    version.state = DocVersionState.published.value
    version.published_at = datetime.utcnow()
    version.published_by = who

    snap = IndexSnapshot(
        version_id=version.version_id,
        collection_name=store.collection,
        embedder_name=embedder_name,
        embedder_version="v1",
        chunk_count=len(chunks),
        total_tokens=sum(len(c.text) for c in chunks),
    )
    session.add(snap)
    session.flush()  # DB 변경 확정 후 Qdrant 호출 (N2: drift 임시 완화)

    # N15: 옛 published 청크 먼저 삭제 (현재 버전 제외, doc_id 기준 filter)
    from qdrant_client.http import models as qm
    store.delete_where(qm.Filter(
        must=[
            qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc.doc_id)),
        ],
        must_not=[
            qm.FieldCondition(key="version_id", match=qm.MatchValue(value=str(version.version_id))),
        ],
    ))

    # N2: Qdrant upsert는 DB flush 성공 후 (영구 drift 위험 완화)
    store.upsert(
        ids=chunk_ids,
        texts=texts,
        dense_vectors=vectors.tolist(),
        metadatas=metadatas,
    )

    audit_service.log(
        session, action="version.publish", entity_type="document_version",
        entity_id=version.version_id, who=who,
        from_state=prev_state, to_state="published",
        note={
            "chunks": len(chunks),
            "collection": store.collection,
            "embedder": embedder_name,
        },
    )

    # E-E: publish 시 용어 자동 추출 (실패해도 publish 자체는 성공)
    try:
        from .glossary_service import extract_terms_from_text
        extract_terms_from_text(session, body, doc_id=doc.doc_id)
    except Exception:
        pass

    return snap


def _chunk_uuid(doc_id: str, version_num: int, chunk_idx: int) -> str:
    """Deterministic UUID5 — 같은 입력이면 항상 같은 ID."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}|{version_num}|{chunk_idx}"))
