"""사용자 프로필 관리 서비스 (관제탑 기능 지원)"""

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: N10 — update_profile 화이트리스트 추가 (사용자 권한 승격 방지)
# Reason: ORDERS.md N10 — setattr(sub, k, v) 무제한 → 보안 위험
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
from typing import Dict, Any

from sqlalchemy.exc import IntegrityError
from ..db import get_session
from ..models.orm import Subscriber


def _row_to_dict(row: "Subscriber") -> dict:
    """ORM row → safe dict (세션 밖에서 접근 가능)."""
    return {
        "subscriber_id": row.subscriber_id,
        "journey_stage": row.journey_stage,
        "faith_stage": row.faith_stage,
        "emotional_state": row.emotional_state,
        "current_struggle": row.current_struggle,
        "preferred_tone": row.preferred_tone,
        "total_questions": row.total_questions,
        "onboarding_step": row.onboarding_step,
        "is_darakbang_member": row.is_darakbang_member,
        "session_count": row.session_count,
        "age_group": row.age_group,
        "gender": row.gender,
        "last_emotion": row.last_emotion,
        "email": row.email,
        "display_name": row.display_name,
        "auth_status": row.auth_status,
        "consent_data": row.consent_data,
        "consent_kakao": row.consent_kakao,
        "first_seen_at": str(row.first_seen_at) if row.first_seen_at else None,
        "last_active_at": str(row.last_active_at) if row.last_active_at else None,
        "topic_interests": row.topic_interests,
        "salvation_status": row.salvation_status,
        "salvation_confidence": row.salvation_confidence,
        "salvation_last_signal_at": str(row.salvation_last_signal_at)
        if row.salvation_last_signal_at
        else None,
        "assume_saved": row.assume_saved,
        "darakbang_role": row.darakbang_role,
        "darakbang_chapter": row.darakbang_chapter,
        "darakbang_joined_at": str(row.darakbang_joined_at)
        if row.darakbang_joined_at
        else None,
        "darakbang_verified": row.darakbang_verified,
        # 종교 분류
        "religion": row.religion,
        "denomination": row.denomination,
        # 봇 관리
        "flagged_as_bot": row.flagged_as_bot,
        "bot_score": row.bot_score or 0.0,
        # 이메일 인증 / 티어 (2026-07-23)
        "email_verified": bool(row.email_verified),
        "email_verified_at": str(row.email_verified_at) if row.email_verified_at else None,
        "is_lifetime_member": bool(row.is_lifetime_member),
        "subscription_tier": row.subscription_tier or "free",
        "subscription_expires_at": row.subscription_expires_at.isoformat() if row.subscription_expires_at else None,
    }


# N10: update_profile 화이트리스트 — 사용자가 직접 수정 가능한 필드
_USER_EDITABLE: frozenset[str] = frozenset(
    {
        "emotional_state",
        "current_struggle",
        "preferred_tone",
        "faith_stage",
        "journey_stage",
        "age_group",
        "gender",
        "display_name",
        "consent_data",
        "consent_kakao",
    }
)
# 운영자(by_operator=True)만 수정 가능한 필드
_OPERATOR_ONLY: frozenset[str] = frozenset(
    {
        "salvation_status",
        "salvation_confidence",
        "assume_saved",
        "auth_status",
        "is_darakbang_member",
        "darakbang_role",
        "darakbang_chapter",
        "darakbang_verified",
        "darakbang_joined_at",
        "onboarding_step",
        "consent_data",
        "consent_kakao",
        "session_count",
        "total_questions",
        "email",
        # 봇 관리
        "flagged_as_bot",
        "bot_score",
        # 이메일 인증 / 티어 (2026-07-23)
        "email_verified",
        "is_lifetime_member",
        "subscription_tier",
        "subscription_expires_at",
    }
)

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create subscriber_service.py for C2
# Reason: 사용자 프로필 CRUD 및 디테일 정보 갱신을 위해 생성
# Related: backend/app/models/orm.py, backend/app/api/subscriber.py
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-19 08:55
# Task: get_or_create → dict 반환으로 변경 (B5/A2 fix)
# Reason: 세션 종료 후 ORM 인스턴스 속성 접근 시 DetachedInstanceError 방지
# Related: ORDERS B5, A2
# Status: COMPLETED
# =============================================================================


# ✏️ AI-CHANGE 2026-05-19 [Antigravity]: dict 반환으로 변경 — DetachedInstanceError 방지 (B5/A2 fix)
def get_or_create(sub_id: str) -> dict:
    with get_session() as s:
        row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not row:
            row = Subscriber(subscriber_id=sub_id)
            try:
                s.add(row)
                s.flush()
            except IntegrityError:
                s.rollback()
                row = (
                    s.query(Subscriber)
                    .filter(Subscriber.subscriber_id == sub_id)
                    .first()
                )
                if row is None:
                    raise
        return _row_to_dict(row)


def prepare_profile(sub_id: str, signal: Dict[str, Any] | None = None) -> dict:
    """increment_question + merge_auto_signal + get_or_create 를 단일 세션으로 처리.

    chat.py 의 3회 개별 세션 호출을 1회로 통합해 DB 왕복을 줄인다.
    signal 이 없으면 카운트 증가 + 프로필 반환만 수행.
    """
    with get_session() as s:
        row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not row:
            row = Subscriber(subscriber_id=sub_id)
            try:
                s.add(row)
                s.flush()
            except IntegrityError:
                s.rollback()
                row = (
                    s.query(Subscriber)
                    .filter(Subscriber.subscriber_id == sub_id)
                    .first()
                )
                if row is None:
                    raise

        row.total_questions = (row.total_questions or 0) + 1

        if signal:
            if signal.get("emotional_state") and not row.emotional_state:
                row.emotional_state = signal["emotional_state"]
            if signal.get("journey_hint") and not row.journey_stage:
                row.journey_stage = signal["journey_hint"]
            if signal.get("faith_hint") and not row.faith_stage:
                row.faith_stage = signal["faith_hint"]

        return _row_to_dict(row)


def get_all_subscribers(limit: int = 10000, offset: int = 0) -> list[dict]:
    # ✏️ AI-CHANGE 2026-05-19 [Antigravity]: dict 리스트 반환으로 변경 (B5 일관성)
    # ❌ AI-REMOVE 2026-05-20 [Cascade]: is_believer 제거 (ORDERS B6 - salvation_status로 대체됨)
    # BUG-09 수정: limit/offset 파라미터 추가 — 백엔드 API 의 페이지네이션 지원.
    # 기본값 10000은 사실상 전체 반환 (기존 호출자 호환성).
    limit = max(1, min(limit, 10000))
    offset = max(0, offset)
    with get_session() as s:
        subs = (
            s.query(Subscriber)
            .order_by(Subscriber.last_active_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        # ✏️ 2026-07-29: 목록 직렬화를 _row_to_dict 로 일원화.
        # (기존 하드코딩 dict 가 subscription_tier/is_lifetime_member/subscription_expires_at/
        #  email_verified/auth_status/age_group/gender 등을 누락해 유저관리 페이지 표시 오류 발생)
        return [_row_to_dict(sub) for sub in subs]


def update_profile(
    sub_id: str, fields: Dict[str, Any], *, by_operator: bool = False
) -> dict:
    # ✏️ AI-CHANGE 2026-05-19 [Antigravity]: dict 반환으로 변경 (B5 일관성)
    # ✏️ AI-CHANGE 2026-05-26 [Claude]: N10 — 화이트리스트 필터 추가 (권한 승격 방지)
    allowed = _USER_EDITABLE | _OPERATOR_ONLY if by_operator else _USER_EDITABLE
    safe_fields = {k: v for k, v in fields.items() if k in allowed}
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            sub = Subscriber(subscriber_id=sub_id)
            s.add(sub)
        for k, v in safe_fields.items():
            setattr(sub, k, v)
        s.flush()
        profile_dict = _row_to_dict(sub)
    return profile_dict


# ──────────────────────────────────────────────────────────────────────────────
# NOTE: increment_session / increment_question / merge_auto_signal 제거 (2026-06-09)
#       prepare_profile() 에 흡수되어 실제 호출 없음 — 데드코드 정리
# ──────────────────────────────────────────────────────────────────────────────
