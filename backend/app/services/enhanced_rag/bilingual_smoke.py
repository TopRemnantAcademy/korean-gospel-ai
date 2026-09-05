"""이중 저장(중국어 우선) 오프라인 스모크 테스트.

외부 의존성 없는 hash 임베더 + in-memory Qdrant 로 전체 파이프라인을 검증한다.
- 번역(GlossaryTranslator) + 품질 검증(verify_translation) 동작
- 인제스트 시 korean_text / chinese_text / trans_meta 이중 payload 생성
- 중국어 우선 검색(search_primary)이 중국어 번역문으로 매칭되는지 확인
- 설정(BilingualConfig / rag_bilingual_enabled)이 요구사항을 반영하는지 확인

실행:
    python backend/app/services/enhanced_rag/bilingual_smoke.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# backend 디렉토리를 sys.path 에 추가해 `import app` 가능하게 함
_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.config import settings

# 외부 Qdrant 서버 없이 실행 (in-memory 모드)
settings.qdrant_url = "memory:"

from app.services.enhanced_rag.config import BilingualConfig, RAGConfig
from app.services.enhanced_rag.translation import TranslationManager
from app.services.enhanced_rag.types import RAGChunk
from app.services.enhanced_rag.vector_store import RAGVectorStore
from app.services.enhanced_rag.embeddings import RAGEmbedder


async def test_translation_and_verify():
    print("\n--- 1) 번역 + 품질 검증 ---")
    cfg = BilingualConfig(
        enabled=True, primary_lang="zh", source_lang="ko",
        translator="glossary", chinese_embedder="hash",
    )
    mgr = TranslationManager(cfg)
    ko = "예수님은 하나님의 아들이시며 은혜로 구원을 주십니다."
    res, meta = await mgr.translate_chunk(ko, None)
    assert "耶稣" in res.zh_text, res.zh_text
    assert meta["engine"] == "glossary-v1", meta
    assert "quality_score" in meta and meta["quality_score"] is not None
    assert meta["review_status"] in ("auto", "flagged")
    print("  KO  :", ko)
    print("  ZH  :", res.zh_text)
    print("  meta:", {k: meta[k] for k in
                     ("engine", "glossary_version", "review_status", "quality_score",
                      "glossary_compliance", "applied_terms")})
    print("  [OK]")


def test_store_dual_payload():
    print("\n--- 2) 이중 저장 payload + 중국어 우선 검색 ---")
    cfg = RAGConfig(embedder="hash")
    cfg.bilingual = BilingualConfig(
        enabled=True, primary_lang="zh", source_lang="ko",
        translator="glossary", chinese_embedder="hash",
    )
    emb = RAGEmbedder("hash")
    store = RAGVectorStore(cfg, emb)

    chunk = RAGChunk(
        chunk_id="doc1::0", doc_id="doc1",
        text="성령께서 교회에 은혜를 주십니다.",
        chunk_index=0, section="", language="ko",
        source="smoke", title="스모크테스트", content_hash="h1",
    )
    store.ingest([chunk])

    docs = store.list_documents()
    assert any(d.doc_id == "doc1" for d in docs), docs

    pid = store._manifest["doc1"]["chunk_ids"][0]
    pt = store.store.get(pid)
    assert pt is not None
    payload = pt.metadata
    assert payload.get("korean_text") == chunk.text
    assert "圣灵" in payload["chinese_text"], payload["chinese_text"]
    assert payload["primary_lang"] == "zh"
    assert payload["trans_meta"]["review_status"] in ("auto", "flagged")

    print("  korean_text :", payload["korean_text"])
    print("  chinese_text:", payload["chinese_text"])
    print("  primary_lang:", payload["primary_lang"])
    print("  trans_meta  :",
          {k: payload["trans_meta"][k]
           for k in ("engine", "review_status", "quality_score", "glossary_compliance")})

    # 중국어 우선 검색: 번역문으로 임베딩된 primary 벡터 사용
    zh = payload["chinese_text"]
    vec = emb.embed_query(zh)
    res = store.search_primary(vec, top_k=3)
    assert res and res[0]["doc_id"] == "doc1", res
    assert "圣灵" in res[0]["text"]
    print("  search_primary 반환:", res[0]["text"])
    print("  [OK]")


def test_config_reflects_requirements():
    print("\n--- 3) 설정 요구사항 반영 확인 ---")
    assert settings.rag_bilingual_enabled is True
    bc = BilingualConfig()
    assert bc.primary_lang == "zh"
    assert bc.source_lang == "ko"
    assert bc.translator == "llm"
    assert bc.glossary_version == "v1"
    assert bc.embed_source_vector is True
    assert bc.auto_verify is True
    assert bc.context_preservation is True
    print("  rag_bilingual_enabled =", settings.rag_bilingual_enabled)
    print("  BilingualConfig 기본값:", bc.model_dump())
    print("  [OK]")


if __name__ == "__main__":
    print("=== 이중 저장(중국어 우선) 오프라인 스모크 테스트 ===")
    asyncio.run(test_translation_and_verify())
    test_store_dual_payload()
    test_config_reflects_requirements()
    print("\n✅ 모든 검증 통과")
