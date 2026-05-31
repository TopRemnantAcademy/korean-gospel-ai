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
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session
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
        "salvation_last_signal_at": str(row.salvation_last_signal_at) if row.salvation_last_signal_at else None,
        "assume_saved": row.assume_saved,
        "darakbang_role": row.darakbang_role,
        "darakbang_chapter": row.darakbang_chapter,
        "darakbang_joined_at": str(row.darakbang_joined_at) if row.darakbang_joined_at else None,
        "darakbang_verified": row.darakbang_verified,
        # 구독/무료체험
        "subscription_tier": row.subscription_tier or "guest",
        "trial_expires_at": str(row.trial_expires_at) if row.trial_expires_at else None,
        "subscribed_at": str(row.subscribed_at) if row.subscribed_at else None,
        # 종교 분류
        "religion": row.religion,
        "denomination": row.denomination,
        # 봇
        "bot_score": row.bot_score,
        "flagged_as_bot": row.flagged_as_bot,
    }

# N10: update_profile 화이트리스트 — 사용자가 직접 수정 가능한 필드
_USER_EDITABLE: frozenset[str] = frozenset({
    "emotional_state", "current_struggle", "preferred_tone",
    "faith_stage", "journey_stage", "age_group", "gender",
    "display_name", "email",
})
# 운영자(by_operator=True)만 수정 가능한 필드
_OPERATOR_ONLY: frozenset[str] = frozenset({
    "salvation_status", "salvation_confidence", "assume_saved",
    "auth_status", "is_darakbang_member", "darakbang_role",
    "darakbang_chapter", "darakbang_verified", "darakbang_joined_at",
    "onboarding_step", "consent_data", "consent_kakao",
    "session_count", "total_questions",
})

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
    """사용자 프로필을 dict로 반환. 세션 밖에서도 안전하게 접근 가능."""
    with get_session() as s:
        row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not row:
            from ..config import settings as _cfg
            from datetime import timedelta
            now = datetime.utcnow()
            row = Subscriber(
                subscriber_id=sub_id,
                tokens_daily=_cfg.tokens_daily_guest,
                trial_expires_at=now + timedelta(days=3),  # 3일 무료체험 자동 부여
            )
            s.add(row)
            s.flush()
        elif row.trial_expires_at is None and row.subscription_tier == "guest":
            # 기존 guest 사용자 중 trial_expires_at 미설정 → first_seen_at 기준 소급 적용
            from datetime import timedelta
            base = row.first_seen_at or datetime.utcnow()
            row.trial_expires_at = base + timedelta(days=3)
        return _row_to_dict(row)


def prepare_profile(sub_id: str, signal: Dict[str, Any] | None = None) -> dict:
    """increment_question + merge_auto_signal + get_or_create 를 단일 세션으로 처리.

    chat.py 의 3회 개별 세션 호출을 1회로 통합해 DB 왕복을 줄인다.
    signal 이 없으면 카운트 증가 + 프로필 반환만 수행.
    """
    with get_session() as s:
        row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not row:
            from ..config import settings as _cfg
            row = Subscriber(
                subscriber_id=sub_id,
                tokens_daily=_cfg.tokens_daily_guest,
            )
            s.add(row)
            s.flush()

        row.total_questions = (row.total_questions or 0) + 1

        if signal:
            if signal.get("emotional_state") and not row.emotional_state:
                row.emotional_state = signal["emotional_state"]
            if signal.get("journey_hint") and not row.journey_stage:
                row.journey_stage = signal["journey_hint"]
            if signal.get("faith_hint") and not row.faith_stage:
                row.faith_stage = signal["faith_hint"]

        return _row_to_dict(row)

def get_all_subscribers() -> list[dict]:
    # ✏️ AI-CHANGE 2026-05-19 [Antigravity]: dict 리스트 반환으로 변경 (B5 일관성)
    # ❌ AI-REMOVE 2026-05-20 [Cascade]: is_believer 제거 (ORDERS B6 - salvation_status로 대체됨)
    with get_session() as s:
        subs = s.query(Subscriber).order_by(Subscriber.last_active_at.desc()).all()
        return [
            {
                "subscriber_id": sub.subscriber_id,
                "display_name": sub.display_name,
                "journey_stage": sub.journey_stage,
                "faith_stage": sub.faith_stage,
                "emotional_state": sub.emotional_state,
                "is_darakbang_member": sub.is_darakbang_member,
                "total_questions": sub.total_questions,
                "session_count": sub.session_count,
                "onboarding_step": sub.onboarding_step,
                "last_active_at": str(sub.last_active_at) if sub.last_active_at else None,
                "first_seen_at": str(sub.first_seen_at) if sub.first_seen_at else None,
            }
            for sub in subs
        ]

def update_profile(sub_id: str, fields: Dict[str, Any], *, by_operator: bool = False) -> dict:
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
        s.commit()
        s.refresh(sub)
    # 변경 후 최신 dict 반환
    return get_or_create(sub_id)

def increment_session(sub_id: str):
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub:
            sub.session_count += 1
            s.commit()

def increment_question(sub_id: str):
    """total_questions 원자적 증가 + last_active_at 갱신.

    벌크 UPDATE는 ORM onupdate 훅을 우회하므로 last_active_at 를 명시적으로 함께 갱신한다.
    """
    from datetime import datetime
    with get_session() as s:
        s.execute(
            sa_update(Subscriber)
            .where(Subscriber.subscriber_id == sub_id)
            .values(
                total_questions=Subscriber.total_questions + 1,
                last_active_at=datetime.utcnow(),
            )
        )

def merge_auto_signal(sub_id: str, signal: Dict[str, Any]):
    """AI가 추출한 사용자 상태 신호 병합 (빈 값만 채움)"""
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            return
            
        if "emotional_state" in signal and not sub.emotional_state:
            sub.emotional_state = signal["emotional_state"]
        if "journey_hint" in signal and not sub.journey_stage:
            sub.journey_stage = signal["journey_hint"]
        if "faith_hint" in signal and not sub.faith_stage:
            sub.faith_stage = signal["faith_hint"]
            
        s.commit()
