"""컨텍스트 강화 — 청크에 위치 맥락 한 줄 부착 (Stage 4, LLM).

Anthropic "Contextual Retrieval" 기법 (LLM 무관, DeepSeek로 구현).
대명사·생략이 많은 한국어 설교에서 검색 정확도를 크게 높인다.

저장 구조:
    embed_text   = 맥락 + "\n\n" + 본문   → 이것으로 임베딩 (검색용)
    display_text = 본문만                   → 사용자/LLM 표시용

비용 통제: 섹션 단위로 맥락 1회 생성 후 같은 섹션 청크끼리 공유.
           → 호출 = 섹션 수 (청크 수보다 훨씬 적음).
실패 시: 맥락 없이 본문만 사용 (fail-open, 검색은 계속 동작).

LLM 독립: chat_with_fallback() 경유.
"""
from __future__ import annotations

import logging

from ..config import settings
from .chunker import Chunk
from .llm.base import Message
from .llm.fallback import chat_with_fallback

logger = logging.getLogger(__name__)


_CONTEXT_SYSTEM = """당신은 검색 시스템을 돕는 한국어 문서 분석가입니다.
주어진 설교/강의의 한 부분에 대해, 이 부분이 전체에서 어떤 맥락인지 한 문장으로 요약하세요.

규칙:
1. 한 문장(40자 내외). "이 부분은 ~를 다룬다/설명한다" 형식.
2. 검색에 도움되는 핵심 주제어·성경 인물·개념을 포함하세요.
3. 설명·머리말 없이 문장만 출력하세요."""


async def _gen_context(title: str, section_title: str, chunk_text: str,
                       llm_provider: str | None) -> str:
    """단일 청크/섹션의 맥락 문장 생성 (실패 시 빈 문자열)."""
    head = f"[문서] {title}"
    if section_title:
        head += f"\n[섹션] {section_title}"
    user_msg = f"{head}\n\n[내용]\n{chunk_text[:1500]}"
    try:
        resp, _, _ = await chat_with_fallback(
            [Message(role="user", content=user_msg)],
            primary_provider=llm_provider,
            system=_CONTEXT_SYSTEM,
            temperature=0.1,
            max_tokens=100,
        )
        return (resp.text or "").strip().replace("\n", " ")
    except Exception as e:
        logger.debug("context gen 실패: %s", e)
        return ""


async def contextualize_chunks(
    chunks: list[Chunk],
    *,
    title: str = "",
    llm_provider: str | None = None,
) -> list[dict]:
    """각 청크에 맥락을 붙여 인덱싱용 dict 리스트 반환.

    Returns: [{"chunk": Chunk, "embed_text": str, "context_prefix": str}, ...]
    섹션 단위로 맥락을 1회 생성해 같은 섹션 청크끼리 공유 (비용 절감).
    """
    if not chunks:
        return []

    # 섹션별 대표 청크(가장 긴 것)로 맥락 1회 생성 → 공유
    section_groups: dict[str, list[Chunk]] = {}
    for c in chunks:
        section_groups.setdefault(c.section_title, []).append(c)

    section_context: dict[str, str] = {}
    for sec_title, group in section_groups.items():
        rep = max(group, key=lambda c: len(c.text))
        section_context[sec_title] = await _gen_context(
            title, sec_title, rep.text, llm_provider
        )

    results: list[dict] = []
    for c in chunks:
        ctx = section_context.get(c.section_title, "")
        # 섹션 제목도 맥락에 포함 (헤딩 자체가 강한 신호)
        prefix_parts = [p for p in [title, c.section_title, ctx] if p]
        context_prefix = " — ".join(prefix_parts)
        embed_text = (context_prefix + "\n\n" + c.text) if context_prefix else c.text
        results.append({
            "chunk": c,
            "embed_text": embed_text,
            "context_prefix": context_prefix,
        })
    return results
