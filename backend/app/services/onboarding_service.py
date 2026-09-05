"""자동 온보딩 (Drip) 질문 시스템 — D-C15 재설계 (구원 질문이 1번).

ORDERS.md D-C15: 기존 C3 폐기. 구원 상태(salvation_status) 가 시스템 전체에서
가장 중요한 변수이므로 첫 번째 질문으로 이동.
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: D-C15 — Onboarding 재설계 (구원 질문이 1번, C3 대체)
# Reason: ORDERS.md EPIC D-C15
# Status: COMPLETED
# =============================================================================
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create onboarding_service.py for C3
# Reason: 사용자와 대화 중 자연스럽게 프로필 정보를 수집하기 위한 로직
# Related: backend/app/api/chat.py
# Status: SUPERSEDED by D-C15
# =============================================================================
from __future__ import annotations
from typing import Optional



# D-C15: 구원 질문이 1번인 재설계 온보딩
ONBOARDING = [
    {
        "step": 1,
        "after_questions": 1,
        "field": "salvation_status",
        "ask": (
            "혹시 한 가지만 여쭤봐도 될까요 — "
            "예수님을 *지금* 구주로 영접하고 계세요? 부담 없이 답해주세요."
        ),
        "choices": [
            "네, 확신이 있어요",           # → assured
            "영접했지만 확신은 없어요",      # → uncertain
            "들어는 봤어요 / 잘 모르겠어요", # → seeker
            "관심 없어요",                 # → seeker (resisting 표시)
            "답하고 싶지 않아요",           # → unknown 유지
        ],
        # choice → salvation_status 매핑 (인덱스 기준)
        "_choice_map": {
            0: "assured",
            1: "uncertain",
            2: "seeker",
            3: "seeker",
            4: None,  # unknown 유지
        },
        "by_operator": True,  # salvation_status 는 operator 권한 필요
    },
    {
        # ✏️ 2026-07-29: 기존 "다락방 모임" 질문 폐기 → 자기이해(신앙 자각) 심층 질문으로 대체.
        # 다락방은 별도 사역 컨텍스트(ORM/프롬프트)로 운영자 설정 방식 유지, 온보딩에서는 질문하지 않음.
        "step": 2,
        "after_questions": 2,
        "field": "faith_self_view",
        "ask": (
            "지금 잠시, 당신 스스로를 가장 솔직하게 돌아보신다면 — "
            "*하나님과의 관계에서 가장 막연하거나 '아직 잘 모르겠다'고 느껴지는 "
            "부분이 있나요?* (그 답이, 당신이 지금 서 있는 곳을 더 정확히 보시는 데 "
            "도움이 될 거예요.)"
        ),
        "free_text": True,
    },
    {
        "step": 3,
        "after_questions": 5,
        "field": "current_struggle",
        "ask": "지금 마음에 가장 무거운 한 가지를 짧게 알려주실 수 있을까요?",
        "free_text": True,
    },
    {
        "step": 4,
        "after_questions": 8,
        "field": "preferred_tone",
        "ask": "어떤 말투가 더 편하세요?",
        "choices": ["부드럽게", "직접적으로", "격려하듯", "말씀 중심으로"],
    },
    {
        "step": 5,
        "after_questions": 12,
        "field": "email",
        "ask": "이메일을 알려주시면 매일 묵상을 보내드릴까요?",
        "free_text": True,
        "optional": True,
    },
]


# ✏️ AI-CHANGE 2026-05-19 [Antigravity]: sub.xxx → sub["xxx"] dict 접근 (B5/A2 fix)
# ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C15 — ONBOARDING 재설계 반영 (condition 체크 추가)
def check_and_get_onboarding_question(sub_id: str) -> Optional[str]:
    """현재 사용자의 질문 횟수와 완료 상태를 확인하여 온보딩 질문 반환."""
    # ✅ 2026-07-24 근본수정: get_session()(지연 BEGIN)은 "읽기→쓰기 승격" 시
    # WAL 모드에서 busy_timeout 을 무시하고 즉시 SQLITE_BUSY_SNAPSHOT
    # ("database is locked")으로 실패한다. BEGIN IMMEDIATE 로 처음부터
    # 쓰기 락을 잡아 busy_timeout(30s) 대기가 정상 동작하도록 한다.
    from ..db import get_session_immediate
    from ..models.orm import Subscriber

    with get_session_immediate() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            sub = Subscriber(subscriber_id=sub_id)
            s.add(sub)
            s.flush()

        sub_onboarding_step = sub.onboarding_step or 0
        total_questions = sub.total_questions or 0
        question_text = None

        for item in ONBOARDING:
            if item["step"] <= sub_onboarding_step:
                continue
            if total_questions < item["after_questions"]:
                continue

            # condition 체크 (예: is_darakbang_member == True 일 때만 darakbang_chapter 질문)
            condition_field = item.get("condition")
            if condition_field and not getattr(sub, condition_field, None):
                # 조건 불충족 → 이 step 건너뜀 (step은 완료로 표시)
                sub_onboarding_step = item["step"]
                sub.onboarding_step = item["step"]
                continue

            # 이미 해당 필드가 채워져 있으면 스킵
            if getattr(sub, item["field"], None):
                sub_onboarding_step = item["step"]
                sub.onboarding_step = item["step"]
                continue

            # 질문 문자열 구성
            q = (
                f"\n\n---\n"
                f"*잠시만요 — 더 잘 도와드리려면 한 가지만 여쭤봐도 될까요? "
                f"{item['ask']}*\n"
                f"*(답 안 해도 괜찮아요 — 그냥 더 잘 도와드리려고 여쭙는 거예요)*"
            )
            if item.get("choices"):
                q += "\n(보기: " + " / ".join(item["choices"]) + ")"

            # 다음 step으로 갱신
            sub.onboarding_step = item["step"]
            question_text = q
            break

        return question_text
