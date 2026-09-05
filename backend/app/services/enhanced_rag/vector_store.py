"""Enhanced RAG — 벡터 스토어 어댑터 (Qdrant + BM25 + 증분 갱신).

책임:
- 밀집(dense) 벡터: 기존 QdrantStore 재사용 (별도 컬렉션 isolated)
- 희소(sparse) 벡터: 패키지 내 SimpleBM25 (키워드 검색, 외부 의존 없음)
- 증분 문서 갱신: 같은 doc_id 재인제스트 시 기존 청크 삭제 후 교체
- 문서 메타데이터 매니페스트 영속화 (data/enhanced_rag_manifest.json)
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from collections import defaultdict
from typing import Optional, Sequence

from ...config import settings
from ..vector_store import QdrantStore

from .bm25 import SimpleBM25, tokenize
from .config import RAGConfig
from .embeddings import RAGEmbedder
from .types import DocInfo, RAGChunk
from .translation import TranslationManager

logger = logging.getLogger(__name__)

_MANIFEST_PATH = settings.root_dir / "data" / "enhanced_rag_manifest.json"


class RAGVectorStore:
    def __init__(
        self,
        config: RAGConfig,
        embedder: RAGEmbedder,
        *,
        source_embedder: RAGEmbedder | None = None,
        extra_vector_configs: dict | None = None,
    ):
        self.config = config
        self.embedder = embedder            # primary(중국어) 임베더
        self.bilingual = config.bilingual
        self.primary_lang = self.bilingual.primary_lang if self.bilingual.enabled else config.language
        self.collection = config.collection_name()
        self.store = QdrantStore(
            embedder_name=embedder.name,
            dim=embedder.dim,
            collection=self.collection,
            extra_vectors=extra_vector_configs,
        )
        self.bm25 = SimpleBM25()
        self._lock = threading.RLock()

        # 이중 저장: 원문 언어용 명명 벡터(dense_ko) 지원 여부
        self.source_embedder = source_embedder
        self.has_source_vector = bool(source_embedder) and self.bilingual.enabled

        # 번역 매니저 (이중 저장 활성 시에만)
        self.translation_mgr: TranslationManager | None = None
        if self.bilingual.enabled:
            try:
                self.translation_mgr = TranslationManager(self.bilingual)
            except Exception as e:
                logger.warning("[rag-store] 번역 매니저 초기화 실패(번역 비활성): %s", e)

        # 매니페스트: {doc_id: {title, source, language, chunk_count, content_hash, chunk_ids}}
        self._manifest: dict[str, dict] = self._load_manifest()
        # 청크 메타 인메모리 캐시 (BM25 경로에서 실제 텍스트/메타 복원용)
        self._chunk_meta: dict[str, dict] = {}
        self._rebuild_bm25()

    # ──────────────────────────────────────────────────────────────
    # 매니페스트 (문서 메타 영속)
    # ──────────────────────────────────────────────────────────────
    def _load_manifest(self) -> dict:
        try:
            if _MANIFEST_PATH.exists():
                data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
                return data.get(self.collection, {})
        except Exception as e:
            logger.warning("[rag-store] 매니페스트 로드 실패: %s", e)
        return {}

    def _save_manifest(self) -> None:
        try:
            _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            full = {}
            if _MANIFEST_PATH.exists():
                try:
                    full = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
                except Exception:
                    full = {}
            full[self.collection] = self._manifest
            _MANIFEST_PATH.write_text(
                json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("[rag-store] 매니페스트 저장 실패: %s", e)

    def _rebuild_bm25(self) -> None:
        """Qdrant 에서 청크 텍스트를 scroll 하여 BM25 를 재구축 (재기동 후 정합성)."""
        client = getattr(self.store, "_client", None)
        if client is None:
            return
        try:
            offset = None
            while True:
                pts, offset = client.scroll(
                    collection_name=self.collection,
                    with_payload=True,
                    with_vectors=False,
                    limit=256,
                    offset=offset,
                )
                for p in pts:
                    payload = p.payload or {}
                    text = payload.get("text", "")
                    cid = str(p.id)
                    if text:
                        self.bm25.add(cid, tokenize(text))
                        self._chunk_meta[cid] = dict(payload)
                if offset is None or not pts:
                    break
            logger.info("[rag-store] BM25 재구축: %d 청크", len(self.bm25))
        except Exception as e:
            logger.debug("[rag-store] BM25 재구축 스킵: %s", e)

    # ──────────────────────────────────────────────────────────────
    # 인제스트 (증분 갱신)
    # ──────────────────────────────────────────────────────────────
    def ingest(self, chunks: Sequence[RAGChunk]) -> dict[str, int]:
        if not chunks:
            return {}
        by_doc: dict[str, list[RAGChunk]] = defaultdict(list)
        for c in chunks:
            by_doc[c.doc_id].append(c)

        updated: dict[str, int] = {}
        with self._lock:
            for doc_id, chs in by_doc.items():
                self._run_async(self._replace_doc(chs))
                updated[doc_id] = len(chs)
            self._save_manifest()
        return updated

    # ──────────────────────────────────────────────────────────────
    # 인제스트 (외부 정제 데이터 직행 / Fast-Track)
    #   - 번역/청킹 생략. 제공된 korean_text / chinese_text 를 그대로 사용.
    #   - dense(bge_m3) = 중국어, dense_ko(kure) = 한국어 이중 벡터.
    # ──────────────────────────────────────────────────────────────
    def ingest_external(self, documents: Sequence[dict]) -> dict[str, int]:
        """외부에서 완전히 정제·번역된 청크를 직접 적재 (LLM 호출 0회).

        documents: List[{
            doc_id:   str  (선택, 미입력 시 자동 생성)
            title:    str
            source:   str  (기본 "external")
            language: str  (기본 "ko")
            content_hash: str (선택)
            chunks:   List[{
                chunk_index: int,
                korean_text: str,   # 원문 (필수, source of truth)
                chinese_text: str,  # 번역문 (비어도 자동 폴백)
                topic_tags:  List[str],
                scripture_refs: List[str],
                summary: str,
            }]
        }]
        반환: {doc_id: chunk_count}
        """
        if not documents:
            return {}
        grouped: dict[str, list[RAGChunk]] = defaultdict(list)
        zh_map: dict[str, list[str]] = defaultdict(list)

        for doc in documents:
            doc_id = (doc.get("doc_id") or "").strip() or f"ext_{uuid.uuid4().hex[:12]}"
            title = (doc.get("title") or "").strip() or doc_id
            source = doc.get("source", "external")
            language = doc.get("language", "ko")
            content_hash = doc.get("content_hash", "")
            for i, ch in enumerate(doc.get("chunks", [])):
                chunk_index = ch.get("chunk_index", i)
                korean_text = (ch.get("korean_text") or "").strip()
                if not korean_text:
                    # 원문 없으면 chinese 를 원문으로 대체 (단일언어 안전)
                    korean_text = (ch.get("chinese_text") or "").strip()
                rc = RAGChunk(
                    chunk_id=f"{doc_id}::{chunk_index}",
                    doc_id=doc_id,
                    text=korean_text,
                    chunk_index=chunk_index,
                    section=ch.get("section", ""),
                    language=language,
                    source=source,
                    title=title,
                    content_hash=content_hash,
                    metadata={
                        "topic_tags": ch.get("topic_tags", []) or [],
                        "scripture_refs": ch.get("scripture_refs", []) or [],
                        "summary": ch.get("summary", "") or "",
                    },
                )
                grouped[doc_id].append(rc)
                zh_map[doc_id].append((ch.get("chinese_text") or "").strip() or korean_text)

        updated: dict[str, int] = {}
        with self._lock:
            for doc_id, chs in grouped.items():
                self._run_async(self._replace_doc_external(chs, zh_map[doc_id]))
                updated[doc_id] = len(chs)
            self._save_manifest()
        return updated

    async def _replace_doc_external(self, chs: list[RAGChunk], zh_texts: list[str]) -> None:
        """Fast-Track: 제공된 chinese_text 를 번역 없이 그대로 사용 (이중 벡터).

        이중 저장 로직은 _replace_doc 와 동일하되, LLM 번역(_translate) 단계를
        생략하고 호출자가 준 chinese_text 를 주 검색 벡터(dense, bge_m3)로 사용.
        source_embedder(kure) 가 있으면 dense_ko 도 병행 생성(한국어 쿼리 지원).
        """
        # 1) 기존 청크 제거 (증분 갱신 — 동일 doc_id 재업로드 시 교체)
        existing = self._manifest.get(chs[0].doc_id)
        if existing:
            old_ids = existing.get("chunk_ids", [])
            if old_ids:
                self.store.delete(old_ids)
                for cid in old_ids:
                    self.bm25.remove(cid)
                    self._chunk_meta.pop(cid, None)

        # 주 검색 벡터 = 제공된 중국어 임베딩 (중국어 사용자 다수 가정)
        primary_texts = [z or c.text for z, c in zip(zh_texts, chs)]
        primary_vecs = self.embedder.embed_documents(primary_texts)

        # 원문 언어 벡터(dense_ko) 병행 — 한국어 쿼리 지원 (source_embedder 있을 때만)
        extra_vecs: dict | None = None
        if self.source_embedder is not None:
            ko_vecs = self.source_embedder.embed_documents([c.text for c in chs])
            extra_vecs = {"dense_ko": ko_vecs.tolist()}

        ids = [str(uuid.uuid4()) for _ in chs]
        trans_meta_base = {
            "engine": "external", "glossary_version": "",
            "review_status": "auto", "quality_score": None, "target_lang": "zh",
        }
        metas = [self._meta(c, zh, trans_meta_base) for c, zh in zip(chs, primary_texts)]

        self.store.upsert(
            ids=ids,
            dense_vecs=primary_vecs.tolist(),
            texts=primary_texts,
            metadatas=metas,
            sparse_vecs=None,
            extra_vecs=extra_vecs,
        )

        # BM25 는 중국어 표시 텍스트 기준 → 중국어 키워드 검색 지원
        for c, zh, pid in zip(chs, primary_texts, ids):
            self.bm25.add(pid, tokenize(zh))
            self._chunk_meta[pid] = self._meta(c, zh, trans_meta_base) | {"text": zh}

        self._update_manifest(chs, ids)

    @staticmethod
    def _run_async(coro):
        """sync 컨텍스트에서 async 번역 코루틴 실행 (이벤트 루프 충돌 방지).

        - 실행 중인 루프가 없으면 asyncio.run 으로 현재 스레드에서 실행.
        - 이미 루프가 돌고 있으면(예: FastAPI async 핸들러) 별도 스레드에서
          새 이벤트 루프로 실행 → AsyncOpenAI 클라이언트의 cross-loop 바인딩
          오류 차단. 이때 LLM 인스턴스 캐시를 갱신해 새 루프에 바인딩되게 함.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            from ..llm.factory import clear_llm_cache
            clear_llm_cache()  # R-1: 새 이벤트 루프에 LLM 인스턴스 캐시 재바인딩
            return asyncio.run(coro)
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            return ex.submit(RAGVectorStore._loop_run, coro).result()

    @staticmethod
    def _loop_run(coro):
        from ..llm.factory import clear_llm_cache

        clear_llm_cache()
        return asyncio.run(coro)

    async def _replace_doc(self, chs: list[RAGChunk]) -> None:
        # 1) 기존 청크 제거 (증분 갱신)
        existing = self._manifest.get(chs[0].doc_id)
        if existing:
            old_ids = existing.get("chunk_ids", [])
            if old_ids:
                self.store.delete(old_ids)
                for cid in old_ids:
                    self.bm25.remove(cid)
                    self._chunk_meta.pop(cid, None)

        # 이중 저장 비활성 → 기존 동작과 완전히 동일
        if not self.bilingual.enabled:
            texts = [c.text for c in chs]
            vecs = self.embedder.embed_documents(texts)
            ids = [str(uuid.uuid4()) for _ in chs]
            metas = [self._meta(c) for c in chs]
            self.store.upsert(
                ids=ids, dense_vecs=vecs.tolist(), texts=texts,
                metadatas=metas, sparse_vecs=None,
            )
            for c, pid in zip(chs, ids):
                self.bm25.add(pid, tokenize(c.text))
                self._chunk_meta[pid] = self._meta(c) | {"text": c.text}
            self._update_manifest(chs, ids)
            return

        # ── 이중 저장(중국어 우선) 경로 ──
        # 청크별 번역 + 검증 + 메타 구성
        enriched = []
        for i, c in enumerate(chs):
            neighbor_ctx = None
            if self.bilingual.context_preservation:
                prev_t = chs[i - 1].text if i > 0 else ""
                next_t = chs[i + 1].text if i + 1 < len(chs) else ""
                neighbor_ctx = f"{prev_t}\n{next_t}" if (prev_t or next_t) else None
            zh_text, trans_meta = await self._translate(c.text, neighbor_ctx)
            enriched.append((c, zh_text, trans_meta))

        # 주 검색 벡터 = 중국어 번역문 임베딩 (중국어 사용자 다수 가정)
        primary_texts = [e[1] for e in enriched]
        primary_vecs = self.embedder.embed_documents(primary_texts)

        # 원문 언어 벡터(dense_ko) 병행 — 한국어 쿼리 지원
        extra_vecs: dict | None = None
        if self.has_source_vector and self.source_embedder is not None:
            ko_vecs = self.source_embedder.embed_documents([c.text for c in chs])
            extra_vecs = {"dense_ko": ko_vecs.tolist()}

        # 표시 텍스트 = 중국어(주 사용자), 원문은 korean_text 로 보존
        display_texts = primary_texts
        ids = [str(uuid.uuid4()) for _ in chs]
        metas = [self._meta(e[0], e[1], e[2]) for e in enriched]
        self.store.upsert(
            ids=ids,
            dense_vecs=primary_vecs.tolist(),
            texts=display_texts,
            metadatas=metas,
            sparse_vecs=None,
            extra_vecs=extra_vecs,
        )

        # BM25 는 주 표시 텍스트(중국어) 기준 → 중국어 키워드 검색 지원
        for e, pid in zip(enriched, ids):
            c, zh_text, _ = e
            self.bm25.add(pid, tokenize(zh_text))
            self._chunk_meta[pid] = self._meta(c, zh_text, e[2]) | {"text": zh_text}

        self._update_manifest(chs, ids)

    async def _translate(self, ko_text: str, neighbor_ctx: str | None):
        """원문→중국어 번역 + 검증. (zh_text, trans_meta) 반환.

        번역 매니저가 없거나 번역 호출이 실패하면 원문(KO)을 그대로 반환 폴백.
        → 하나의 청크 번역 실패가 문서 전체 인제스트를 죽이지 않도록 보장
          (대체옵션 확보). 번역이 불가능해도 검색 인덱스는 항상 생성된다.
        """
        if self.translation_mgr is None:
            # 번역 매니저 없으면 원문을 그대로 표시(폴백)
            return ko_text, {
                "engine": "none", "glossary_version": "",
                "review_status": "auto", "quality_score": None,
                "target_lang": "ko",
            }
        try:
            res, trans_meta = await self.translation_mgr.translate_chunk(ko_text, neighbor_ctx)
            return res.zh_text, trans_meta
        except Exception as e:
            logger.warning("[rag-store] 청크 번역 실패 → 원문(KO) 폴백: %s", e)
            return ko_text, {
                "engine": "fallback_source", "glossary_version": "",
                "review_status": "auto", "quality_score": None,
                "target_lang": "ko",
            }

    def _update_manifest(self, chs: list[RAGChunk], ids: list[str]) -> None:
        first = chs[0]
        self._manifest[first.doc_id] = {
            "title": first.title,
            "source": first.source,
            "language": first.language,
            "chunk_count": len(chs),
            "content_hash": first.content_hash,
            "chunk_ids": ids,
        }

    @staticmethod
    def _meta(c: RAGChunk, chinese_text: str | None = None, trans_meta: dict | None = None) -> dict:
        base = {
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "source": c.source,
            "title": c.title,
            "section": c.section,
            "language": c.language,
            "chunk_index": c.chunk_index,
            "content_hash": c.content_hash,
            **c.metadata,
        }
        if chinese_text is not None and trans_meta is not None:
            # 이중 저장 메타: 원문 불변 보존 + 번역 + 검증 태그
            base.update({
                "korean_text": c.text,            # source of truth (불변)
                "chinese_text": chinese_text,     # 번역문(표시/검색)
                "primary_lang": trans_meta.get("target_lang", "zh"),
                "trans_meta": trans_meta,         # engine/version/quality/review
            })
        return base

    # ──────────────────────────────────────────────────────────────
    # 삭제 / 목록 / 카운트
    # ──────────────────────────────────────────────────────────────
    def delete_doc(self, doc_id: str) -> bool:
        with self._lock:
            existing = self._manifest.pop(doc_id, None)
            if not existing:
                return False
            old_ids = existing.get("chunk_ids", [])
            if old_ids:
                self.store.delete(old_ids)
                for cid in old_ids:
                    self.bm25.remove(cid)
                    self._chunk_meta.pop(cid, None)
            self._save_manifest()
            return True

    def list_documents(self) -> list[DocInfo]:
        out: list[DocInfo] = []
        for doc_id, m in self._manifest.items():
            out.append(
                DocInfo(
                    doc_id=doc_id,
                    title=m.get("title", ""),
                    source=m.get("source", ""),
                    language=m.get("language", "ko"),
                    chunk_count=m.get("chunk_count", 0),
                    content_hash=m.get("content_hash", ""),
                )
            )
        return out

    def count(self) -> int:
        return self.store.count()

    # ──────────────────────────────────────────────────────────────
    # 검색 (dense / keyword)
    # ──────────────────────────────────────────────────────────────
    def search_dense(
        self, query_vec: Sequence[float], *, top_k: int = 40, allowed_ids: Optional[set] = None
    ) -> list[dict]:
        pts = self.store.search_dense(list(query_vec), top_k=top_k)
        out = []
        for p in pts:
            if allowed_ids is not None and p.id not in allowed_ids:
                continue
            meta = p.metadata or {}
            out.append(
                {
                    "chunk_id": meta.get("chunk_id", p.id),
                    "doc_id": meta.get("doc_id", ""),
                    "text": p.text,
                    "score": float(p.score),
                    "meta": meta,
                }
            )
        return out

    def search_primary(
        self, query_vec: Sequence[float], *, top_k: int = 40, allowed_ids: Optional[set] = None
    ) -> list[dict]:
        """주 검색 벡터(dense, 중국어 우선) 검색."""
        return self.search_dense(query_vec, top_k=top_k, allowed_ids=allowed_ids)

    def search_source(
        self, query_vec: Sequence[float], *, top_k: int = 40, allowed_ids: Optional[set] = None
    ) -> list[dict]:
        """원문 언어 벡터(dense_ko) 검색 — 한국어 쿼리 지원. 미설정 시 [].

        주의: 호출 전 has_source_vector 체크 권장.
        """
        if not self.has_source_vector:
            return []
        pts = self.store.search_dense(list(query_vec), top_k=top_k, using="dense_ko")
        out = []
        for p in pts:
            if allowed_ids is not None and p.id not in allowed_ids:
                continue
            meta = p.metadata or {}
            out.append(
                {
                    "chunk_id": meta.get("chunk_id", p.id),
                    "doc_id": meta.get("doc_id", ""),
                    "text": meta.get("korean_text", p.text),
                    "score": float(p.score),
                    "meta": meta,
                }
            )
        return out

    def search_keyword(
        self, query_tokens: list[str], *, top_k: int = 40, allowed_ids: Optional[set] = None
    ) -> list[dict]:
        ranked = self.bm25.search(query_tokens, top_k=top_k)
        out = []
        for cid, score in ranked:
            if allowed_ids is not None and cid not in allowed_ids:
                continue
            meta = self._chunk_meta.get(cid) or self._meta_by_chunk(cid)
            out.append(
                {
                    "chunk_id": meta.get("chunk_id", cid),
                    "doc_id": meta.get("doc_id", ""),
                    "text": meta.get("text", ""),
                    "score": float(score),
                    "meta": meta,
                }
            )
        return out

    def _meta_by_chunk(self, chunk_id: str) -> dict:
        """매니페스트 청크_ids → doc 매핑으로 간이 메타 복원 (BM25 미복원 시 폴백)."""
        meta = {"chunk_id": chunk_id}
        for doc_id, m in self._manifest.items():
            if chunk_id in m.get("chunk_ids", []):
                meta.update(
                    {
                        "doc_id": doc_id,
                        "source": m.get("source", ""),
                        "title": m.get("title", ""),
                        "language": m.get("language", "ko"),
                    }
                )
                break
        return meta
