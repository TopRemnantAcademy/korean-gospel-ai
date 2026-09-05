"""기존 인덱스된 문서를 enhanced_rag 이중 저장으로 마이그레이션.

작업 K — AI_COLLAB_ORDERS.md
기존 DB의 published DocumentVersion 을 순회하며 enhanced_rag 컬렉션으로 재인제스트한다.
- 중국어 우선 이중 저장(BilingualConfig.enabled=True)이므로 각 청크는 한국어 원문 + 중국어 번역으로 저장된다.
- 번역은 LLMTranslator(Tencent DeepSeek-V4)를 사용하므로 문서량에 따라 Tencent API 호출이 발생한다.
  `--limit N` 으로 먼저 소량 테스트할 것을 권장.
- add_document() 는 증분 갱신(같은 doc_id 재인제스트 시 기존 청크 교체)이므로 재실행해도 안전하다.
"""
from __future__ import annotations

import argparse
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

log = __import__("logging").getLogger("migrate.enhanced_rag")


def main() -> int:
    parser = argparse.ArgumentParser(description="published 문서를 enhanced_rag 이중 저장으로 마이그레이션")
    parser.add_argument("--limit", type=int, default=0, help="처리할 최대 문서 수 (0=전체)")
    args = parser.parse_args()

    with get_session() as s:
        versions = (
            s.query(DocumentVersion)
            .filter(DocumentVersion.state == DocVersionState.published.value)
            .all()
        )
        total = len(versions)
        if args.limit > 0:
            versions = versions[: args.limit]
        print(f"마이그레이션 대상(published): 전체 {total}개 / 이번 실행 {len(versions)}개")

        if not versions:
            print("마이그레이션할 문서가 없습니다.")
            return 0

        pipeline = get_pipeline()
        ok = skip = err = 0
        t0 = time.perf_counter()
        for idx, v in enumerate(versions, 1):
            doc = v.document
            body = get_effective_body(v)
            if not body or len(body.strip()) < 50:
                log.info("[skip] 본문 부족: %s#v%s", v.doc_id, v.version_number)
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
                    log.warning("[fail] %s: %s", rag_doc.doc_id, result.error)
                    err += 1
                    mark = "⚠️"
                elif result.status == "skipped":
                    skip += 1
                    mark = "⏭️"
                else:
                    ok += 1
                    mark = "✅"
                print(
                    f"  [{idx}/{len(versions)}] {mark} {rag_doc.doc_id} "
                    f"({result.num_chunks}청크) — {rag_doc.title[:40]}"
                )
            except Exception as exc:
                log.warning("[fail] %s: %s", rag_doc.doc_id, exc)
                err += 1
                print(f"  [{idx}/{len(versions)}] ⚠️ {rag_doc.doc_id}: {exc}")

        elapsed = time.perf_counter() - t0
        print(
            f"마이그레이션 완료 — 성공 {ok} / 건너뜀 {skip} / 실패 {err} "
            f"(소요 {elapsed:.1f}s)"
        )
        return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
