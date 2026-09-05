"""validated → published 변환 + Qdrant L3 인덱싱.

핵심:
- L2가 validated 일 때만 가능
- 청크 ID = deterministic ({doc_id}#{version}#{idx})
- 같은 doc의 옛 published 버전은 자동 superseded
- audit_log 기록
- publish 실패 시 L2 상태 그대로 유지 (롤백)

progress_cb(current, total, detail) — 임베딩 배치 완료 시마다 호출.
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
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np

from sqlalchemy.orm import Session

from ..config import settings
from ..models.orm import (
    DocumentVersion, DocVersionState, IndexSnapshot,
)
from . import audit_service, document_service
from .embedding.factory import get_embedder
from .vector_store import QdrantStore

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[int, int, str], None]]

_EMBED_BATCH = 10   # 한 번에 임베딩할 청크 수 (진행바 세분화용)


def _ingest_to_enhanced_rag(version: "DocumentVersion") -> None:
    """발행된 문서를 enhanced_rag 이중 저장 컬렉션에 인제스트.

    실패해도 publish 자체는 성공하도록 예외를 삼켜다(graceful degradation).
    본문이 너무 짧으면 인제스트하지 않는다.
    """
    # 이중 저장(enhanced_rag)은 중국어 우선 bilingual 모드에서만 의미가 있음.
    # rag_bilingual_enabled 가 꺼져 있으면 표준 단일언어 경로이므로 스킵
    # (bge-m3 등 중국어 임베더 로드 시도/오류 · 불필요한 2중 컬렉션 저장 방지).
    if not settings.rag_bilingual_enabled:
        return
    try:
        from .enhanced_rag import get_pipeline
        from .enhanced_rag.types import RAGDocument

        body = document_service.get_effective_body(version)
        if not body or len(body.strip()) < 50:
            return
        doc = version.document
        rag_pipeline = get_pipeline()
        rag_doc = RAGDocument(
            doc_id=f"{version.doc_id}#v{version.version_number}",
            title=version.title or "",
            source=doc.doc_key or doc.doc_type or "sermon",
            content=body,
            metadata={
                "doc_type": doc.doc_type,
                "scripture_refs": version.scripture_refs or [],
                "topic_tags": version.topic_tags or [],
            },
        )
        rag_pipeline.add_document(rag_doc)
        logger.info("[publish] enhanced_rag 이중 저장 완료: %s", rag_doc.doc_id)
    except Exception as exc:
        logger.warning("[publish] enhanced_rag 인제스트 실패 (폴백): %s", exc)


def publish_version(
    session: Session,
    *,
    version: DocumentVersion,
    embedder_name: str | None = None,
    who: str = "admin",
    progress_cb: ProgressCb = None,
) -> IndexSnapshot:
    """L2 -> Qdrant 인덱싱 + L3 snapshot 생성."""
    if version.state != DocVersionState.validated.value:
        raise ValueError(f"Cannot publish version in state {version.state} — validated 상태만 게시 가능")

    embedder_name = embedder_name or settings.embedder
    embedder = get_embedder(embedder_name)
    store = QdrantStore(embedder_name, dim=embedder.dim)

    # 본문 (마이크로 패치 우선)
    body = document_service.get_effective_body(version, session=session)
    if not body:
        raise ValueError("Body is empty")

    # ⚡ INGEST 파이프라인 (Stage 1~7): 정규화→구조화→청킹→메타추출→품질게이트→컨텍스트
    #   각 단계는 settings.ingest_*_enabled 로 ON/OFF. publish_service 는 결과만 인덱싱.
    from .ingest_pipeline import build_index_chunks
    ingest = build_index_chunks(body, title=version.title)

    if ingest.blocked:
        raise ValueError(
            "품질 게이트 차단: " + "; ".join(ingest.warnings[:5]) or "인덱싱 불가 청크"
        )

    chunks = ingest.chunks
    if not chunks:
        raise ValueError("No chunks produced")

    # 메타데이터 자동 보강 (관리자가 CSV로 직접 입력한 값은 우선 보존)
    if not (version.scripture_refs or []) and ingest.scripture_refs:
        version.scripture_refs = ingest.scripture_refs
    if not (version.topic_tags or []) and ingest.topic_tags:
        version.topic_tags = ingest.topic_tags
    # 구조화 산출물 보존 (있으면) — 재발행·디버깅용
    if ingest.structured_body and hasattr(version, "structured_body"):
        version.structured_body = ingest.structured_body

    # 청크 ID = deterministic. rollback/replace 깨끗.
    doc = version.document
    chunk_ids = [_chunk_uuid(doc.doc_id, version.version_number, c.chunk_id) for c in chunks]
    texts = [c.text for c in chunks]                 # 표시용 (사용자/LLM)
    embed_texts = ingest.embed_texts                  # 임베딩용 (맥락 포함 가능)

    # 배치 임베딩 (진행 콜백 지원) — embed_texts 로 벡터화
    total = len(embed_texts)
    if progress_cb:
        progress_cb(0, total, f"0/{total} 청크 임베딩 시작")

    all_vectors: list = []
    for batch_start in range(0, total, _EMBED_BATCH):
        batch_texts = embed_texts[batch_start: batch_start + _EMBED_BATCH]
        batch_vecs = embedder.embed_documents(batch_texts)
        # embed_documents 는 numpy 배열 또는 리스트 반환 — 통일
        if hasattr(batch_vecs, "tolist"):
            all_vectors.extend(batch_vecs.tolist())
        else:
            all_vectors.extend(batch_vecs)
        done = min(batch_start + _EMBED_BATCH, total)
        if progress_cb:
            progress_cb(done, total, f"{done}/{total} 청크 임베딩 완료")

    vectors = np.array(all_vectors)

    metadatas = []
    for i, c in enumerate(chunks):
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
            # INGEST 신규 payload — 검색 품질·디버깅
            "section_title": c.section_title,
            "token_estimate": c.token_estimate,
            "context_prefix": ingest.context_prefixes[i] if i < len(ingest.context_prefixes) else "",
            # 구원·다락방 메타데이터 — retriever boost matrix (D-C16)용
            "target_salvation_stage": version.target_salvation_stage or [],
            "darakbang_tier": version.darakbang_tier,
            "salvation_focus_score": version.salvation_focus_score,
            "gospel_core_tag": version.gospel_core_tag or False,
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
    version.published_at = datetime.now(timezone.utc)
    version.published_by = who

    snap = IndexSnapshot(
        version_id=version.version_id,
        collection_name=store.collection,
        embedder_name=embedder_name,
        embedder_version="v1",
        chunk_count=len(chunks),
        total_tokens=sum(c.token_estimate for c in chunks),
    )
    session.add(snap)
    session.flush()  # DB 변경 확정 후 Qdrant 호출 (N2: drift 임시 완화)

    from qdrant_client.http import models as qm

    # N2: Qdrant upsert는 DB flush 성공 후 (영구 drift 위험 완화)
    store.upsert(
        ids=chunk_ids,
        texts=texts,
        dense_vecs=vectors.tolist(),
        metadatas=metadatas,
    )

    # N15: 옛 published 청크 삭제 (현재 버전 제외, doc_id 기준 filter)
    store.delete_where(qm.Filter(
        must=[
            qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc.doc_id)),
        ],
        must_not=[
            qm.FieldCondition(key="version_id", match=qm.MatchValue(value=str(version.version_id))),
        ],
    ))

    # V2: 자체 BM25 sparse 인덱스에도 반영 (embedded 하이브리드 검색)
    try:
        from .sparse_index import get_index
        bm25 = get_index(store.collection)
        # 옛 버전 청크 제거 (같은 doc_id, 다른 version_id)
        _vid = str(version.version_id)
        bm25.remove_by(lambda pl: pl.get("doc_id") == doc.doc_id and str(pl.get("version_id")) != _vid)
        bm25.add_batch([
            (cid, txt, dict(meta, text=txt))
            for cid, txt, meta in zip(chunk_ids, texts, metadatas)
        ])
    except Exception as _e:
        logger.warning(
            "[publish] BM25 sparse 인덱스 갱신 실패 — 하이브리드 검색 정확도 저하 가능: %s",
            _e,
            exc_info=True,
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

    # 작업 H: enhanced_rag 이중 저장 인제스트 (실패해도 publish 자체는 성공)
    try:
        _ingest_to_enhanced_rag(version)
    except Exception as exc:
        logger.warning("[publish] enhanced_rag 인제스트 호출 실패 (무시): %s", exc)

    return snap


def _chunk_uuid(doc_id: str, version_num: int, chunk_idx: int) -> str:
    """Deterministic UUID5 — 같은 입력이면 항상 같은 ID."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}|{version_num}|{chunk_idx}"))


def prepare_publish(session: Session, *, version: DocumentVersion) -> dict:
    """Publish Phase 1: 청킹 + 품질게이트 (세션 내, 임베딩 전).

    publish-async 전용. 세션 밖에서 임베딩할 수 있도록 중간 데이터를 반환.
    """
    body = document_service.get_effective_body(version)
    if not body:
        raise ValueError("Body is empty")

    from .ingest_pipeline import build_index_chunks
    ingest = build_index_chunks(body, title=version.title)

    if ingest.blocked:
        raise ValueError(
            "품질 게이트 차단: " + "; ".join(ingest.warnings[:5]) or "인덱싱 불가 청크"
        )

    if not ingest.chunks:
        raise ValueError("No chunks produced")

    # 메타데이터 자동 보강
    if not (version.scripture_refs or []) and ingest.scripture_refs:
        version.scripture_refs = ingest.scripture_refs
    if not (version.topic_tags or []) and ingest.topic_tags:
        version.topic_tags = ingest.topic_tags

    doc = version.document
    chunk_ids = [_chunk_uuid(doc.doc_id, version.version_number, c.chunk_id)
                 for c in ingest.chunks]
    texts = [c.text for c in ingest.chunks]

    return {
        "chunks": ingest.chunks,
        "embed_texts": ingest.embed_texts,
        "context_prefixes": ingest.context_prefixes,
        "chunk_ids": chunk_ids,
        "texts": texts,
        "doc_id": doc.doc_id,
        "doc_key": doc.doc_key,
        "version_id": version.version_id,
        "version_number": version.version_number,
        "title": version.title,
        "doc_type": doc.doc_type,
        "series": doc.series,
        "scripture_refs": version.scripture_refs or [],
        "topic_tags": version.topic_tags or [],
        "is_canonical": doc.is_canonical,
        "target_salvation_stage": version.target_salvation_stage or [],
        "darakbang_tier": version.darakbang_tier,
        "salvation_focus_score": version.salvation_focus_score,
        "gospel_core_tag": version.gospel_core_tag or False,
    }


def finalize_publish(
    session: Session,
    *,
    version_id: str,
    prep: dict,
    vectors: list,
    embedder_name: str,
    who: str = "admin",
) -> IndexSnapshot:
    """Publish Phase 3: DB 업데이트 + Qdrant upsert (세션 내, 임베딩 후).

    publish-async 전용. prep 은 prepare_publish() 의 반환값.
    """
    from qdrant_client.http import models as qm

    version = document_service.get_version(session, version_id)
    if not version:
        raise ValueError("version not found")
    doc = version.document

    embedder = get_embedder(embedder_name)
    store = QdrantStore(embedder_name, dim=embedder.dim)

    import numpy as np
    vectors_np = np.array(vectors)

    # 메타데이터 구성
    chunks = prep["chunks"]
    chunk_ids = prep["chunk_ids"]
    texts = prep["texts"]
    context_prefixes = prep["context_prefixes"]

    metadatas = []
    for i, c in enumerate(chunks):
        metadatas.append({
            "doc_id": prep["doc_id"],
            "doc_key": prep["doc_key"],
            "version_id": prep["version_id"],
            "version_number": prep["version_number"],
            "title": prep["title"],
            "doc_type": prep["doc_type"],
            "series": prep["series"],
            "scripture_refs": prep["scripture_refs"],
            "topic_tags": prep["topic_tags"],
            "chunk_seq": c.chunk_id,
            "is_canonical_doc": prep["is_canonical"],
            "section_title": c.section_title,
            "token_estimate": c.token_estimate,
            "context_prefix": context_prefixes[i] if i < len(context_prefixes) else "",
            "target_salvation_stage": prep["target_salvation_stage"],
            "darakbang_tier": prep["darakbang_tier"],
            "salvation_focus_score": prep["salvation_focus_score"],
            "gospel_core_tag": prep["gospel_core_tag"],
        })

    # 옛 published → superseded
    for v in doc.versions:
        if v.version_id != version.version_id and v.state == DocVersionState.published.value:
            prev_st = v.state
            v.state = DocVersionState.superseded.value
            audit_service.log(
                session, action="version.supersede", entity_type="document_version",
                entity_id=v.version_id, who=who,
                from_state=prev_st, to_state="superseded",
                note={"by_version": version.version_id},
            )

    # 이 버전 → published
    prev_state = version.state
    version.state = DocVersionState.published.value
    version.published_at = datetime.now(timezone.utc)
    version.published_by = who

    snap = IndexSnapshot(
        version_id=version.version_id,
        collection_name=store.collection,
        embedder_name=embedder_name,
        embedder_version="v1",
        chunk_count=len(chunks),
        total_tokens=sum(c.token_estimate for c in chunks),
    )
    session.add(snap)
    session.flush()

    # Qdrant upsert
    store.upsert(
        ids=chunk_ids,
        texts=texts,
        dense_vecs=vectors_np.tolist(),
        metadatas=metadatas,
    )

    # 옛 Qdrant 청크 삭제
    store.delete_where(qm.Filter(
        must=[
            qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc.doc_id)),
        ],
        must_not=[
            qm.FieldCondition(key="version_id", match=qm.MatchValue(value=str(version.version_id))),
        ],
    ))

    # BM25 sparse 인덱스
    try:
        from .sparse_index import get_index
        bm25 = get_index(store.collection)
        _vid = str(version.version_id)
        bm25.remove_by(lambda pl: pl.get("doc_id") == doc.doc_id
                       and str(pl.get("version_id")) != _vid)
        bm25.add_batch([
            (cid, txt, dict(meta, text=txt))
            for cid, txt, meta in zip(chunk_ids, texts, metadatas)
        ])
    except Exception as _e:
        logger.warning(
            "[publish] BM25 sparse 인덱스 갱신 실패 — 하이브리드 검색 정확도 저하 가능: %s",
            _e,
            exc_info=True,
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

    # 작업 H: enhanced_rag 이중 저장 인제스트 (실패해도 publish 자체는 성공)
    try:
        _ingest_to_enhanced_rag(version)
    except Exception as exc:
        logger.warning("[publish] enhanced_rag 인제스트 호출 실패 (무시): %s", exc)

    return snap
