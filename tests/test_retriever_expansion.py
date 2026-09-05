"""retriever — 쿼리 확장(async analyze_query_async) 다중 경로 검색 통합 테스트.

실행:
    ./venv/Scripts/python.exe -m pytest tests/test_retriever_expansion.py -q

검증 목표 (부족 A 해결 증명)
----------------------------
과거 `analyze_query`(동기)가 retriever 비동기 컨텍스트에서 LLM 확장을 '실행 중 loop
→ 무시' 로 영구 비활성화했던 문제를, `analyze_query_async` 로 직접 await 하여
expanded_queries 가 실제로 다중 검색 경로에 주입되는지 검증한다.

외부 의존(Qdrant 실서버 / 임베더 모델)은 전부 모킹 → 단위·통합 CI 에서 격리 실행.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

# retriever 가 내부에서 import 하는 asyncio 를 제어하기 위해 먼저 로드
import asyncio  # noqa: E402
from app.services.search_optimizer import QueryAnalysis  # noqa: E402


@pytest.fixture
def patched_retriever_deps():
    """QdrantStore / get_embedder / get_reranker / _bm25_sparse 를 모킹.

    - embed_query 는 쿼리 텍스트를 기록(spy)하면서 더미 벡터 반환
    - search_dense / search_sparse 는 빈 결과 반환(검색 경로가 호출되었음만 확인)
    """
    captured = {"queries": []}

    import numpy as np

    class _FakeEmb:
        dim = 4

        def embed_query(self, q: str):
            captured["queries"].append(q)
            return np.array([0.0, 0.0, 0.0, 0.0])

        def embed_documents(self, docs):
            return [np.array([0.0, 0.0, 0.0, 0.0]) for _ in docs]

    fake_emb = _FakeEmb()

    # QdrantStore 인스턴스 메서드 모킹
    with mock.patch(
        "app.services.retriever.QdrantStore"
    ) as MockStore, mock.patch(
        "app.services.retriever.get_embedder", return_value=fake_emb
    ), mock.patch(
        "app.services.retriever.get_reranker", return_value=mock.MagicMock()
    ), mock.patch(
        "app.services.retriever._bm25_sparse", return_value=[]
    ):
        store_inst = MockStore.return_value
        store_inst.search_dense.return_value = []
        store_inst.search_sparse.return_value = []
        yield fake_emb, captured, store_inst


def test_retrieve_consumes_expanded_queries(patched_retriever_deps):
    """analyze_query_async 가 주입한 2개 확장 쿼리가 각각 검색 경로로 전달된다."""
    fake_emb, captured, store_inst = patched_retriever_deps

    from app.services.retriever import HybridRetriever

    retriever = HybridRetriever(embedder_name="kure")
    # embed_query spy 는 patched_retriever_deps 의 fake_emb 와 동일 인스턴스여야 함
    retriever.embedder = fake_emb

    expanded = ["구원이란 무엇인가", "예수님 구원의 의미"]
    qa = QueryAnalysis(
        original="구원이란",
        query_type="semantic",
        expanded_queries=expanded,
        dense_weight=0.7,
        sparse_weight=0.3,
        preferred_filters={},
        confidence=0.8,
    )

    async def _run():
        with mock.patch(
            "app.services.retriever.analyze_query_async",
                new=mock.AsyncMock(return_value=qa),
            ):
            return await retriever.retrieve("구원이란", top_k=5)

    results = asyncio.run(_run())

    # 각 확장 쿼리가 dense 검색에 주입되었는지
    assert captured["queries"], "어떤 쿼리도 검색 경로에 전달되지 않음"
    assert "구원이란 무엇인가" in captured["queries"]
    assert "예수님 구원의 의미" in captured["queries"]
    # 원본과 확장이 모두 포함되었는지(중복 없이)
    assert set(captured["queries"]) == set(expanded)


def test_retrieve_single_query_no_merge(patched_retriever_deps):
    """확장이 1개(원본만)면 중복 병합 단계를 타지 않고 정상 종료."""
    fake_emb, captured, store_inst = patched_retriever_deps

    from app.services.retriever import HybridRetriever

    retriever = HybridRetriever(embedder_name="kure")
    retriever.embedder = fake_emb

    qa = QueryAnalysis(
        original="구원",
        query_type="semantic",
        expanded_queries=["구원"],
        dense_weight=0.7,
        sparse_weight=0.3,
        preferred_filters={},
        confidence=0.8,
    )

    async def _run():
        with mock.patch(
            "app.services.retriever.analyze_query_async",
                new=mock.AsyncMock(return_value=qa),
            ):
            return await retriever.retrieve("구원", top_k=5)

    results = asyncio.run(_run())
    assert captured["queries"] == ["구원"]
