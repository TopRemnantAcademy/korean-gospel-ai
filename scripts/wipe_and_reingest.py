"""모든 Qdrant 컬렉션(청크) 삭제 후 ZZ 청킹으로 전체 재수집.

주의:
- embedded Qdrant(`.qdrant_local`) 단일 프로세스 전용 → 백엔드(8000) 정지 후 실행.
- 삭제는 복구 불가. 재수집은 published DocumentVersion 을 다시 청킹/이중저장.
- add_document() 는 증분 갱신(같은 doc_id 재인제스트 시 기존 청크 교체).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.app.db import get_session  # noqa: E402
from backend.app.models.orm import DocumentVersion, DocVersionState  # noqa: E402
from backend.app.services.document_service import get_effective_body  # noqa: E402
from backend.app.services.enhanced_rag import get_pipeline  # noqa: E402
from backend.app.services.enhanced_rag.types import RAGDocument  # noqa: E402
from backend.app.services.enhanced_rag.vector_store import (  # noqa: E402
    SimpleBM25,
    _MANIFEST_PATH,
)

log = logging.getLogger("wipe.reingest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def wipe_all_collections(vs) -> None:
    client = getattr(vs.store, "_client", None)
    if client is None:
        raise SystemExit(
            "[wipe] Qdrant client 를 가져올 수 없습니다 — embedded Qdrant 락이 "
            "다른 프로세스에 의해 점유 중입니다. 백엔드/좀비 프로세스를 모두 종료하고 "
            "stale 락 파일(.qdrant_local/.kggateway_embedded.lock)을 삭제한 뒤 재시도하세요."
        )

    cols = client.get_collections().collections
    names = [c.name for c in cols]
    print(f"[wipe] 컬렉션 {len(names)}개 삭제 예정: {names}")
    for n in names:
        try:
            client.delete_collection(n)
            print(f"  - 삭제됨: {n}")
        except Exception as e:  # noqa: BLE001
            print(f"  - 실패 {n}: {e}")

    # 메모리 매니페스트 / BM25 / 청크 메타 초기화
    vs._manifest.clear()
    vs._chunk_meta.clear()
    vs.bm25 = SimpleBM25()

    # 디스크 매니페스트 삭제
    try:
        _MANIFEST_PATH.unlink(missing_ok=True)
        print(f"[wipe] 매니페스트 삭제: {_MANIFEST_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"[wipe] 매니페스트 삭제 실패: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Qdrant 와이프 후 ZZ 청킹 재수집")
    ap.add_argument("--limit", type=int, default=0, help="재수집할 문서 수 (0=전체)")
    ap.add_argument(
        "--no-bilingual",
        action="store_true",
        help="이중저장 번역(LLM) 비활성 — 청킹만 빠르게 검증 (rate-limit 회피용)",
    )
    args = ap.parse_args()

    pipeline = get_pipeline()
    vs = pipeline.store
    if args.no_bilingual:
        vs.translation_mgr = None
        print("[reingest] --no-bilingual: 번역(LLM) 비활성 — 청킹만 수행")
    wipe_all_collections(vs)

    with get_session() as s:
        versions = (
            s.query(DocumentVersion)
            .filter(DocumentVersion.state == DocVersionState.published.value)
            .all()
        )
        if args.limit and args.limit > 0:
            versions = versions[: args.limit]
            print(f"[reingest] --limit {args.limit} 적용 → {len(versions)}개만 처리")
        total = len(versions)
        print(f"[reingest] 대상(published): {total}개")
        if not versions:
            print("[reingest] 재수집할 문서가 없습니다.")
            return 0

        ok = skip = err = 0
        t0 = time.perf_counter()
        for idx, v in enumerate(versions, 1):
            doc = v.document
            body = get_effective_body(v)
            if not body or len(body.strip()) < 50:
                skip += 1
                continue
            rag_doc = RAGDocument(
                doc_id=f"{v.doc_id}#v{v.version_number}",
                title=v.title or "",
                source=doc.doc_key if doc else "sermon",
                content=body,
                metadata={
                    "doc_type": doc.doc_type if doc else "sermon",
                    "scripture_refs": v.scripture_refs or [],
                    "topic_tags": v.topic_tags or [],
                },
            )
            try:
                result = pipeline.add_document(rag_doc)
                if result.status == "error":
                    err += 1
                elif result.status == "skipped":
                    skip += 1
                else:
                    ok += 1
                print(
                    f"  [{idx}/{total}] {result.status} ({result.num_chunks}청크) "
                    f"— {(rag_doc.title or '')[:40]}"
                )
            except Exception as exc:  # noqa: BLE001
                err += 1
                print(f"  [{idx}/{total}] fail {rag_doc.doc_id}: {exc}")

        print(
            f"[reingest] 완료 — 성공 {ok} / 건너뜀 {skip} / 실패 {err} "
            f"(소요 {time.perf_counter() - t0:.1f}s)"
        )
        return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
