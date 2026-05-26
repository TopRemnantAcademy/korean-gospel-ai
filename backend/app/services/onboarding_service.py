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

from .subscriber_service import get_or_create, update_profile


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
        "step": 2,
        "after_questions": 2,
        "field": "is_darakbang_member",
        "ask": "혹시 *다락방* 모임에 함께하고 계신가요?",
        "choices": ["네, 식구입니다", "인도자입니다", "한두 번 가봤어요", "아니요", "다락방이 뭔가요?"],
        "_choice_map": {
            0: True,   # is_darakbang_member=True, darakbang_role=member
            1: True,   # is_darakbang_member=True, darakbang_role=leader
            2: False,
            3: False,
            4: False,
        },
        "by_operator": True,
    },
    {
        "step": 3,
        "after_questions": 3,
        "field": "darakbang_chapter",
        "ask": "어느 다락방 모임에 계세요?",
        "free_text": True,
        "optional": True,
        "condition": "is_darakbang_member",  # is_darakbang_member == True 일 때만
        "by_operator": True,
    },
    {
        "step": 4,
        "after_questions": 5,
        "field": "current_struggle",
        "ask": "지금 마음에 가장 무거운 한 가지를 짧게 알려주실 수 있을까요?",
        "free_text": True,
    },
    {
        "step": 5,
        "after_questions": 8,
        "field": "preferred_tone",
        "ask": "어떤 말투가 더 편하세요?",
        "choices": ["부드럽게", "직접적으로", "격려하듯", "말씀 중심으로"],
    },
    {
        "step": 6,
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
    sub = get_or_create(sub_id)

    for item in ONBOARDING:
        if item["step"] <= sub["onboarding_step"]:
            continue
        if sub["total_questions"] < item["after_questions"]:
            continue

        # condition 체크 (예: is_darakbang_member == True 일 때만 darakbang_chapter 질문)
        condition_field = item.get("condition")
        if condition_field and not sub.get(condition_field):
            # 조건 불충족 → 이 step 건너뜀 (step은 완료로 표시)
            update_profile(sub_id, {"onboarding_step": item["step"]}, by_operator=True)
            continue

        # 이미 해당 필드가 채워져 있으면 스킵
        if sub.get(item["field"]):
            update_profile(sub_id, {"onboarding_step": item["step"]}, by_operator=True)
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
        update_profile(sub_id, {"onboarding_step": item["step"]}, by_operator=True)
        return q

    return None
