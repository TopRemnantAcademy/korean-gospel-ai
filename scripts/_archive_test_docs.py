"""게시 코퍼스에서 테스트 문서만 archived 처리 (실서문 보존).

- _clean_seed.py / publish_documents.py 가 '%테스트%' 만으로는 놓치는
  실제 테스트 픽스처(통영다락방 등)를 마커 기반으로 아카이브.
- published/superseded 상태인 DB 행만 state=archived 로 변경 (비파괴).
- 해당 문서의 Qdrant 청크도 함께 제거 (인덱스 오염 방지, 없으면 no-op).
- 실서문(sermon) 데이터는 절대 건드리지 않음.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import or_

from backend.app.config import settings
from backend.app.db import get_session
from backend.app.models.orm import DocVersionState, DocumentVersion
from backend.app.services.embedding.factory import get_embedder
from backend.app.services.vector_store import QdrantStore

_TEST_MARKERS = ("통영다락방",)


def _title_filters():
    f = [DocumentVersion.title.like(f"%{m}%") for m in _TEST_MARKERS]
    f.append(DocumentVersion.title.like("%테스트%"))
    return f


def main():
    with get_session() as s:
        versions = (
            s.query(DocumentVersion)
            .filter(
                DocumentVersion.state.in_(
                    [DocVersionState.published.value, DocVersionState.superseded.value]
                ),
                or_(*_title_filters()),
            )
            .all()
        )
        if not versions:
            print("archived 대상 테스트 문서 없음 (이미 정리됨)")
            return

        for v in versions:
            v.state = DocVersionState.archived.value
        s.commit()
        print(f"archived 테스트 문서 {len(versions)}개: {[v.title for v in versions]}")
        doc_ids = sorted({v.doc_id for v in versions})

    # Qdrant 청크 제거 (인덱스 오염 방지)
    try:
        embedder = get_embedder(settings.embedder)
        store = QdrantStore(settings.embedder, dim=embedder.dim)
        from qdrant_client.http import models as qm
        for did in doc_ids:
            store.delete_where(
                qm.Filter(
                    must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=did))]
                )
            )
        print(f"Qdrant 청크 제거 완료: {len(doc_ids)} doc")
    except Exception as e:
        print("Qdrant 청크 제거 스킵(무해):", e)


if __name__ == "__main__":
    main()
