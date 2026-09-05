"""독립형 RAG 엔진 - 다른 시스템에서 모듈로 재사용 가능.

FastAPI나 DB에 의존하지 않는 순수 Python 라이브러리 형태의 RAG 인터페이스.
번역 시스템, 더빙 시스템, 챗봇 등 어떤 시스템에서도 import 해서 사용 가능.

사용법 (다른 프로젝트에서):
```python
from app.services.rag_engine import RAGEngine

# 초기화
engine = RAGEngine(embedder_name="bge_m3")  # 다국어는 bge_m3 권장

# 검색
results = engine.search(
    query="예수님은 누구신가요?",
    top_k=5,
    target_lang="ko",  # ko / en / zh / ja
    enable_mmr=True,
    enable_compression=True,
)

# 결과 활용
for r in results:
    print(r["score"], r["content"][:50])
    print(r["source_title"])
```

번역 시스템 연동 예시:
```python
# 한국어 설교 녹취문을 일본어로 번역할 때
# 관련 컨텍스트를 검색해서 번역 정확도 향상
context = engine.search(
    korean_sermon_text[:200],  # 번역할 텍스트 일부를 쿼리로 사용
    top_k=3,
    target_lang="ja",
)
# context 를 번역 모델에 함께 제공하면 전문 용어 정확도 향상
```
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


_SUPPORTED_LANGS = {"ko", "en", "zh", "ja"}
_MULTILINGUAL_EMBEDDERS = {"bge_m3", "e5", "voyage", "hf_inference"}


@dataclass
class RAGResult:
    """RAG 검색 결과 항목."""
    id: str
    content: str
    score: float
    source_title: str
    source_type: str
    reliability_score: float
    relevant_sentences: list[str] = field(default_factory=list)
    compression_confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGResponse:
    """RAG 검색 응답 전체."""
    results: list[RAGResult]
    query: str
    target_lang: str
    embedder_used: str
    total_found: int
    elapsed_ms: int = 0

    def to_dicts(self) -> list[dict]:
        return [asdict(r) for r in self.results]


class RAGEngine:
    """독립형 RAG 엔진.

    외부 시스템에서 쉽게 재사용할 수 있도록 설계된 인터페이스.
    복잡한 내부 로직을 숨기고 간단한 메서드만 노출.
    """

    def __init__(
        self,
        embedder_name: str = "bge_m3",
        target_lang: str = "ko",
        collection_name: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
    ):
        """RAG 엔진 초기화.

        Args:
            embedder_name: 사용할 임베더 (bge_m3 추천 - 다국어 지원)
            target_lang: 기본 대상 언어
            collection_name: Qdrant 컬렉션명 (기본: 자동 생성)
            qdrant_url: Qdrant 서버 URL (없으면 환경변수에서 읽음)
            qdrant_api_key: Qdrant API 키 (없으면 환경변수에서 읽음)
        """
        if target_lang not in _SUPPORTED_LANGS:
            raise ValueError(f"지원하지 않는 언어: {target_lang}. "
                           f"지원 언어: {_SUPPORTED_LANGS}")

        self.default_lang = target_lang

        effective_embedder = embedder_name
        if target_lang != "ko" and embedder_name not in _MULTILINGUAL_EMBEDDERS:
            effective_embedder = "bge_m3"

        self.embedder_name = effective_embedder
        self.collection_name = collection_name
        self._qdrant_url = qdrant_url
        self._qdrant_api_key = qdrant_api_key

        self._retriever = None
        self._search_engine = None
        self._initialized = False

    def _ensure_initialized(self):
        """필요할 때 초기화 (지연 로딩)."""
        if self._initialized:
            return

        from .retriever import get_retriever
        from .search_v4 import get_search_engine

        if self._qdrant_url:
            os.environ.setdefault("QDRANT_URL", self._qdrant_url)
        if self._qdrant_api_key:
            os.environ.setdefault("QDRANT_API_KEY", self._qdrant_api_key)

        self._retriever = get_retriever(self.embedder_name, collection=self.collection_name)
        self._search_engine = get_search_engine(self._retriever)
        self._initialized = True

    async def search(
        self,
        query: str,
        top_k: int = 5,
        target_lang: Optional[str] = None,
        enable_mmr: bool = True,
        enable_compression: bool = True,
        enable_explain: bool = False,
        profile: Optional[dict] = None,
    ) -> RAGResponse:
        """고급 검색 (v4 엔진).

        Args:
            query: 검색 쿼리 (어떤 언어든 가능)
            top_k: 반환할 결과 개수
            target_lang: 결과 대상 언어 (기본: 초기화시 설정)
            enable_mmr: MMR 다양성 랭킹 사용 여부
            enable_compression: 컨텍스트 압축 사용 여부
            enable_explain: 검색 설명 포함 여부
            profile: 사용자 프로필 (옵션)

        Returns:
            RAGResponse 객체
        """
        import time
        t0 = time.time()

        self._ensure_initialized()

        lang = target_lang or self.default_lang
        if lang not in _SUPPORTED_LANGS:
            lang = self.default_lang

        enriched = await self._search_engine.search(
            query=query,
            top_k=top_k,
            enable_mmr=enable_mmr,
            enable_compression=enable_compression,
            enable_explain=enable_explain,
            profile=profile,
        )

        results: list[RAGResult] = []
        for item in enriched:
            content = item.text
            rel_sentences: list[str] = []
            conf = 0.0

            if enable_compression and item.compressed_context:
                content = item.compressed_context.compressed_text
                rel_sentences = item.compressed_context.relevant_sentences
                conf = item.compressed_context.confidence

            results.append(RAGResult(
                id=item.id,
                content=content,
                score=float(item.final_score),
                source_title=item.source_title,
                source_type=item.source_type,
                reliability_score=float(item.reliability_score),
                relevant_sentences=rel_sentences,
                compression_confidence=float(conf),
                metadata=item.metadata,
            ))

        elapsed = int((time.time() - t0) * 1000)

        return RAGResponse(
            results=results,
            query=query,
            target_lang=lang,
            embedder_used=self.embedder_name,
            total_found=len(results),
            elapsed_ms=elapsed,
        )

    async def simple_search(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """가장 간단한 검색 - 딕셔너리 리스트로 즉시 반환.

        번역/더빙 시스템 등에서 컨텍스트만 간단히 가져올 때 사용.
        """
        resp = await self.search(
            query=query,
            top_k=top_k,
            enable_mmr=True,
            enable_compression=True,
        )
        return [
            {
                "content": r.content,
                "score": r.score,
                "source": r.source_title,
            }
            for r in resp.results
        ]

    def index_documents(
        self,
        folder_path: str,
        *,
        reset: bool = False,
    ) -> dict:
        """폴더 내 문서들을 일괄 인덱싱.

        Args:
            folder_path: 문서 폴더 경로 (.txt, .md 파일 지원)
            reset: 기존 컬렉션을 지우고 새로 시작할지 여부

        Returns:
            인덱싱 결과 요약
        """
        self._ensure_initialized()

        from ..services.chunker import chunk_text
        from ..services.embedding.factory import get_embedder
        from ..services.vector_store import QdrantStore
        from ..config import settings
        import uuid

        root = Path(folder_path)
        if not root.exists():
            return {"ok": False, "error": f"폴더를 찾을 수 없음: {root}"}

        suffixes = {".txt", ".md"}
        paths = [p for p in root.iterdir()
                 if p.is_file() and p.suffix.lower() in suffixes]

        if not paths:
            return {"ok": False, "error": "텍스트 파일이 없음"}

        embedder = get_embedder(self.embedder_name)
        store = self._retriever.store if hasattr(self._retriever, 'store') else QdrantStore(
            self.embedder_name, dim=embedder.dim
        )

        if reset:
            store.delete_collection()

        total_chunks = 0
        total_files = 0
        errors = []

        for path in paths:
            try:
                text = path.read_text(encoding='utf-8', errors='replace').strip()
                if len(text) < 30:
                    continue

                chunks = chunk_text(
                    text,
                    target_tokens=settings.ingest_chunk_target_tokens,
                    max_tokens=settings.ingest_chunk_max_tokens,
                    min_tokens=settings.ingest_chunk_min_tokens,
                    overlap_sentences=settings.ingest_chunk_overlap,
                )
                if not chunks:
                    continue

                texts = [c.text for c in chunks]
                vectors = embedder.embed_documents(texts)
                ids = [str(uuid.uuid4()) for _ in chunks]
                metas = [
                    {
                        "title": path.name,
                        "source_file": path.name,
                        "doc_type": "corpus",
                        "chunk_seq": c.chunk_id,
                    }
                    for c in chunks
                ]

                store.upsert(
                    ids=ids,
                    texts=texts,
                    dense_vecs=vectors.tolist(),
                    metadatas=metas,
                )

                total_chunks += len(chunks)
                total_files += 1
            except Exception as e:
                errors.append(f"{path.name}: {e}")

        count = store._client.get_collection(store.collection).points_count if store._client else 0

        return {
            "ok": True,
            "files_indexed": total_files,
            "total_chunks": total_chunks,
            "total_points": count,
            "errors": errors,
        }


def create_rag_engine(
    embedder: str = "bge_m3",
    target_lang: str = "ko",
    **kwargs,
) -> RAGEngine:
    """RAG 엔진 팩토리 함수.

    가장 간편하게 RAG 엔진을 생성하는 방법.

    Args:
        embedder: 임베더 이름 (다국어면 bge_m3 추천)
        target_lang: 기본 대상 언어
        **kwargs: 추가 옵션 (collection_name, qdrant_url, 등)

    Returns:
        RAGEngine 인스턴스
    """
    return RAGEngine(
        embedder_name=embedder,
        target_lang=target_lang,
        **kwargs,
    )


class TranslationRAGHelper:
    """번역 시스템용 RAG 헬퍼.

    한국어 콘텐츠를 다른 언어로 번역할 때,
    관련 컨텍스트를 검색해서 번역 품질과 용어 정확도를 높여줌.

    사용 예:
    ```python
    helper = TranslationRAGHelper(target_lang="ja")

    # 번역할 한국어 텍스트의 주제와 관련된 컨텍스트 검색
    context = await helper.get_translation_context(korean_sermon_text)

    # 번역 프롬프트에 컨텍스트를 추가해서 전문 용어 정확도 향상
    translation = await llm.translate(
        korean_sermon_text,
        context=context,
        source_lang="ko",
        target_lang="ja",
    )
    ```
    """

    def __init__(
        self,
        target_lang: str = "en",
        embedder: str = "bge_m3",
        top_k: int = 3,
    ):
        self.target_lang = target_lang
        self.engine = RAGEngine(embedder_name=embedder, target_lang=target_lang)
        self.top_k = top_k

        self._context_prompts = {
            "en": (
                "Below is relevant context from Korean Christian materials. "
                "Use this to ensure accurate translation of theological terms "
                "and maintain consistent terminology.\n\n"
            ),
            "zh": (
                "以下是韩国基督教资料中的相关上下文。"
                "请参考这些内容，确保神学术语的翻译准确性，"
                "并保持用词一致。\n\n"
            ),
            "ja": (
                "以下は韓国のキリスト教資料からの関連コンテキストです。"
                "これらを参考にして、神学用語の翻訳正確性を確保し、"
                "用語の一貫性を保ってください。\n\n"
            ),
        }

    async def get_translation_context(
        self,
        source_text: str,
        *,
        excerpt_chars: int = 500,
    ) -> str:
        """번역할 텍스트와 관련된 컨텍스트를 검색해서 프롬프트 형태로 반환.

        Args:
            source_text: 번역할 원본 텍스트 (한국어)
            excerpt_chars: 컨텍스트 검색에 사용할 텍스트 앞부분 길이

        Returns:
            번역 프롬프트에 추가할 컨텍스트 문자열
        """
        query = source_text[:excerpt_chars]
        results = await self.engine.simple_search(query, top_k=self.top_k)

        if not results:
            return ""

        header = self._context_prompts.get(
            self.target_lang,
            self._context_prompts["en"],
        )

        parts = [header]
        for i, r in enumerate(results, 1):
            parts.append(f"[Reference {i} - {r['source']}]")
            parts.append(r["content"][:300])
            parts.append("")

        return "\n".join(parts)

    def build_translation_prompt(
        self,
        source_text: str,
        context: Optional[str] = None,
    ) -> str:
        """완전한 번역 프롬프트 생성.

        Args:
            source_text: 번역할 원본 텍스트
            context: get_translation_context() 로 얻은 컨텍스트

        Returns:
            LLM 에 전달할 번역 프롬프트
        """
        if context is None:
            context = ""

        lang_names = {
            "en": "English",
            "zh": "Simplified Chinese",
            "ja": "Japanese",
            "ko": "Korean",
        }

        target_name = lang_names.get(self.target_lang, "English")

        prompt = ""
        if context:
            prompt += context + "\n---\n\n"

        prompt += f"Translate the following Korean text to {target_name}.\n"
        prompt += "Maintain the tone and style of the original.\n"
        prompt += "Use consistent theological terminology.\n\n"
        prompt += f"[Korean Source]\n{source_text}\n\n"
        prompt += f"[{target_name} Translation]\n"

        return prompt
