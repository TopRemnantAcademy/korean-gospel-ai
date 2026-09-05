"""인제스트 오케스트레이터 — 원문을 검색 최적화 청크로 변환 (Stage 1~7 통합).

publish_service 가 이 모듈의 build_index_chunks() 를 호출한다.
각 단계는 settings.ingest_*_enabled feature flag 로 켜고 끈다.

흐름:
    원문(body)
      → Stage 1 정규화 (normalizer)         [규칙, ingest_normalize_enabled]
      → Stage 2 구조화 (restructurer)        [LLM,  ingest_restructure_enabled]
      → Stage 3 청킹 (chunker, 토큰+헤딩)    [항상]
      → Stage 5 메타추출 (cleanup_pipeline)  [규칙]
      → Stage 7 품질 게이트 (quality_gate)   [규칙, ingest_quality_gate_enabled]
      → Stage 4 컨텍스트 강화 (contextualizer)[LLM,  ingest_contextual_enabled]
    → IngestResult(chunks, embed_texts, metadatas_extra, report)

    (실제 실행 순서 기준. 품질게이트는 원문 청크를 대상으로 먼저 실행되어
     차단 시 LLM 컨텍스트강화 비용을 절약하고, 임베딩은 맥락강화본으로 수행)

동기 함수: publish_service 가 스레드 풀에서 호출하므로 LLM 호출은 내부에서
          asyncio 이벤트 루프를 안전하게 확보해 실행한다.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..config import settings
from .chunker import Chunk, chunk_text
from . import normalizer, quality_gate
from .cleanup_pipeline import extract_metadata

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    chunks: list[Chunk]                          # 최종 청크 (품질 통과)
    embed_texts: list[str]                        # 임베딩할 텍스트 (맥락 포함 가능)
    context_prefixes: list[str]                   # 청크별 맥락 (payload용)
    scripture_refs: list[str]                     # 문서 전체 성경구절
    topic_tags: list[str]                         # 문서 전체 주제어
    structured_body: str | None = None            # 구조화 산출물 (있으면)
    blocked: bool = False                          # 품질 게이트 차단?
    report: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _run_async(coro):
    """동기 컨텍스트에서 async 코루틴 실행 (이벤트 루프 안전 확보)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # 이미 루프 안 (드묾) — 새 스레드에서 실행
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()
    return asyncio.run(coro)


def build_index_chunks(
    body: str,
    *,
    title: str = "",
    llm_provider: str | None = None,
) -> IngestResult:
    """원문을 인덱싱 가능한 청크 + 메타데이터로 변환."""
    warnings: list[str] = []
    report: dict = {"stages": []}

    if not body or not body.strip():
        return IngestResult(
            chunks=[], embed_texts=[], context_prefixes=[],
            scripture_refs=[], topic_tags=[],
            blocked=True, report={"error": "empty body"},
        )

    text = body

    # ── Stage 0.5: 청킹 선행 정규화 (ZZ-1 단어결합 + ZZ-3 마침표) ─────────────────
    if settings.ingest_normalize_enabled:
        text = normalizer.preprocess_for_chunking(text)
        report["stages"].append("preprocess_spacing")

    # ── Stage 1: 정규화 (규칙) ───────────────────────────────────────────────
    if settings.ingest_normalize_enabled:
        text = normalizer.normalize_text(text, remove_fillers=True)
        report["stages"].append("normalize")

    # ── Stage 2: 구조화 (LLM, 옵션) ──────────────────────────────────────────
    structured_body = None
    if settings.ingest_restructure_enabled:
        try:
            from .restructurer import restructure_text
            text, info = _run_async(restructure_text(text, title=title, llm_provider=llm_provider))
            structured_body = text
            warnings.extend(info.get("warnings", []))
            report["stages"].append(f"restructure({info.get('windows')}win)")
        except Exception as e:
            logger.warning("구조화 실패 (원문 유지): %s", e)
            warnings.append(f"restructure 실패: {e}")

    # ── Stage 3: 청킹 (토큰 + 헤딩, 항상) ────────────────────────────────────
    chunks = chunk_text(
        text,
        target_tokens=settings.ingest_chunk_target_tokens,
        max_tokens=settings.ingest_chunk_max_tokens,
        min_tokens=settings.ingest_chunk_min_tokens,
        overlap_sentences=settings.ingest_chunk_overlap,  # 취약점 4: 설정값 전달
    )
    report["stages"].append(f"chunk({len(chunks)})")

    # ── Stage 5: 메타데이터 추출 (규칙) ──────────────────────────────────────
    meta = extract_metadata(text)
    scripture_refs = meta.get("scripture_refs", [])
    topic_tags = meta.get("topic_tags", [])

    # ── Stage 7: 품질 게이트 (규칙, 옵션) ────────────────────────────────────
    if settings.ingest_quality_gate_enabled:
        gate = quality_gate.run_quality_gate(chunks)
        chunks = gate.chunks
        warnings.extend(gate.warnings)
        report["quality"] = gate.report
        report["stages"].append("quality_gate")
        if gate.blocked:
            return IngestResult(
                chunks=chunks, embed_texts=[], context_prefixes=[],
                scripture_refs=scripture_refs, topic_tags=topic_tags,
                structured_body=structured_body,
                blocked=True, report=report,
                warnings=warnings + gate.errors,
            )

    # ── Stage 4: 컨텍스트 강화 (LLM, 옵션) ───────────────────────────────────
    embed_texts: list[str]
    context_prefixes: list[str]
    if settings.ingest_contextual_enabled and chunks:
        try:
            from .contextualizer import contextualize_chunks
            ctx_results = _run_async(
                contextualize_chunks(chunks, title=title, llm_provider=llm_provider)
            )
            embed_texts = [r["embed_text"] for r in ctx_results]
            context_prefixes = [r["context_prefix"] for r in ctx_results]
            report["stages"].append("contextual")
        except Exception as e:
            logger.warning("컨텍스트 강화 실패 (본문만 임베딩): %s", e)
            warnings.append(f"contextual 실패: {e}")
            embed_texts = [c.text for c in chunks]
            context_prefixes = ["" for _ in chunks]
    else:
        embed_texts = [c.text for c in chunks]
        context_prefixes = ["" for _ in chunks]

    return IngestResult(
        chunks=chunks,
        embed_texts=embed_texts,
        context_prefixes=context_prefixes,
        scripture_refs=scripture_refs,
        topic_tags=topic_tags,
        structured_body=structured_body,
        blocked=False,
        report=report,
        warnings=warnings,
    )
