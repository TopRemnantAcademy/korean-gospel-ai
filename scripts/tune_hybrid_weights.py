"""validation 질문셋으로 dense/sparse RRF 가중치 그리드 탐색.

  python scripts/tune_hybrid_weights.py
  python scripts/tune_hybrid_weights.py --embedder kure
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.app.services.hybrid_tuner import tune_hybrid_weights  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default=None)
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    result = await tune_hybrid_weights(embedder=args.embedder, top_k=args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("ok"):
        b = result["best"]
        print(f"\n[추천] DENSE_WEIGHT={b['dense_weight']}  SPARSE_WEIGHT={b['sparse_weight']}  MRR={b['mrr']}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
