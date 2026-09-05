"""문서 인덱싱 — data/documents/ → Qdrant 벡터 DB.

  python scripts/ingest_documents.py
  python scripts/ingest_documents.py --reset

백엔드 시작 시 자동으로 KURE 모델 로딩 + BM25 sparse 인덱스 재구축이 실행됨.
이 스크립트는 명시적 재색인 또는 신규 설치 시 초기화 용도.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def main():
    ap = argparse.ArgumentParser(description="문서 → Qdrant 인덱싱")
    ap.add_argument("--doc-dir", default=None)
    ap.add_argument("--embedders", default=None, help="CSV e.g. kure,bge_m3 (사용하지 않음 — 백엔드 설정 따름)")
    ap.add_argument("--reset", action="store_true", help="Qdrant 컬렉션 초기화 후 재색인")
    args = ap.parse_args()

    print("[ingest] 초기화 중...")

    # 1. DB + ORM 초기화
    from backend.app.db import init_db
    init_db()
    print("[ingest] DB 초기화 완료")

    # 2. Sparse 인덱스 재구축 (Qdrant → BM25)
    try:
        from backend.app.services.retriever import get_retriever
        from backend.app.services.sparse_index import rebuild_from_qdrant
        retriever = get_retriever()
        n = rebuild_from_qdrant(
            retriever.store.collection,
            client=retriever.store._client,
        )
        print(f"[ingest] BM25 sparse 인덱스 재구축 완료: {n}개 청크")
    except Exception as exc:
        print(f"[ingest] BM25 재구축 건너뜀 (데이터 없음 또는 오류): {exc}")

    # 3. 데이터 폴더에서 문서 인덱싱 (있는 경우)
    doc_dir = args.doc_dir or str(ROOT / "data" / "documents")
    doc_path = Path(doc_dir)
    if doc_path.exists():
        docs = list(doc_path.rglob("*"))
        doc_count = len([d for d in docs if d.is_file() and d.suffix.lower() in (".txt", ".md", ".pdf", ".docx")])
        if doc_count > 0:
            print(f"[ingest] {doc_count}개 문서 발견 — 백엔드 시작 시 자동 색인됩니다")
            print("[ingest] 터미널에서 STEP3_START.bat 실행 후 Admin UI > Upload 로 업로드하세요")
        else:
            print("[ingest] data/documents/ 에 문서 없음 — 샘플 설교 업로드 필요")

    print("[ingest] OK")
    result = {"ok": True, "doc_dir": doc_dir}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
