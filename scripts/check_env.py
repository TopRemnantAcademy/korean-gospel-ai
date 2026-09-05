#!/usr/bin/env python3
"""env 프리셋 일관성 검증 — 로컬/클라우드 전환 시 조용한降级 방지.

문제: .env.production 과 .env.local 은 별도로手写 → 새 기능 env(예: RAG_ENHANCED_ENABLED)
     한쪽만 추가하면 전환 후 해당 기능이 조용히 기본값(보통 OFF)으로 동작.
해결: BASELINE(아래) 에 필수 키를 등록 → 두 프리셋 모두에 존재하는지 검증.

사용:
    python scripts/check_env.py                # .env.production + .env.local 비교
    python scripts/check_env.py --strict       # 템플릿 기준 누락키도 경고
    python scripts/check_env.py --a .env.production --b .env.local
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── BASELINE: 두 프리셋 모두에 반드시 있어야 하는 핵심 키 ──
# (기능 on/off 와 무관하게, 전환 후 동일하게 동작해야 하는 설정)
BASELINE = [
    # LLM
    "LLM_PROVIDER", "LLM_FALLBACK_ENABLED", "LLM_FALLBACK_CHAIN",
    "OLLAMA_HOST", "OLLAMA_MODEL",
    # Embedder
    "EMBEDDER", "EMBEDDER_LIST",
    # Vector DB
    "QDRANT_URL", "QDRANT_COLLECTION_PREFIX",
    # Reranker
    "RERANKER",
    # Retrieval
    "RETRIEVAL_TOP_K", "RERANK_TOP_N", "DENSE_WEIGHT", "SPARSE_WEIGHT",
    # Policy / Speed
    "POLICY_ENABLED", "SALVATION_DETECTION_ENABLED", "CLASSIFY_INPUT_ENABLED",
    # Ingest
    "INGEST_NORMALIZE_ENABLED", "INGEST_RESTRUCTURE_ENABLED",
    "INGEST_CONTEXTUAL_ENABLED", "INGEST_QUALITY_GATE_ENABLED",
    "INGEST_CHUNK_TARGET_TOKENS", "INGEST_CHUNK_MAX_TOKENS", "INGEST_CHUNK_MIN_TOKENS",
    # Data
    "DATA_DIR", "LOG_LEVEL", "MAX_UPLOAD_SIZE_MB",
    # Runtime
    "APP_ENV", "DOCS_ENABLED", "KRAI_PUBLIC_MODE", "UVICORN_WORKERS", "PORT",
]

# 환경별로 값이 달라야 하는 키(일치 비교에서 제외 — 차이가 정상인 것)
EXPECTED_DIFF = {
    "QDRANT_URL",      # prod=http://qdrant:6333 / local=local:./.qdrant_local
    "LLM_PROVIDER",    # prod=gemini / local=ollama
    "LLM_FALLBACK_ENABLED",
    "RERANKER",        # prod=bge_m3 / local=none
    "DOCS_ENABLED",
    "KRAI_PUBLIC_MODE",
    "APP_ENV",
    "UVICORN_WORKERS",
    "OLLAMA_HOST",
}


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=".env.production")
    ap.add_argument("--b", default=".env.local")
    ap.add_argument("--strict", action="store_true",
                    help="템플릿(.template) 기준으로 누락 키도 경고")
    args = ap.parse_args()

    pa, pb = ROOT / args.a, ROOT / args.b
    if not pa.exists():
        print(f"❌ {pa} 없음 — 먼저 cp {args.a}.template {args.a}")
        return 1
    if not pb.exists():
        print(f"❌ {pb} 없음 — 먼저 cp {args.b}.template {args.b}")
        return 1

    a, b = parse_env(pa), parse_env(pb)
    problems: list[str] = []

    # 1) BASELINE 누락 검사
    for key in BASELINE:
        if key not in a:
            problems.append(f"[{args.a}] 누락: {key}")
        if key not in b:
            problems.append(f"[{args.b}] 누락: {key}")

    # 2) 키 집합 비대칭(전환 시 조용한降级 유발)
    only_a = set(a) - set(b) - EXPECTED_DIFF
    only_b = set(b) - set(a) - EXPECTED_DIFF
    for k in sorted(only_a):
        problems.append(f"⚠️ {args.a} 에만 존재(전환 시 {args.b} 에서 무시됨): {k}")
    for k in sorted(only_b):
        problems.append(f"⚠️ {args.b} 에만 존재(전환 시 {args.a} 에서 무시됨): {k}")

    # 3) strict: 템플릿 기준 누락
    if args.strict:
        for tmpl_name in [f"{args.a}.template", f"{args.b}.template"]:
            tmpl = ROOT / tmpl_name
            if tmpl.exists():
                tkeys = set(parse_env(tmpl))
                for k in sorted(tkeys - set(a) - set(b)):
                    problems.append(f"⚠️ 템플릿 {tmpl_name} 에 있으나 양쪽 프리셋에 없음: {k}")

    if problems:
        print(f"\n🔴 env 일관성 검증 실패 ({len(problems)}건):\n")
        for p in problems:
            print(f"  - {p}")
        print("\n수정: 두 프리셋에 동일 키를 추가하거나 EXPECTED_DIFF/Docker env 로 보강하세요.")
        return 1

    print(f"✅ env 일관성 OK — {args.a} ↔ {args.b} (BASELINE {len(BASELINE)}키 일치)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
