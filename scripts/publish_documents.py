"""data/documents/*.txt|*.md 를 DB publish 파이프라인으로 일괄 적재.

경로: SourceArtifact → create_draft_from_artifact(draft) → validated →
      publish_version(Qdrant 인덱싱, build_index_chunks 경유 → normalizer 적용)

특징:
- 임베디드 Qdrant 단일 점유 문제 회피: 실행 전 백엔드(uvicorn)를 멈춰둘 것.
- 시작 시 Qdrant 컬렉션을 리셋(delete_collection) → 중복 청크 방지.
- content_hash 기준 멱등: 같은 파일 재실행 시 skipping.
- '통영다락방' 테스트 파일은 제외. 이미 게시된 테스트 문서는 archived 처리(인덱스 오염 방지).
- RAG_BILINGUAL_ENABLED=false 로 실행 → enhanced_rag(중국어) 중복 저장 방지.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
from pathlib import Path

# 백엔드 임포트 전에 env 오버라이드 (pydantic settings 는 env 를 우선)
os.environ.setdefault("RAG_BILINGUAL_ENABLED", "false")
# 시드 적재는 LLM 스테이지(구조화/맥락강화) 비활성 → 속도·오프라인 안정성.
# (baseline 은 검색 정확도 측정 목적이므로 정규화+청킹만으로 충분)
os.environ.setdefault("INGEST_RESTRUCTURE_ENABLED", "false")
os.environ.setdefault("INGEST_CONTEXTUAL_ENABLED", "false")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed")

from backend.app.config import settings
from backend.app.db import get_session
from backend.app.models.orm import (
    DocVersionState,
    Document,
    DocumentVersion,
    SourceArtifact,
)
from backend.app.services.document_service import create_draft_from_artifact
from backend.app.services.publish_service import publish_version
from backend.app.services.embedding.factory import get_embedder
from backend.app.services.vector_store import QdrantStore

_TEXT_SUFFIXES = {".txt", ".md"}
_TEST_MARKERS = ("통영다락방",)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mime(suffix: str) -> str:
    return "text/markdown" if suffix.lower() == ".md" else "text/plain"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="시작 시 Qdrant 컬렉션 리셋(기존 청크 전체 삭제). "
                         "이미 게시된 문서는 보존하려면 사용하지 마세요.")
    ap.add_argument("--limit", type=int, default=0,
                    help="최대 게시(doc) 수 (0=제한없음). 분할 실행용 — skip 은 문턱 미소모.")
    args = ap.parse_args()

    doc_dir = ROOT / settings.data_dir
    files = sorted(
        p for p in doc_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES
        and not any(m in p.name for m in _TEST_MARKERS)
    )
    logger.info("[seed] 대상 파일 %d개: %s", len(files), doc_dir)

    # 1) Qdrant 리셋 (--reset 시에만. 중복 청크 방지용. 재실행 시 보존 목적 비활성)
    if args.reset:
        embedder = get_embedder(settings.embedder)
        store = QdrantStore(settings.embedder, dim=embedder.dim)
        try:
            store.delete_collection()
            logger.info("[seed] Qdrant 컬렉션 리셋 완료: %s", store.collection)
        except Exception as e:
            logger.warning("[seed] Qdrant 리셋 실패(무시): %s", e)

    published = 0
    skipped = 0
    with get_session() as session:
        for path in files:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
            if len(raw) < 50:
                logger.info("[skip] 너무 짧음: %s", path.name)
                skipped += 1
                continue

            h = _sha256(raw)
            # 멱등: 같은 본문의 artifact 가 이미 있으면 skip
            if session.query(SourceArtifact).filter(SourceArtifact.content_hash == h).first():
                logger.info("[skip] 이미 적재됨(hash): %s", path.name)
                skipped += 1
                continue
            # 이미 게시된 동일 제목 문서가 있으면 skip
            title = path.stem
            if session.query(DocumentVersion).filter(
                DocumentVersion.title == title,
                DocumentVersion.state == DocVersionState.published.value,
            ).first():
                logger.info("[skip] 이미 게시됨(title): %s", path.name)
                skipped += 1
                continue

            artifact = SourceArtifact(
                original_filename=path.name,
                content_hash=h,
                mime_type=_mime(path.suffix),
                size_bytes=len(raw.encode("utf-8")),
                extracted_text=raw,
                storage_path=str(path),
                uploaded_by="seed",
            )
            session.add(artifact)
            session.flush()

            version = create_draft_from_artifact(
                session,
                artifact=artifact,
                title=title,
                doc_type="sermon",
                topic_tags=["설교"],
                who="seed",
            )
            # 체크리스트 우회 → validated 직접 전환
            version.state = DocVersionState.validated.value
            session.flush()

            publish_version(session, version=version, who="seed")
            session.commit()
            published += 1
            logger.info("[ok] 게시 완료 (%d/%d): %s", published, len(files), path.name)
            if args.limit and published >= args.limit:
                logger.info("[seed] --limit %d 도달, 조기 종료", args.limit)
                break

        # 2) 기존 테스트 게시 문서 archived 처리 (인덱스 오염 방지)
        #    '%테스트%' 외에 실제 테스트 픽스처(통영다락방 등) 마커도 포함.
        from sqlalchemy import or_
        _marker_filters = [DocumentVersion.title.like(f"%{m}%") for m in _TEST_MARKERS]
        _marker_filters.append(DocumentVersion.title.like("%테스트%"))
        test_versions = session.query(DocumentVersion).filter(
            DocumentVersion.state == DocVersionState.published.value,
            or_(*_marker_filters),
        ).all()
        for tv in test_versions:
            tv.state = DocVersionState.archived.value
        if test_versions:
            session.commit()
            logger.info("[seed] 테스트 게시 문서 %d개 archived 처리", len(test_versions))

    logger.info("[seed] 완료 — published=%d skipped=%d", published, skipped)


if __name__ == "__main__":
    main()
