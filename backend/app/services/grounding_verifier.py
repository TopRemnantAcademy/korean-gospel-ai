"""SourceGroundingVerifier — 생성 답변의 검색 청크 귀속 / 환각 검증.

설계 원칙 (사용자 요구: 다른 오류 없음 + 속도 저하 없음):
- Fail-open: 어떤 예외/타임아웃도 답변 차단으로 이어지지 않음.
- 기본 monitor 모드 = 백그라운드 실행 → 응답 지연 0 (기존 _bg_judge 패턴과 동일).
- enforce 모드(opt-in) = 동기 실행, 미통과 시 안전 응답으로 대체. 재생성 없음 → 지연 bounded.

검증 대상 컨텍스트는 chat_pipeline.retrieve_and_classify 가 반환하는
`items`(EnrichedSearchResult 리스트)이며, 각 항목은 .text / .source_title 을 가진다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

from ..config import settings
from .llm.base import Message
from .llm.fallback import chat_with_fallback

logger = logging.getLogger("gospel-api.grounding")

_SYSTEM = (
    "You are a strict faithfulness checker for a Christian Q&A assistant. "
    "You are given an ANSWER and several retrieved SOURCE passages. "
    "Decide whether every factual claim in the ANSWER is supported by the SOURCE passages. "
    "Ignore greeting/polite phrasing. Respond ONLY with JSON: "
    '{"supported": true/false, "score": 0.0-1.0, "issues": ["claim not found in sources", ...]}. '
    "score=1.0 means fully grounded; score<=0.4 means serious hallucination."
)

_PROMPT_TMPL = (
    "ANSWER:\n{answer}\n\n"
    "SOURCE PASSAGES:\n{sources}\n\n"
    "Return the JSON verdict now."
)

# 근거 부족 시 안전 응답 (언어별, 즉시 생성 → 재생성 지연 없음)
_SAFE_RESPONSES = {
    "ko": "죄송합니다. 드린 답변 중 근거 자료로 확인되지 않는 부분이 있어, 정확한 출처를 다시 확인해 안내해 드리겠습니다.",
    "zh": "抱歉，我刚才的回答中有部分内容无法在资料中核实，我会重新核对出处后再为您说明。",
    "en": "I'm sorry — part of my answer couldn't be verified against the source materials. I'll re-check the references and get back to you.",
    "ja": "申し訳ありません。今の回答の一部は参照資料から確認できなかったため、出典を再確認してからお伝えします。",
}


@dataclass
class GroundingResult:
    passed: bool
    score: float
    issues: list[str] = field(default_factory=list)
    mode: str = "monitor"
    error: str | None = None

    def model_dump(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues,
            "mode": self.mode,
            "error": self.error,
        }


def _format_sources(contexts: list) -> str:
    out: list[str] = []
    for i, c in enumerate(contexts[:8], 1):
        text = (getattr(c, "text", None) or getattr(c, "snippet", "") or "")[:800]
        title = getattr(c, "source_title", None) or getattr(c, "title", "") or f"src{i}"
        out.append(f"[{i}] ({title}) {text}")
    return "\n".join(out)


def _parse_verdict(raw: str) -> tuple[bool, float, list[str]]:
    """LLM 출력에서 JSON 파싱. 실패 시 fail-open(지원됨=True)."""
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return True, 1.0, []
        data = json.loads(m.group(0))
        supported = bool(data.get("supported", True))
        score = float(data.get("score", 1.0))
        issues = [str(x) for x in data.get("issues", [])]
        return supported, score, issues
    except Exception:
        return True, 1.0, []


async def verify_grounding(
    answer: str,
    contexts: list,
    target_lang: str = "ko",
    mode: str = "monitor",
) -> GroundingResult:
    """답변의 근거 귀속 검증. 예외 발생 시 fail-open(Grounded=True)."""
    if not answer or not contexts:
        return GroundingResult(passed=True, score=1.0, mode=mode, error="no-context")
    sources = _format_sources(contexts)
    if not sources.strip():
        return GroundingResult(passed=True, score=1.0, mode=mode, error="empty-sources")

    messages = [Message(role="user", content=_PROMPT_TMPL.format(answer=answer, sources=sources))]
    try:
        resp, _llm, _att = await chat_with_fallback(
            messages,
            system=_SYSTEM,
            temperature=0.0,
            max_tokens=400,
        )
        supported, score, issues = _parse_verdict(getattr(resp, "text", "") or "")
        # supported=False 이거나 score 가 낮으면 미통과
        passed = supported and score > 0.4
        return GroundingResult(passed=passed, score=score, issues=issues, mode=mode)
    except Exception as exc:
        logger.warning("grounding verify 실패(fail-open): %s", exc)
        return GroundingResult(passed=True, score=1.0, mode=mode, error=str(exc)[:200])


def safe_response(target_lang: str) -> str:
    return _SAFE_RESPONSES.get(target_lang, _SAFE_RESPONSES["ko"])


async def verify_grounding_with_timeout(
    answer: str,
    contexts: list,
    target_lang: str = "ko",
    mode: str = "enforce",
    timeout: float | None = None,
) -> GroundingResult:
    """enforce 모드용: 타임아웃으로 지연을 bound. 타임아웃 초과 시 fail-open."""
    to = timeout if timeout is not None else settings.grounding_verify_timeout
    try:
        return await asyncio.wait_for(
            verify_grounding(answer, contexts, target_lang=target_lang, mode=mode),
            timeout=to,
        )
    except asyncio.TimeoutError:
        logger.warning("grounding verify 타임아웃(fail-open): %ss", to)
        return GroundingResult(passed=True, score=1.0, mode=mode, error="timeout")
