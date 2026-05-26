"""data/documents → Qdrant 인덱싱 (검색·평가용).

  python scripts/ingest_documents.py
  python scripts/ingest_documents.py --reset --embedders kure
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

from backend.app.services.document_indexer import index_documents_folder  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-dir", default=None)
    ap.add_argument("--embedders", default=None, help="CSV e.g. kure,bge_m3")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    embedders = None
    if args.embedders:
        embedders = [e.strip() for e in args.embedders.split(",") if e.strip()]

    result = index_documents_folder(
        doc_dir=args.doc_dir,
        embedders=embedders,
        reset=args.reset,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
