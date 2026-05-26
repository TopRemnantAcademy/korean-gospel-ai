"""data/eval/questions.json 의 질문셋으로 임베더 A/B 자동 평가.

사용:
    python scripts/ab_test.py
    python scripts/ab_test.py --embedders kure,bge_m3,e5

평가 지표 (간단):
- Hit@K: relevant 문서 id가 top-K에 들어왔는지
- 평균 rerank score
- 평균 응답시간
"""
from __future__ import annotations
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.app.config import settings  # noqa: E402
from backend.app.services.retriever import HybridRetriever  # noqa: E402


async def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedders", default=",".join(settings.embedders))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--questions", default="data/eval/questions.json")
    args = ap.parse_args()

    qpath = ROOT / args.questions
    if not qpath.exists():
        print(f"[X] {qpath} 없음. 샘플을 먼저 만드세요.")
        sys.exit(1)
    questions = json.loads(qpath.read_text(encoding="utf-8"))

    print(f"[i] 질문 {len(questions)}개 · embedders={args.embedders}\n")

    for emb_name in [e.strip() for e in args.embedders.split(",") if e.strip()]:
        retriever = HybridRetriever(embedder_name=emb_name)
        latencies, top_scores, hits = [], [], []
        for q in questions:
            t0 = time.time()
            res = await retriever.retrieve(q["query"], rerank_top_n=args.top_k)
            latencies.append(time.time() - t0)
            top_scores.append(res[0].score if res else 0.0)
            if "expected_keywords" in q:
                joined = "\n".join(r.text for r in res)
                hit = any(k in joined for k in q["expected_keywords"])
                hits.append(1 if hit else 0)

        print(f"=== {emb_name} ===")
        print(f"  평균 latency : {statistics.mean(latencies):.2f}s")
        print(f"  평균 top1    : {statistics.mean(top_scores):.3f}")
        if hits:
            print(f"  Hit@{args.top_k}    : {sum(hits)}/{len(hits)}  ({sum(hits)/len(hits)*100:.1f}%)")
        print()


if __name__ == "__main__":
    asyncio.run(run())
