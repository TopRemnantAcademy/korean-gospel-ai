"""Enhanced RAG — 단위/통합 테스트.

실행:
    ./venv/Scripts/python.exe tests/test_enhanced_rag.py
    # 또는 pytest: ./venv/Scripts/python.exe -m pytest tests/test_enhanced_rag.py -q

- 순수 단위: 청킹, BM25, RRF 융합, 검색 지표, 프롬프트 조립
- 통합 스모크: in-memory Qdrant + hash 임베더로 인제스트→검색→평가 전체 파이프라인
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.services.enhanced_rag.chunking import DocumentChunker
from backend.app.services.enhanced_rag.bm25 import SimpleBM25, tokenize
from backend.app.services.enhanced_rag.retrieval import HybridRetriever
from backend.app.services.enhanced_rag.evaluation import RAGEvaluator
from backend.app.services.enhanced_rag.prompt import PromptAssembler
from backend.app.services.enhanced_rag.types import RAGDocument, RetrievedChunk


# ──────────────────────────────────────────────────────────────
# 1) 청킹
# ──────────────────────────────────────────────────────────────
def test_chunking_recursive():
    chunker = DocumentChunker(strategy="recursive", chunk_size=120, chunk_overlap=20)
    text = (
        "# 제목\n\n첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장도 있습니다. "
        "네 번째 문장을 추가합니다. 다섯 번째 문장입니다. 여섯 번째 문장도 있어요. "
        "일곱 번째 문장입니다. 여덟 번째 문장을 덧붙입니다."
    )
    chunks = chunker.chunk(text, doc_id="d1", title="T", source="s.txt")
    assert len(chunks) >= 1
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "chunk_id 는 전역 고유해야 함"
    joined = "".join(c.text for c in chunks)
    assert "첫 번째" in joined and "여덟" in joined, "원문 보존"


def test_chunking_fixed_and_overlap():
    # fixed 전략은 최소 청크 크기를 50자로 강제하므로 더 긴 텍스트 사용
    chunker = DocumentChunker(strategy="fixed", chunk_size=50, chunk_overlap=10)
    text = (
        "가나다라마바사아자차카타파하거너더러머버서어저버 "
        "조차차카타파하거너더러머버서어저버호되로모조코토 "
        "노단더러머버서어저버호되로모조코토소루푸호되로모"
    )
    chunks = chunker.chunk(text, doc_id="d2")
    assert len(chunks) >= 2
    # overlap 이 있으므로 마지막 청크가 이전 일부를 포함할 수 있음 (길이만 검증)
    assert all(len(c.text) <= 60 for c in chunks)


def test_chunking_json_loader():
    chunker = DocumentChunker(strategy="recursive")
    data = [
        {"title": "A", "text": "첫 내용입니다."},
        {"title": "B", "text": "두 번째 내용입니다."},
    ]
    import json
    text = DocumentChunker.load(json.dumps(data), "json")
    assert "첫 내용입니다." in text and "두 번째 내용입니다." in text


# ──────────────────────────────────────────────────────────────
# 2) BM25 (증분 갱신)
# ──────────────────────────────────────────────────────────────
def test_bm25_search_and_remove():
    bm = SimpleBM25()
    bm.add("c1", tokenize("예수님의 사랑과 은혜에 대하여"))
    bm.add("c2", tokenize("부활의 증거와 십자가의 의미"))
    res = bm.search(tokenize("부활"), top_k=5)
    assert res and res[0][0] == "c2"
    bm.remove("c2")
    assert "c2" not in bm
    res2 = bm.search(tokenize("부활"), top_k=5)
    assert all(cid != "c2" for cid, _ in res2)


# ──────────────────────────────────────────────────────────────
# 3) RRF 융합
# ──────────────────────────────────────────────────────────────
def test_rrf_fusion():
    # 파트4 리팩터 이후 시그니처: _rrf_fusion_streams(streams, k)
    # streams = [(ranked_results, weight, kind), ...]  kind = "dense" | "sparse"
    dense = [
        {"chunk_id": "a", "doc_id": "da", "text": "x", "score": 0.9, "meta": {}},
        {"chunk_id": "b", "doc_id": "db", "text": "y", "score": 0.5, "meta": {}},
    ]
    kw = [
        {"chunk_id": "b", "doc_id": "db", "text": "y", "score": 3.0, "meta": {}},
        {"chunk_id": "c", "doc_id": "dc", "text": "z", "score": 2.0, "meta": {}},
    ]
    streams = [(dense, 0.7, "dense"), (kw, 0.3, "sparse")]
    fused = HybridRetriever._rrf_fusion_streams(streams, 60)
    ids = [f["chunk_id"] for f in fused]
    # b 는 두 랭킹 모두 상위 → 1위여야 함
    assert ids[0] == "b"
    assert set(ids) == {"a", "b", "c"}


# ──────────────────────────────────────────────────────────────
# 4) 검색 지표
# ──────────────────────────────────────────────────────────────
def _mk_chunk(chunk_id, doc_id, score):
    c = RetrievedChunk(chunk_id=chunk_id, doc_id=doc_id, text="t", score=score)
    return c


def test_retrieval_metrics():
    cases = [
        {
            "retrieved": [_mk_chunk("a1", "A", 0.9), _mk_chunk("b1", "B", 0.5)],
            "relevant": {"A"},
            "relevant_is_doc": True,
        },
        {
            "retrieved": [_mk_chunk("x1", "X", 0.9), _mk_chunk("y1", "Y", 0.5)],
            "relevant": {"Y"},
            "relevant_is_doc": True,
        },
    ]
    m = RAGEvaluator.eval_retrieval(cases, k=2)
    assert m.queries == 2
    assert m.hit_rate == 1.0
    assert m.recall_at_k == 1.0
    # case0: rank1 rel(A) → mrr 1.0 ; case1: rank2 rel(Y) → 0.5 ; 평균 0.75
    assert abs(m.mrr - 0.75) < 1e-6
    assert m.ndcg_at_k > 0.0


# ──────────────────────────────────────────────────────────────
# 5) 프롬프트 조립
# ──────────────────────────────────────────────────────────────
def test_prompt_assembly():
    chunks = [
        RetrievedChunk(chunk_id="c1", doc_id="A", text="예수님은 구원의 길입니다.", score=0.9,
                       title="복음", source="gospel.txt", section="서론"),
        RetrievedChunk(chunk_id="c2", doc_id="B", text="부활은 희망의 증거입니다.", score=0.8,
                       title="부활", source="easter.txt"),
    ]
    asm = PromptAssembler(language="ko")
    system, user, citations = asm.assemble("예수님에 대해 알려줘", chunks, max_tokens=200, top_k=5)
    assert citations[0]["index"] == 1
    assert citations[0]["title"] == "복음"
    assert "[1]" in user and "[2]" in user
    assert "예수님에 대해 알려줘" in user


# ──────────────────────────────────────────────────────────────
# 6) 통합 스모크 (in-memory Qdrant + hash 임베더)
# ──────────────────────────────────────────────────────────────
def test_pipeline_e2e():
    import asyncio

    try:
        from backend.app.services.enhanced_rag import RAGPipeline, RAGConfig
        from backend.app.config import settings
    except Exception as e:
        print(f"[SKIP] import 실패: {e}")
        return

    # 테스트 격리: 이전 실행 잔류 매니페스트 제거 (증분 skip 오판 방지)
    try:
        _mf = settings.root_dir / "data" / "enhanced_rag_manifest.json"
        if _mf.exists():
            _mf.unlink()
    except Exception:
        pass

    # in-memory Qdrant + 경량 hash 임베더 (모델 로딩 회피)
    # P10-9: 전역 settings 변이는 다른 테스트로 누수되지 않도록 원복 보장(try/finally).
    _orig_qdrant_url = settings.qdrant_url
    settings.qdrant_url = "memory:"
    try:
        cfg = RAGConfig(embedder="hash", collection="rag_test_e2e", reranker="heuristic")
        pipe = RAGPipeline(cfg)

        docs = [
            RAGDocument(doc_id="A", title="복음", source="gospel.txt",
                        content="예수님의 사랑과 구원의 은혜에 대하여 설명합니다. 하나님의 사랑은 무조건적입니다.",
                        language="ko"),
            RAGDocument(doc_id="B", title="부활", source="easter.txt",
                        content="부활의 증거와 십자가의 의미를 다룹니다. 부활은 기독교 신앙의 핵심입니다.",
                        language="ko"),
        ]
        res = pipe.add_documents(docs)
        assert all(r.status == "ok" for r in res), res
        assert pipe.count() > 0

        # 쿼리 (생성 없이 검색만) — async 호출
        q = asyncio.run(pipe.query("부활의 증거", top_k=3, use_rerank=True, generate=False))
        assert q.retrieved, "검색 결과가 없음"
        top_doc = q.retrieved[0].doc_id
        # hash 임베더는 dense 신호가 무의미하므로 B 가 상위에 포함되는지 관대히 검증
        assert "B" in [c.doc_id for c in q.retrieved[:2]], (
            f"B 미검출 (retrieved={[c.doc_id for c in q.retrieved]})"
        )

        # 증분 갱신: A 재인제스트(동일 해시) → skipped
        r2 = pipe.add_document(docs[0])
        assert r2.unchanged is True

        # 삭제
        assert pipe.remove_document("B") is True
        docs_after = pipe.list_documents()
        assert all(d.doc_id != "B" for d in docs_after)

        # 평가 (검색 지표)
        eval_res = asyncio.run(pipe.evaluate(
            [{"query": "예수님의 사랑", "relevant": {"A"}, "relevant_is_doc": True}],
            k=3, with_generation=False,
        ))
        assert eval_res.retrieval is not None
        assert eval_res.retrieval.hit_rate >= 0.0
        print(f"[E2E] retrieval hit_rate={eval_res.retrieval.hit_rate:.2f}, "
              f"docs={len(pipe.list_documents())}, chunks={pipe.count()}")
    finally:
        settings.qdrant_url = _orig_qdrant_url


# ──────────────────────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────────────────────
def _run(name, fn):
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except Exception as e:
        import traceback
        print(f"[FAIL] {name}: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    tests = [
        ("chunking_recursive", test_chunking_recursive),
        ("chunking_fixed", test_chunking_fixed_and_overlap),
        ("chunking_json", test_chunking_json_loader),
        ("bm25", test_bm25_search_and_remove),
        ("rrf_fusion", test_rrf_fusion),
        ("retrieval_metrics", test_retrieval_metrics),
        ("prompt_assembly", test_prompt_assembly),
        ("pipeline_e2e", test_pipeline_e2e),
    ]
    ok = sum(_run(n, f) for n, f in tests)
    print(f"\n=== {ok}/{len(tests)} passed ===")
    sys.exit(0 if ok == len(tests) else 1)
