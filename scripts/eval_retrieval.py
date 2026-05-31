"""검색 품질 측정 도구 — 골든 질문 세트로 retrieval 정확도 평가.

측정 지표:
  - recall@k     : 기대 키워드가 top-k 청크 안에 등장하는 비율
  - avg_score    : top-1 평균 점수
  - latency      : 검색 소요 시간(ms)

용도:
  - boost matrix·메타데이터 추출 개선 전후 A/B 비교
  - 정규 회귀 테스트 (검색 품질이 떨어지지 않았는지)

※ 실행 중인 백엔드 서버의 /chat?debug=true 를 호출해 평가한다.
  embedded Qdrant 는 동시 접속이 안 되므로 별도 프로세스로 retriever 를
  직접 띄우지 않고, 서버 API 를 통해 검색 결과를 받아온다.

실행 (서버가 8000 포트에서 떠 있어야 함):
  venv/Scripts/python -m scripts.eval_retrieval
  venv/Scripts/python -m scripts.eval_retrieval --k 5 --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

API_BASE = "http://127.0.0.1:8000"


# ── 골든 질문 세트 ────────────────────────────────────────────────────────────
# 각 항목: 질문 + 검색 결과 본문에 등장해야 하는 키워드(하나라도 매치하면 hit)
GOLDEN_SET: list[dict] = [
    {"q": "복음이 무엇인가요?",            "expect": ["복음", "예수", "그리스도"]},
    {"q": "구원은 어떻게 받나요?",          "expect": ["구원", "믿음", "은혜", "영접"]},
    {"q": "십자가의 의미가 무엇인가요?",     "expect": ["십자가", "대속", "죄"]},
    {"q": "예수님은 누구신가요?",          "expect": ["예수", "그리스도", "하나님"]},
    {"q": "기도는 어떻게 하나요?",          "expect": ["기도", "하나님", "말씀"]},
    {"q": "성령님은 어떤 분이신가요?",       "expect": ["성령", "하나님"]},
    {"q": "회개란 무엇인가요?",            "expect": ["회개", "죄", "돌이"]},
    {"q": "믿음이란 무엇인가요?",          "expect": ["믿음", "하나님", "예수"]},
    {"q": "은혜가 무엇인가요?",            "expect": ["은혜", "선물", "값없"]},
    {"q": "교회는 왜 다녀야 하나요?",        "expect": ["교회", "공동체", "성도", "예배"]},
]


def _hit(text: str, expect: list[str]) -> bool:
    """검색된 본문에 기대 키워드가 하나라도 등장하면 hit."""
    return any(kw in text for kw in expect)


def _query_server(client: httpx.Client, q: str) -> list[dict]:
    """서버 /chat?debug=true 호출 → sources 리스트 반환."""
    r = client.post(f"{API_BASE}/chat", json={"query": q, "history": [], "debug": True})
    if r.status_code >= 400:
        return []
    return r.json().get("sources", [])


def run_eval(k: int = 5, as_json: bool = False) -> dict:
    rows = []
    hits = 0
    total_latency = 0.0
    total_top1 = 0.0
    scored = 0

    with httpx.Client(timeout=120) as client:
        # 워밍업 1회 (모델 로딩·캐시 제외)
        _query_server(client, "워밍업")

        for item in GOLDEN_SET:
            q = item["q"]
            expect = item["expect"]
            t0 = time.time()
            sources = _query_server(client, q)
            latency = (time.time() - t0) * 1000
            total_latency += latency

            results = sources[:k]
            combined = " ".join(s.get("text", "") for s in results)
            is_hit = _hit(combined, expect)
            if is_hit:
                hits += 1

            top1_score = results[0].get("score", 0.0) if results else 0.0
            if results:
                total_top1 += top1_score
                scored += 1

            rows.append({
                "q": q,
                "hit": is_hit,
                "results": len(results),
                "top1_score": round(top1_score, 4),
                "latency_ms": round(latency, 1),
                "top1_title": (results[0].get("metadata") or {}).get("title", "?") if results else None,
            })

    n = len(GOLDEN_SET)
    summary = {
        "recall_at_k": round(hits / n, 3),
        "k": k,
        "questions": n,
        "hits": hits,
        "avg_top1_score": round(total_top1 / scored, 4) if scored else 0.0,
        "avg_latency_ms": round(total_latency / n, 1),
    }

    if as_json:
        print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print("=" * 64)
        print(f"검색 품질 평가 — recall@{k}")
        print("=" * 64)
        for r in rows:
            mark = "✓" if r["hit"] else "✗"
            print(f"  {mark} [{r['top1_score']:.3f}] {r['q'][:30]:<30} "
                  f"→ {r['top1_title']} ({r['latency_ms']:.0f}ms)")
        print("-" * 64)
        print(f"  recall@{k}      : {summary['recall_at_k']:.1%} ({hits}/{n})")
        print(f"  avg top1 score : {summary['avg_top1_score']:.4f}")
        print(f"  avg latency    : {summary['avg_latency_ms']:.0f}ms")
        print("=" * 64)

    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5, help="top-k 검색 개수")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()
    run_eval(k=args.k, as_json=args.json)
