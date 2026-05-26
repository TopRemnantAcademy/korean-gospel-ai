"""data/documents → data/eval/questions.json 자동 생성.

  python scripts/generate_eval_set.py
  python scripts/generate_eval_set.py --merge --max-per-doc 2
"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.app.services.eval_set_generator import (  # noqa: E402
    generate_questions_from_documents,
    save_questions,
)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-dir", default=None)
    ap.add_argument("--max-per-doc", type=int, default=3)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true", help="LLM 없이 파일명 기반 생성")
    args = ap.parse_args()

    if args.offline:
        from backend.app.services.eval_set_generator import build_questions_offline
        questions = build_questions_offline(doc_dir=args.doc_dir)
    else:
        questions = await generate_questions_from_documents(
            doc_dir=args.doc_dir,
            max_per_doc=args.max_per_doc,
        )
    print(f"[i] 생성 {len(questions)}개")
    for q in questions[:5]:
        print(f"  - {q['query'][:60]}…")
    if args.dry_run:
        return
    if not questions:
        sys.exit(1)
    path = save_questions(questions, merge=args.merge)
    print(f"[OK] 저장: {path}")


if __name__ == "__main__":
    asyncio.run(main())
