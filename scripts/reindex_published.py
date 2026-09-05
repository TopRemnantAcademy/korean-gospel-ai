"""발행(published) 문서를 메인 컬렉션(gospel_kure)에 재인덱싱.

P1(Kiwi 정제) 적용 후 기존 청크를 갱신하기 위함.
- build_index_chunks 를 경유하므로 normalizer.normalize_text + chunk_text 가 적용됨(ingest_pipeline:81).
  → `scripts/index_sermons.py` 는 normalize_text 를 안 쓰므로 P1 재인덱스에 부적합.
- doc_id 메타데이터로 기존 청크를 delete_where 로 교체(증분, 멱등).
- ⚠️ 기존 인덱스가 doc_id 메타를 안 가졌다면 교체가 안 돼 중복될 수 있음 → 최초 1회는 --reset 로 전체 클린 재인덱스 권장.

실행:
    python scripts/reindex_published.py --limit 3     # 소량 점진 테스트
    python scripts/reindex_published.py --reset        # 전체 컬렉션 초기화 후 전체 재인덱스(권장 최초 1회)
    python scripts/reindex_published.py                # 전체 점진 재인덱스
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.db import get_session  # noqa: E402
from backend.app.models.orm import DocumentVersion, DocVersionState  # noqa: E402
from backend.app.services.document_service import get_effective_body  # noqa: E402
from backend.app.services.ingest_pipeline import build_index_chunks  # noqa: E402
from backend.app.services.embedding.factory import get_embedder  # noqa: E402
from backend.app.services.vector_store import QdrantStore  # noqa: E402


def _chunk_uuid(doc_id: str, version_number: int, chunk_seq: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"doc:{doc_id}:v{version_number}:{chunk_seq}"))


def reindex_all(*, limit: int, reset: bool) -> int:
    embedder = get_embedder(settings.embedder)
    store = QdrantStore(settings.embedder, dim=embedder.dim)

    if reset:
        print(f"[reset] 컬렉션 '{store.collection}' 삭제 후 전체 재구축")
        store.delete_collection()

    with get_session() as s:
        versions = (
            s.query(DocumentVersion)
            .filter(DocumentVersion.state == DocVersionState.published.value)
            .all()
        )
        total = len(versions)
        if limit > 0:
            versions = versions[:limit]
        print(f"재인덱스 대상(published): 전체 {total}개 / 이번 실행 {len(versions)}개")

        if not versions:
            print("재인덱스할 문서가 없습니다.")
            return 0

        ok = skip = err = 0
        t0 = time.perf_counter()
        for idx, v in enumerate(versions, 1):
            doc = v.document
            body = get_effective_body(v)
            if not body or len(body.strip()) < 50:
                print(f"  [{idx}/{len(versions)}] ⏭️ 본문 부족: {v.doc_id}#v{v.version_number}")
                skip += 1
                continue
            try:
                res = build_index_chunks(body, title=v.title or "")
                if res.blocked or not res.chunks:
                    print(f"  [{idx}/{len(versions)}] ⏭️ 청킹 차단/빈: {v.doc_id}#v{v.version_number}")
                    skip += 1
                    continue

                embed_texts = res.embed_texts if res.embed_texts else [c.text for c in res.chunks]
                vectors = embedder.embed_documents(embed_texts)

                ids = [_chunk_uuid(v.doc_id, v.version_number, c.chunk_id) for c in res.chunks]
                texts = [c.text for c in res.chunks]
                metadatas = []
                for c in res.chunks:
                    metadatas.append(
                        {
                            "doc_id": v.doc_id,
                            "version_number": v.version_number,
                            "title": v.title or "",
                            "doc_type": doc.doc_type if doc else "sermon",
                            "chunk_seq": c.chunk_id,
                            "section_title": c.section_title,
                            "scripture_refs": res.scripture_refs or [],
                            "topic_tags": res.topic_tags or [],
                        }
                    )

                # 기존 청크 교체(동일 doc_id). --reset 이 아닐 때만 증분 교체.
                if not reset:
                    store.delete_where(
                        Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=v.doc_id))])
                    )
                store.upsert(ids=ids, texts=texts, dense_vecs=vectors.tolist(), metadatas=metadatas)

                ok += 1
                print(f"  [{idx}/{len(versions)}] ✅ {v.doc_id}#v{v.version_number} ({len(res.chunks)}청크)")
            except Exception as exc:
                err += 1
                print(f"  [{idx}/{len(versions)}] ⚠️ {v.doc_id}#v{v.version_number}: {exc}")

        elapsed = time.perf_counter() - t0
        print(f"재인덱스 완료 — 성공 {ok} / 건너뜀 {skip} / 실패 {err} (소요 {elapsed:.1f}s)")
        return 0 if err == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="published 문서를 메인 컬렉션에 재인덱싱")
    parser.add_argument("--limit", type=int, default=0, help="처리할 최대 문서 수 (0=전체, --reset 미설정 시)")
    parser.add_argument("--reset", action="store_true", help="컬렉션 전체 삭제 후 전체 재인덱스(최초 1회 권장)")
    args = parser.parse_args()
    return reindex_all(limit=args.limit, reset=args.reset)


if __name__ == "__main__":
    raise SystemExit(main())
