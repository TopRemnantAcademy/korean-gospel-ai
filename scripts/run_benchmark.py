"""Embedder 벤치마크 — 지원 모델별 처리량/지연/캐시 적중률 비교.

README.md / PROCESS_MAP.md 가 명시한 공식 운영 스크립트다. 임베더 팩토리의
공개 인터페이스(`list_supported`/`get_embedder`/`cache_stats`/
`clear_all_caches`)만 사용하며, DB 를 전혀 건드리지 않는다(순수 벤치마크).

실행:
    cd <repo> && python scripts/run_benchmark.py
    python scripts/run_benchmark.py --embedders kure bge_m3 --docs 200 --queries 100
    python scripts/run_benchmark.py --warmup 1   # 캐시 적중률 측정용 사전 워밍업

    # API 키가 필요한 원격 embedder(nvidia/hf_inference 등) 벤치마크 예시:
    #   키는 환경변수로 주입하며 스크립트는 DB 를 건드리지 않으므로 안전하다.
    TENCENT_API_KEY=xxx NVIDIA_API_KEY=yyy \
        python scripts/run_benchmark.py --embedders nvidia hf_inference --docs 100 --queries 50

    # embedding/factory.py 의 list_supported() 로 현재 사용 가능한 이름 확인:
    python -c "import sys; sys.path.insert(0,'backend'); \
from app.services.embedding.factory import list_supported; print(list_supported())"

출력:
    각 embedder 별
      - doc_throughput   : 문서 배치 임베딩 처리량 (docs/sec)
      - query_p50/p95    : 단일 쿼리 지연 백분위 (ms)
      - cache_hit_ratio  : 2회차 실행 시 캐시 적중률
      - dim              : 임베딩 차원

설계 원칙
--------
- 외부 입력(--embedders/--docs/--queries)은 모두 엄격 검증. 0 이하 거부.
- 임베딩 실패(키 누락 등)는 해당 embedder 를 skip 하고 경고, 전체 중단 안 함.
- 캐시 통계는 embedder 이름별로 격리되어 있으므로, 각 대상 전후로
  clear_all_caches() 로 격리 측정한다.
- numpy 기반 percentile 로 p50/p95 계산(추가 의존 없음).
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("benchmark")

# 벤치마크 고정 말뭉치 (의미 있는 길이의 한국어/영어 혼합 샘플)
_SAMPLE_DOCS = [
    "예수님은 우리의 죄를 위하여 십자가에서 돌아가시고 부활하셨다.",
    "로마서 3장 23절은 모든 사람이 죄를 범하였다고 선포한다.",
    "요한복음 3장 16절은 하나님이 세상을 이처럼 사랑하셨다고 말한다.",
    "천국은 마음이 가난한 자의 것이니라.",
    "Faith comes by hearing, and hearing by the word of God.",
    "성령은 우리를 진리 가운데로 인도하시는 보혜사시다.",
    "은혜로 구원을 받았으니 이것은 너희가 행한 것이 아니라 하나님의 선물이다.",
    "네 이웃을 네 몸과 같이 사랑하라 하는 것이 율법의 요점이니라.",
    "기도는 하나님과의 대화이며 믿음의 호흡이다.",
    "The Lord is my shepherd, I shall not want.",
    "회개하라 천국이 가까이 왔느니라.",
    "말씀은 살았고 운동력이 있어 좌우에 날선 검보다 더 예리하다.",
    "사랑은 인내하고 사랑은 온유하며 투기하는 자가 되지 아니한다.",
    "너희는 세상을 본받지 말고 오직 마음을 새롭게 함으로 변화를 받으라.",
    "For God so loved the world that He gave His only Son.",
]
_SAMPLE_QUERIES = [
    "구원이란 무엇인가?",
    "로마서에서 죄에 대해 무엇이라 하는가?",
    "요한복음 3장 16절을 설명해 줘.",
    "성령의 역할은?",
    "은혜로 구원받는다는 뜻은?",
    "이웃 사랑에 대한 말씀은?",
    "기도의 의미를 알려줘.",
    "The Lord is my shepherd 의미는?",
    "회개와 천국에 대해 설명해 줘.",
    "말씀의 예리함에 대해 말씀해 줘.",
    "사랑에 대한 성경 구절을 알려줘.",
    "마음을 새롭게 함이란?",
    "하나님이 세상을 사랑하신 방식은?",
    "십자가의 의미를 설명해 줘.",
    "부활의 의미는 무엇인가?",
]

_BENCH_DOC_SIZE = 40  # 단일 문서 평균 토큰 추정용 (지연 정규화 무관, 표시용)


def _build_corpus(n_docs: int, n_queries: int) -> tuple[list[str], list[str]]:
    """말뭉치를 결정적(seed 고정)으로 생성.

    매개변수
    --------
    n_docs: 생성할 문서 수(최소 1).
    n_queries: 생성할 쿼리 수(최소 1).

    반환
    ----
    (docs, queries) 튜플. 샘플을 순환 복제 + 난수 jitter 로 길이 다양화.
    """
    rng = random.Random(20260526)  # 재현 가능한 벤치마크
    docs: list[str] = []
    for i in range(max(1, n_docs)):
        base = _SAMPLE_DOCS[i % len(_SAMPLE_DOCS)]
        # 결정적 jitter: 매 문서마다 짧은 접두/후접으로 분산 확보
        docs.append(f"[{i}] {base} (참고: {_SAMPLE_DOCS[(i * 7) % len(_SAMPLE_DOCS)]})")
    queries: list[str] = []
    for i in range(max(1, n_queries)):
        queries.append(_SAMPLE_QUERIES[i % len(_SAMPLE_QUERIES)])
    return docs, queries


def _percentile(values: list[float], q: float) -> float:
    """numpy 없이도 동작하도록 np.percentile 래퍼(단일 값 방어)."""
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), q))


def _bench_embedder(name: str, docs: list[str], queries: list[str], warmup: int) -> dict | None:
    """단일 embedder 벤치마크.

    매개변수
    --------
    name: 팩토리 등록명(list_supported 결과 중 하나).
    docs: 문서 말뭉치.
    queries: 쿼리 말뭉치.
    warmup: 캐시 적중률 측정용 사전 워밍업 횟수.

    반환
    ----
    결과 dict(dim/throughput/p50/p95/hit_ratio) 또는 실패 시 None.
    """
    from app.services.embedding.factory import (  # noqa: E402
        clear_all_caches,
        get_embedder,
    )

    try:
        emb = get_embedder(name)
    except Exception as e:
        log.warning("embedder '%s' 로드 실패 — skip: %s", name, e)
        return None

    dim = emb.dim
    log.info("벤치마크 시작: %s (dim=%d, docs=%d, queries=%d)", name, dim, len(docs), len(queries))

    # ── 1) 문서 배치 처리량 ──
    clear_all_caches()
    t0 = time.perf_counter()
    try:
        emb.embed_documents(docs)
    except Exception as e:
        log.warning("embedder '%s' 문서 임베딩 실패 — skip: %s", name, e)
        return None
    doc_elapsed = time.perf_counter() - t0
    throughput = len(docs) / doc_elapsed if doc_elapsed > 0 else float("inf")

    # ── 2) 쿼리 지연 p50/p95 (cold, 캐시 비운 상태) ──
    clear_all_caches()
    cold_lat = []
    for q in queries:
        t0 = time.perf_counter()
        emb.embed_query(q)
        cold_lat.append((time.perf_counter() - t0) * 1000.0)

    # ── 3) 워밍업 후 캐시 적중률 ──
    for _ in range(max(0, warmup)):
        for q in queries:
            emb.embed_query(q)
    stats = emb.cache_stats()
    hit_ratio = float(stats.get("hit_ratio", 0.0))

    result = {
        "embedder": name,
        "dim": dim,
        "doc_throughput_docs_per_sec": round(throughput, 2),
        "doc_total_ms": round(doc_elapsed * 1000, 2),
        "query_p50_ms": round(_percentile(cold_lat, 50), 3),
        "query_p95_ms": round(_percentile(cold_lat, 95), 3),
        "cache_hit_ratio": hit_ratio,
        "cache_size": int(stats.get("size", 0)),
    }
    log.info("결과[%s]: %s", name, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Embedder 벤치마크")
    parser.add_argument(
        "--embedders", nargs="+", default=None,
        help="벤치마크할 embedder 이름들(미지정 시 list_supported 전체).",
    )
    parser.add_argument("--docs", type=int, default=200, help="문서 말뭉치 크기 (>=1)")
    parser.add_argument("--queries", type=int, default=100, help="쿼리 말뭉치 크기 (>=1)")
    parser.add_argument("--warmup", type=int, default=1, help="캐시 적중률 측정용 워밍업 횟수 (>=0)")
    args = parser.parse_args()

    # ── 입력 검증 ──
    if args.docs < 1:
        parser.error("--docs 는 1 이상이어야 합니다.")
    if args.queries < 1:
        parser.error("--queries 는 1 이상이어야 합니다.")
    if args.warmup < 0:
        parser.error("--warmup 은 0 이상이어야 합니다.")

    # 팩토리에서 지원 목록 조회(지연 import 로 순환 방지)
    from app.services.embedding.factory import list_supported  # noqa: E402

    supported = set(list_supported())
    if args.embedders:
        unknown = [e for e in args.embedders if e not in supported]
        if unknown:
            parser.error(f"지원하지 않는 embedder: {unknown}. 지원: {sorted(supported)}")
        targets = list(args.embedders)
    else:
        targets = list(supported)

    docs, queries = _build_corpus(args.docs, args.queries)

    log.info("벤치마크 대상: %s", targets)
    results: list[dict] = []
    for name in targets:
        r = _bench_embedder(name, docs, queries, args.warmup)
        if r is not None:
            results.append(r)

    # ── 요약 출력 ──
    print("\n=== Embedder Benchmark Summary ===")
    print(f"{'embedder':<14}{'dim':>6}{'docs/s':>12}{'q_p50(ms)':>12}{'q_p95(ms)':>12}{'cache_hit':>11}")
    for r in results:
        print(
            f"{r['embedder']:<14}{r['dim']:>6}"
            f"{r['doc_throughput_docs_per_sec']:>12}"
            f"{r['query_p50_ms']:>12}{r['query_p95_ms']:>12}"
            f"{r['cache_hit_ratio']:>11}"
        )
    if not results:
        print("(벤치마크 가능한 embedder 가 없음 — API 키/모델 확인 필요)")
    log.info("벤치마크 종료: %d/%d 성공", len(results), len(targets))


if __name__ == "__main__":
    main()
