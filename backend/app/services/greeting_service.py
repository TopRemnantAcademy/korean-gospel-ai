"""재방문 사용자 환영 메시지 생성 서비스 — v2 (영적 재해석 방향).

설계 원칙:
  - 감정 위로 완전 배제 ("좋아지셨나요", "나아지셨나요", "힘드셨죠" 류 금지)
  - 지난번 상황·감정·질문을 영적 렌즈로 재해석하는 질문으로 시작
  - 위로 5단계 기준 1단계 수준 유지 — 짧고 직접적이며 영적 임팩트 우선
  - 감정 공감 → 영적 재질문 으로의 전환이 핵심

엔트리포인트:
  generate_greeting(sub_id, mode, target_lang) → dict
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from ..db import get_session
from ..models.orm import Interaction


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def days_since_last_active(dt_str: Optional[str]) -> Optional[int]:
    """last_active_at 문자열 → 경과 일수. 파싱 실패 시 None."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.split(".")[0]).replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception as e:
        logger.debug("[greeting] unparseable last_active_at=%r: %s", dt_str, e)
        return None


def get_last_interaction(sub_id: str) -> Optional[dict]:
    """가장 최근 Interaction — question 100자만 반환."""
    try:
        with get_session() as s:
            row = (
                s.query(Interaction)
                .filter(Interaction.subscriber_id == sub_id)
                .order_by(Interaction.created_at.desc())
                .first()
            )
            if row:
                return {
                    "question": (row.question or "")[:100],
                    "created_at": str(row.created_at),
                }
    except Exception as _e:
        logger.debug("greeting query failed: %s", _e)
    return None


# ── 규칙 기반 영적 재해석 메시지 ─────────────────────────────────────────────
#
# 핵심 전환:
#   ❌ "걱정하던 일은 좀 풀리셨나요?"         ← 감정 위로 (배제)
#   ✅ "그 걱정이 하나님께 나아가는 신호였을까요?" ← 영적 재해석 질문 (사용)

def rule_based_greeting(
    profile: dict,
    days_away: Optional[int],
    last_interaction: Optional[dict],
) -> str:
    emotional = profile.get("emotional_state", "")
    journey   = profile.get("journey_stage", "")
    salvation = profile.get("salvation_status", "unknown")
    total_q   = profile.get("total_questions", 0)

    # ── 첫 방문 ──────────────────────────────────────────────────────────────
    if not last_interaction or total_q <= 1:
        return "어떤 이야기든 가져오세요."

    # ── 이정표 (관계 깊이 인식) ───────────────────────────────────────────────
    if total_q == 10:
        return "열 번의 대화가 쌓였네요. 그 시간 속에 무엇이 변했나요?"
    if total_q == 50:
        return "50번의 대화. 지금 당신의 신앙은 처음과 무엇이 다른가요?"
    if total_q == 100:
        return "100번을 함께했어요. 하나님이 그 시간을 어떻게 쓰셨을까요?"

    # ── 30일+ 부재 ───────────────────────────────────────────────────────────
    if days_away is not None and days_away > 30:
        return f"{days_away}일 사이, 하나님께서 어떤 방식으로 일하셨나요?"

    # ── 감정 상태 기반 영적 재해석 ────────────────────────────────────────────
    # (감정 공감이 아닌, 그 감정을 영적 관점에서 재질문)
    if emotional == "anxious":
        return "지난번 그 불안이 하나님을 더 찾게 만드는 신호였을까요?"
    if emotional == "grieving":
        return "그 상실이 영적으로 어떤 의미로 다가오고 있나요?"
    if emotional == "distressed":
        return "지난번 그 고통 안에서 하나님은 어디 계신 것 같았나요?"
    if emotional == "hopeful":
        return "그 소망이 어디에서 오는 건지 생각해 보셨나요?"

    # ── 여정 단계 기반 ────────────────────────────────────────────────────────
    if journey == "hurting":
        return "그 상처를 복음의 눈으로 보면 어떻게 보이시나요?"
    if journey == "healing":
        return "치유가 일어나고 있다면, 그게 어떤 모습인가요?"
    if journey == "exploring":
        return "지난번 탐구가 지금 어디까지 이어졌나요?"
    if journey == "growing":
        return "요즘 하나님에 대해 새롭게 발견한 것이 있나요?"

    # ── 구원 여정 기반 ────────────────────────────────────────────────────────
    if salvation == "seeker":
        return "지난번 대화 이후, 복음에 대해 무엇이 더 궁금해졌나요?"
    if salvation == "new_believer":
        return "새 신자로서 요즘 가장 실제적으로 느끼는 게 뭔가요?"

    # ── 기본 (감정 위로 없는 직접적 질문) ────────────────────────────────────
    return "지난번 대화 이후, 무엇이 마음에 남았나요?"


# ── LLM 기반 영적 재해석 메시지 ──────────────────────────────────────────────

_LLM_SYSTEM = """\
당신은 복음 기반 AI 상담자입니다.
재방문 사용자에게 보낼 짧은 영적 메시지를 작성하세요.

[필수 원칙]
1. 감정 위로 완전 금지
   - 사용 금지 표현: "좋아지셨나요", "나아지셨나요", "힘드셨겠어요",
     "함께할게요", "괜찮으세요", "응원해요", "걱정 마세요"
2. 지난번 상황·감정을 영적 렌즈로 재해석하는 질문 1~2개
   - 형식 예시: "그 [감정/사건]이 하나님 앞에서 어떤 의미였나요?"
              "그 [경험]이 복음과 어떻게 연결되는 것 같나요?"
3. 1~2문장만 — 설교 금지, 답 강요 금지
4. 직접적이고 영적인 질문으로만 구성
5. 마크다운·이모지 없이 순수 텍스트"""


async def llm_greeting(
    profile: dict,
    days_away: Optional[int],
    last_interaction: Optional[dict],
    target_lang: str = "ko",
) -> str:
    """DeepSeek 기반 영적 재해석 메시지. 실패 시 빈 문자열."""
    from .llm.fallback import chat_with_fallback
    from .llm.base import Message

    ctx_lines: list[str] = []
    if days_away is not None:
        ctx_lines.append(f"마지막 방문: {days_away}일 전")
    if profile.get("emotional_state"):
        ctx_lines.append(f"마지막 감정 상태: {profile['emotional_state']}")
    if profile.get("journey_stage"):
        ctx_lines.append(f"여정 단계: {profile['journey_stage']}")
    sal = profile.get("salvation_status")
    if sal and sal != "unknown":
        ctx_lines.append(f"구원 여정: {sal}")
    if last_interaction and last_interaction.get("question"):
        ctx_lines.append(f"마지막 질문: {last_interaction['question']}")
    if profile.get("total_questions"):
        ctx_lines.append(f"누적 대화: {profile['total_questions']}번")

    context = "\n".join(ctx_lines) if ctx_lines else "첫 방문"

    lang_label = {"ko": "한국어", "en": "영어", "zh": "중국어", "ja": "일본어"}.get(target_lang, "한국어")
    system = _LLM_SYSTEM + f"\n\n언어: {lang_label}로 작성"

    try:
        resp, _, _ = await chat_with_fallback(
            [Message(
                role="user",
                content=f"사용자 정보:\n{context}\n\n영적 재해석 메시지를 작성해주세요.",
            )],
            primary_provider="deepseek",
            system=system,
            temperature=0.6,
            max_tokens=150,
        )
        return resp.text.strip()
    except Exception:
        return ""


# ── 통합 진입점 ──────────────────────────────────────────────────────────────

async def generate_greeting(
    sub_id: str,
    mode: str = "auto",
    target_lang: str = "ko",
) -> dict:
    """
    Returns:
        {
            "greeting": str,
            "mode_used": "rule" | "llm",
            "days_since_last_visit": int | None,
            "is_first_visit": bool,
        }
    """
    import asyncio
    from .subscriber_service import get_or_create

    profile          = await asyncio.to_thread(get_or_create, sub_id)
    last_interaction = await asyncio.to_thread(get_last_interaction, sub_id)
    days_away        = days_since_last_active(profile.get("last_active_at"))
    is_first_visit   = not last_interaction or (profile.get("total_questions", 0) <= 1)

    use_llm = (
        mode == "llm"
        or (mode == "auto" and not is_first_visit and days_away is not None and days_away >= 1)
    )

    greeting  = ""
    mode_used = "rule"

    if use_llm:
        greeting  = await llm_greeting(profile, days_away, last_interaction, target_lang)
        mode_used = "llm"

    if not greeting:  # rule fallback
        greeting  = rule_based_greeting(profile, days_away, last_interaction)
        mode_used = "rule"

    return {
        "greeting":              greeting,
        "mode_used":             mode_used,
        "days_since_last_visit": days_away,
        "is_first_visit":        is_first_visit,
    }
