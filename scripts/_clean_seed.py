"""시드 partial 상태 정리: 기존 시드 데이터 + Qdrant 리셋 + 테스트 문서 archived.

publish_documents.py 가 artifact 는 커밋했으나 publish(Qdrant) 실패해
'hash skip' 이 영구화되는 상황을 해결하기 위해, 실제 설교 시드 데이터를
모두 삭제하고 Qdrant 를 비운 뒤 깨끗한 상태로 재시도한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings
from backend.app.db import get_session
from backend.app.models.orm import (
    DocVersionState,
    Document,
    DocumentVersion,
    IndexSnapshot,
    SourceArtifact,
)
from backend.app.services.embedding.factory import get_embedder
from backend.app.services.vector_store import QdrantStore

ROOT = Path(__file__).resolve().parents[1]
_TEST_MARKERS = ("통영다락방",)


def main():
    doc_dir = ROOT / settings.data_dir
    stems = {
        p.stem
        for p in doc_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".txt", ".md"}
        and not any(m in p.name for m in _TEST_MARKERS)
    }

    with get_session() as s:
        # 1) 실제 설교 버전/문서 삭제
        versions = (
            s.query(DocumentVersion)
            .filter(DocumentVersion.title.in_(stems))
            .all()
        )
        vids = [v.version_id for v in versions]
        doc_ids = {v.doc_id for v in versions}
        if vids:
            s.query(IndexSnapshot).filter(IndexSnapshot.version_id.in_(vids)).delete(
                synchronize_session=False
            )
            s.query(DocumentVersion).filter(
                DocumentVersion.version_id.in_(vids)
            ).delete(synchronize_session=False)
        if doc_ids:
            s.query(Document).filter(Document.doc_id.in_(doc_ids)).delete(
                synchronize_session=False
            )
        # 2) 시드 artifact 삭제
        s.query(SourceArtifact).filter(SourceArtifact.uploaded_by == "seed").delete(
            synchronize_session=False
        )
        # 3) 테스트 게시 문서 archived (인덱스 오염 방지, 비파괴)
        #    '%테스트%' 외에 실제 테스트 픽스처(통영다락방 등) 마커도 포함.
        from sqlalchemy import or_
        _marker_filters = [DocumentVersion.title.like(f"%{m}%") for m in _TEST_MARKERS]
        _marker_filters.append(DocumentVersion.title.like("%테스트%"))
        tv = (
            s.query(DocumentVersion)
            .filter(
                DocumentVersion.state == DocVersionState.published.value,
                or_(*_marker_filters),
            )
            .all()
        )
        for v in tv:
            v.state = DocVersionState.archived.value
        s.commit()
        print(f"deleted real-sermon versions={len(versions)} artifacts(seed) cleared, "
              f"test docs archived={len(tv)}")

    # 4) Qdrant 리셋
    embedder = get_embedder(settings.embedder)
    store = QdrantStore(settings.embedder, dim=embedder.dim)
    try:
        store.delete_collection()
        print("Qdrant reset:", store.collection)
    except Exception as e:
        print("Qdrant reset skip:", e)


if __name__ == "__main__":
    main()
