"""LLM 기반 통찰 생성 엔진 — 4단계 파이프라인.

설계 문서 §4 기반 구현.

통찰 생성 파이프라인:
  Step 1: 근본 원인 분석 (root_cause_analysis)
  Step 2: AI 진단 요약 (ai_diagnosis)
  Step 3: 도움된 이유 분석 (best_answer_why)
  Step 4: 성찰 질문 생성 (reflection_prompt)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import or_
from ..db import get_session_immediate
from ..models.orm import QATrendSnapshot
from .llm.base import Message

log = logging.getLogger("gospel-api.insight")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 프롬프트 템플릿 (§4.1) ──

PROMPT_VERSION = "v1.0"

_ROOT_CAUSE_PROMPT = """당신은 중독 회복 커뮤니티의 AI 상담사입니다.

다음 질문이 중독 회복 커뮤니티에서 {total_count}회 반복되었습니다.
질문: "{question}"
변형: {variants}

다음을 분석해 주세요:
1. 이 질문이 반복되는 심리적·영적 근본 원인은 무엇인가?
2. 질문자들이 진짜 원하는 것은 무엇인가? (표면 vs 본질)
3. 이 질문이 회복 여정의 어떤 단계에서 주로 나오는가?

200자 이내로 작성. 따뜻하고 공감적인 어조.
판단하거나 정죄하지 말고, 이해와 공감을 먼저 보여주세요.{additional}"""

_AI_DIAGNOSIS_PROMPT = """당신은 이 질문에 대해 AI 상담사로서 답변했습니다.

질문: "{question}"
당신의 답변: {answer}

다음을 설명해 주세요:
1. 이 질문의深层 구조 — 질문자가 미처 말하지 못한 진짜 고민
2. 당신이 답변에서 특히 강조한 핵심 포인트 2가지
3. 이 답변이 단순한 조언이 아니라 '회복의 관점 전환'을 어떻게 유도했는지

250자 이내. 분석적이되 전문용어 없이 일상 언어로.
'당신은 죄인입니다' 같은 정죄 표현은 절대 사용하지 마세요.{additional}"""

_BEST_ANSWER_WHY_PROMPT = """이 답변은 {positive}명의 👍와 {negative}명의 👎를 받았습니다 ({fb_ratio:.0f}% 긍정).

질문: "{question}"
답변: {answer}

분석해 주세요: 왜 이 답변이 특히 도움이 되었을까요?
1. 답변의 어떤 부분이 가장 공감을 얻었는지
2. 이 답변이 주는 '깨달음의 순간'은 무엇인지

150자 이내. 따뜻한 어조로.{additional}"""

_REFLECTION_PROMPT = """사용자가 "{question}"라는 인기 질문의 통찰 패널을 보고 있습니다.
사용자가 스스로에게 물어볼 수 있는 성찰 질문 1개를 만들어 주세요.

조건:
- '당신은 ~인가요?' 형태의 열린 질문
- 정답을 강요하지 않고 스스로 생각하게 만드는 질문
- 판단하지 않고 초대하는 어조
- 80자 이내

예시: '당신은 지금 회복의 어느 계절에 서 있나요?'{additional}"""


_SHORT_SERMON_PROMPT = """당신은 중독 회복 커뮤니티의 따뜻한 설교자입니다.

다음 질문을 품고 고민하는 분들을 위해, 성경 말씀을 바탕으로 한 짧은 '단편 설교' 한 편을 작성해 주세요.

질문: "{question}"

조건:
- 분량: 300~500자 내외의 한 편 (문단 2~3개)
- 어조: 판단하지 않고, 하나님의 은혜와 회복의 소망을 전하는 따뜻한 어조
- 성경 구절 1~2개 인용(가능한 경우), 일상의 언어로 풀어서 설명
- 정죄하거나 가르치려 들지 말고, 동행하는 마음으로 쓸 것
- 마크다운은 사용하지 말고 일반 텍스트로 작성{additional}"""

# ── 통찰 생성 실행 ──


async def _call_llm(
    prompt: str,
    *,
    system: str = "당신은 중독 회복을 돕는 AI 상담사입니다.",
    max_tokens: int = 400,
    timeout: float = 30.0,
) -> Optional[str]:
    """LLM 호출 with 타임아웃 + 3회 retry."""
    from ..services.llm.fallback import chat_with_fallback

    messages = [Message(role="user", content=prompt)]

    for attempt in range(3):
        try:
            response, _, _ = await asyncio.wait_for(
                chat_with_fallback(
                    messages,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=0.3,
                ),
                timeout=timeout,
            )
            text = (response.text or "").strip()
            if text:
                return text
            log.warning("[insight] LLM 응답이 빈 문자열 (attempt %d/3)", attempt + 1)
        except asyncio.TimeoutError:
            log.warning("[insight] LLM 타임아웃 (attempt %d/3)", attempt + 1)
        except Exception as e:
            log.warning("[insight] LLM 호출 실패 (attempt %d/3): %s", attempt + 1, e)

        if attempt < 2:
            await asyncio.sleep(1.0 * (2 ** attempt))  # exponential backoff

    return None


async def generate_insights(
    snapshot_id: str,
    *,
    sections: Optional[list[str]] = None,
    additional_instruction: Optional[str] = None,
    model_override: Optional[str] = None,
) -> dict:
    """단일 스냅샷에 대한 통찰 생성.

    Args:
        snapshot_id: 대상 스냅샷 ID
        sections: 생성할 섹션 목록 (기본: 전체 4개)
        additional_instruction: LLM에게 추가 지시사항
        model_override: 사용할 LLM 모델 (기본값 사용 시 None)

    Returns:
        {
            "ok": bool,
            "snapshot_id": str,
            "insight_version": int,
            "generated_at": str,
            "sections_generated": list[str],
            "sections_failed": list[str],
            "model_used": str,
        }
    """
    from ..config import settings

    if sections is None:
        sections = ["root_cause", "ai_diagnosis", "best_answer_why", "reflection"]

    additional = ""
    if additional_instruction:
        # 프롬프트 injection 방지 — 마크다운 코드블록으로 감싸서 주입
        additional = f"\n\n[추가 지시사항]\n```\n{additional_instruction[:500]}\n```"

    with get_session_immediate() as s:
        snap = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_id == snapshot_id,
                QATrendSnapshot.deleted_at.is_(None),
            )
            .first()
        )

        if not snap:
            return {"ok": False, "error": "스냅샷을 찾을 수 없습니다"}

        question = snap.canonical_text
        variants = (snap.raw_variants or [])[:5]
        variants_str = ", ".join(v.get("text", "") for v in variants[:5]) if variants else "(없음)"

        total_count = snap.total_count
        pos = snap.positive_feedback
        neg = snap.negative_feedback
        fb_total = pos + neg
        fb_ratio = (pos / fb_total * 100) if fb_total > 0 else 0.0

        answer = snap.best_answer_text or snap.admin_edited_text or ""

        model_used = model_override or settings.llm_provider or "gemini-2.5-flash"
        generated = []
        failed = []

        # Step 1: 근본 원인 분석
        if "root_cause" in sections:
            prompt = _ROOT_CAUSE_PROMPT.format(
                total_count=total_count,
                question=question,
                variants=variants_str,
                additional=additional,
            )
            result = await _call_llm(prompt, max_tokens=300)
            if result:
                snap.root_cause_analysis = result
                snap.review_status_root_cause = "pending"
                generated.append("root_cause")
            else:
                failed.append("root_cause")

        # Step 2: AI 진단 요약
        if "ai_diagnosis" in sections:
            prompt = _AI_DIAGNOSIS_PROMPT.format(
                question=question,
                answer=answer or "(아직 충분한 답변이 없습니다)",
                additional=additional,
            )
            result = await _call_llm(prompt, max_tokens=350)
            if result:
                snap.ai_diagnosis = result
                snap.review_status_ai_diagnosis = "pending"
                generated.append("ai_diagnosis")
            else:
                failed.append("ai_diagnosis")

        # Step 3: 도움된 이유 분석 (best_answer_text가 있을 때만)
        if "best_answer_why" in sections:
            if answer:
                prompt = _BEST_ANSWER_WHY_PROMPT.format(
                    positive=pos,
                    negative=neg,
                    fb_ratio=fb_ratio,
                    question=question,
                    answer=answer,
                    additional=additional,
                )
                result = await _call_llm(prompt, max_tokens=250)
                if result:
                    snap.best_answer_why = result
                    snap.review_status_best_answer_why = "pending"
                    generated.append("best_answer_why")
                else:
                    failed.append("best_answer_why")
            else:
                log.info("[insight] best_answer_text 없음 — Step 3 스킵")

        # Step 4: 성찰 질문 생성
        if "reflection" in sections:
            prompt = _REFLECTION_PROMPT.format(
                question=question,
                additional=additional,
            )
            result = await _call_llm(prompt, max_tokens=150)
            if result:
                snap.reflection_prompt = result
                snap.review_status_reflection = "pending"
                generated.append("reflection")
            else:
                failed.append("reflection")

        # 메타데이터 업데이트
        if generated:
            if snap.insight_version == 0:
                snap.insight_version = 1
            else:
                snap.insight_version += 1

            snap.insight_generated_at = _now()
            snap.ai_model_used = model_used
            snap.insight_prompt_version = PROMPT_VERSION
            snap.needs_regeneration = bool(failed)
            snap.updated_at = _now()

        s.flush()

        return {
            "ok": True,
            "snapshot_id": snapshot_id,
            "insight_version": snap.insight_version,
            "generated_at": _now().isoformat(),
            "sections_generated": generated,
            "sections_failed": failed,
            "model_used": model_used,
        }


async def generate_short_sermon(snapshot_id: str) -> dict:
    """단일 스냅샷에 대해 '단편 설교' 한 편을 LLM 으로 생성한다 (작업 W).

    생성된 텍스트는 저장하지 않고 반환만 한다. 관리자 검토 후 PATCH 로 저장.
    """
    with get_session_immediate() as s:
        snap = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_id == snapshot_id,
                QATrendSnapshot.deleted_at.is_(None),
            )
            .first()
        )
        if not snap:
            return {"ok": False, "error": "스냅샷을 찾을 수 없습니다"}
        question = snap.admin_edited_text or snap.canonical_text

    prompt = _SHORT_SERMON_PROMPT.format(question=question, additional="")
    text = await _call_llm(prompt, max_tokens=600, timeout=40.0)
    if not text:
        return {"ok": False, "error": "단편 설교 생성에 실패했습니다"}
    return {"ok": True, "snapshot_id": snapshot_id, "text": text}


async def generate_insights_for_top_questions(limit: int = 20) -> dict:
    """Top N 질문 중 통찰이 없는 항목에 대해 통찰 생성.

    Returns:
        {"total_candidates": int, "generated": int, "skipped": int, "errors": list}
    """
    with get_session_immediate() as s:
        candidates = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_type == "question",
                QATrendSnapshot.deleted_at.is_(None),
                QATrendSnapshot.insight_version == 0,
            )
            .order_by(QATrendSnapshot.trend_score.desc())
            .limit(limit)
            .all()
        )

    total = len(candidates)
    generated = 0
    skipped = 0
    errors = []

    for snap in candidates:
        # 중복 생성 방지
        if snap.insight_version > 0 and not snap.needs_regeneration:
            skipped += 1
            continue

        try:
            result = await generate_insights(snap.snapshot_id)
            if result.get("ok"):
                generated += 1
            else:
                errors.append({"snapshot_id": snap.snapshot_id, "reason": result.get("error", "unknown")})
        except Exception as e:
            log.exception("[insight] 통찰 생성 실패: %s", snap.snapshot_id)
            errors.append({"snapshot_id": snap.snapshot_id, "reason": str(e)})

    return {
        "total_candidates": total,
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }


async def regenerate_insights_for_stale(older_than_days: int = 30) -> int:
    """일정 기간 이상 지난 통찰 중 재생성 필요 항목 처리.

    Returns:
        재생성 시도 횟수
    """
    with get_session_immediate() as s:
        cutoff = _now() - timedelta(days=older_than_days)
        candidates = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_type == "question",
                QATrendSnapshot.deleted_at.is_(None),
                QATrendSnapshot.needs_regeneration == True,  # noqa: E712
                QATrendSnapshot.insight_version > 0,
                # older_than_days 가 실제로 적용되도록 컷오프 필터 추가
                # (insight_generated_at 가 없으면 "생성된 적 없음"으로 간주해 항상 대상)
                or_(
                    QATrendSnapshot.insight_generated_at.is_(None),
                    QATrendSnapshot.insight_generated_at <= cutoff,
                ),
            )
            .order_by(QATrendSnapshot.trend_score.desc())
            .limit(10)
            .all()
        )

    count = 0
    for snap in candidates:
        try:
            result = await generate_insights(snap.snapshot_id)
            if result.get("ok"):
                count += 1
        except Exception as e:
            log.warning("[insight] 재생성 실패: %s — %s", snap.snapshot_id, e)

    return count


# ── 추가 질문하기 (인기QA 후속 질문) ──
# 디자인 원칙: 추가 질문은 반드시 유저의 질문 + 해당 QA의 내용(위의 내용)을
# 근거로 한 후속 질문이어야 하며, 단독적인 하나의 질문이 아니다. 따라서
# LLM 프롬프트에 원본 질문·답변·통찰을 항상 컨텍스트로 주입하여 맥락 밖
# 답변이 나오지 않도록 강제한다.
_ASK_SYSTEM_PROMPT = (
    "당신은 중독 회복을 돕는 AI 상담사입니다. "
    "아래에 제시된 [원본 질문]과 [답변]·[통찰]의 맥락 안에서만 답하세요. "
    "맥락과 무관한 새로운 주제로 빠져나가지 말고, 제시된 내용을 근거로 답변하세요."
)

_ASK_PROMPT_TEMPLATE = """다음은 인기 질문과 그에 대한 답변, 그리고 분석 통찰입니다.

[원본 질문 / 위의 내용]
{context}

위는 이 QA의 '위의 내용'입니다. 관리자가 이 내용을 근거로 후속 질문을 합니다.
원본 질문과 답변·통찰의 맥락을 벗어나지 않고, 제시된 내용을 근거로 답변하세요.

[추가 질문]
{followup}
"""


async def ask_about_snapshot(snapshot_id: str, question: str) -> dict:
    """인기 QA 스냅샷에 대해 맥락 기반 후속 질문에 답한다.

    question 은 반드시 유저의 질문 + 위의 내용을 근거로 한 후속 질문이어야 하며,
    단독적인 질문이 아니다. 답변은 항상 원본 질문·답변·통찰 컨텍스트에 묶인다.
    """
    q = (question or "").strip()
    if len(q) < 2:
        return {"ok": False, "error": "질문을 2자 이상 입력하세요."}

    with get_session_immediate() as s:
        snap = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_id == snapshot_id,
                QATrendSnapshot.deleted_at.is_(None),
            )
            .first()
        )
        if not snap:
            return {"ok": False, "error": "스냅샷을 찾을 수 없습니다."}

        user_question = (snap.canonical_text or "").strip()
        answer = (snap.admin_edited_text or snap.best_answer_text or "").strip()

        context_parts: list[str] = []
        if user_question:
            context_parts.append(f"• 원본 질문: {user_question}")
        if answer:
            context_parts.append(f"• 답변: {answer}")
        if snap.root_cause_analysis:
            context_parts.append(f"• 근본 원인: {snap.root_cause_analysis}")
        if snap.ai_diagnosis:
            context_parts.append(f"• AI 진단: {snap.ai_diagnosis}")
        if snap.best_answer_why:
            context_parts.append(f"• 도움된 이유: {snap.best_answer_why}")
        if snap.reflection_prompt:
            context_parts.append(f"• 성찰 질문: {snap.reflection_prompt}")

        context = "\n".join(context_parts) if context_parts else "(근거 내용 없음)"

    prompt = _ASK_PROMPT_TEMPLATE.format(context=context, followup=q)
    try:
        text = await _call_llm(prompt, system=_ASK_SYSTEM_PROMPT, max_tokens=600, timeout=45.0)
    except Exception as exc:  # LLM 실패 시 친절한 에러
        log.exception("[ask_about_snapshot] LLM 호출 실패 snapshot=%s", snapshot_id)
        return {"ok": False, "error": f"LLM 응답 생성에 실패했습니다: {exc}"}

    if not text or not text.strip():
        return {"ok": False, "error": "LLM이 빈 응답을 반환했습니다."}

    return {
        "ok": True,
        "snapshot_id": snapshot_id,
        "answer": text.strip(),
        "grounded_in": {
            "question": user_question,
            "answer": answer[:300],
        },
    }
