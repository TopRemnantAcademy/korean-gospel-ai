"""Enhanced RAG — 프롬프트 조립 (검색 컨텍스트 → LLM 입력).

책임:
- 중복 컨텍스트 제거
- [번호] 인용 마커 부여 + 토큰 예산 내 컨텍스트 구성
- citation 메타(출처/섹션/스니펫) 생성 → 생성 모듈이 답변에 인용 병합
"""
from __future__ import annotations

from ..chunker import estimate_tokens
from .types import RetrievedChunk


class PromptAssembler:
    def __init__(self, language: str = "ko"):
        self.language = language

    def assemble(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        max_tokens: int = 1200,
        top_k: int = 5,
    ) -> tuple[str, str, list[dict]]:
        # 1) 중복 텍스트 제거 (최초 출현 유지)
        seen: set[str] = set()
        uniq: list[RetrievedChunk] = []
        for c in chunks:
            if c.text in seen:
                continue
            seen.add(c.text)
            uniq.append(c)

        blocks: list[str] = []
        citations: list[dict] = []
        used = 0
        idx = 0
        for c in uniq:
            if idx >= top_k:
                break
            est = estimate_tokens(c.text)
            if blocks and used + est > max_tokens:
                break
            idx += 1
            src = c.title or c.source or c.doc_id
            header = f"[{idx}] (출처: {src}"
            if c.section:
                header += f" / {c.section}"
            header += ")"
            blocks.append(f"{header}\n{c.text}")
            citations.append(
                {
                    "index": idx,
                    "doc_id": c.doc_id,
                    "title": c.title or c.source,
                    "source": c.source,
                    "section": c.section,
                    "snippet": c.text[:200],
                }
            )
            used += est

        context = "\n\n".join(blocks)
        system = self._system_prompt()
        user = (
            f"질문: {query}\n\n"
            f"참고 문맥:\n{context}\n\n"
            "위 문맥을 바탕으로 질문에 답하세요. 근거가 되는 문맥은 반드시 [번호] 형태로 인용하세요. "
            "문맥에 존재하지 않는 정보는 추측하지 말고, 알 수 없다면 그렇게 명시하세요."
        )
        return system, user, citations

    def _system_prompt(self) -> str:
        lang = self.language
        return (
            "You are a precise retrieval-augmented assistant. "
            f"Answer in the language of the user's question (prefer: {lang}). "
            "Use ONLY the provided context passages. Cite supporting passages with [n] markers. "
            "If the context does not contain the answer, say you cannot answer from the available context. "
            "Do not invent facts, dates, or sources."
        )
