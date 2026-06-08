"""사용자 관리 및 관제탑 API"""
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from ..services.subscriber_service import get_or_create, update_profile, get_all_subscribers
from ..config import settings
from .auth import get_current_user

log = logging.getLogger("gospel-api.subscriber")

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create API endpoints for Subscriber management
# Reason: 관제탑 UI와 클라이언트가 프로필을 조회하고 수정할 수 있도록 제공
# Related: backend/app/services/subscriber_service.py
# Status: COMPLETED
# =============================================================================

router = APIRouter(prefix="", tags=["subscriber"])


class UserProfileUpdateReq(BaseModel):
    """일반 사용자가 직접 수정할 수 있는 필드만 포함.
    운영자 전용 필드(salvation_status, assume_saved, darakbang_role, darakbang_verified)는 제외.
    """
    display_name: Optional[str] = None
    journey_stage: Optional[str] = None
    faith_stage: Optional[str] = None
    emotional_state: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    current_struggle: Optional[str] = None
    preferred_tone: Optional[str] = None
    is_darakbang_member: Optional[bool] = None
    darakbang_chapter: Optional[str] = None   # 사용자 자기신고 허용
    consent_data: Optional[bool] = None
    consent_kakao: Optional[bool] = None


class ProfileUpdateReq(BaseModel):
    """운영자용 전체 프로필 수정 (운영자 전용 필드 포함)."""
    display_name: Optional[str] = None
    journey_stage: Optional[str] = None
    faith_stage: Optional[str] = None
    emotional_state: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    current_struggle: Optional[str] = None
    preferred_tone: Optional[str] = None
    is_darakbang_member: Optional[bool] = None
    consent_data: Optional[bool] = None
    consent_kakao: Optional[bool] = None
    # 운영자 전용 필드
    salvation_status: Optional[str] = None
    assume_saved: Optional[bool] = None
    darakbang_role: Optional[str] = None
    darakbang_chapter: Optional[str] = None
    darakbang_verified: Optional[bool] = None


def _check_admin(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        log.warning("Admin auth failed: missing or malformed Authorization header")
        raise HTTPException(status_code=403, detail="missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_api_key:
        log.warning("Admin auth failed: invalid token presented")
        raise HTTPException(status_code=403, detail="invalid admin token")

@router.get("/subscribers/me")
def get_my_profile(current_user: str = Depends(get_current_user)):
    sub = get_or_create(current_user)
    return sub


@router.patch("/subscribers/me")
def update_my_profile(req: UserProfileUpdateReq, current_user: str = Depends(get_current_user)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    sub = update_profile(current_user, fields, by_operator=False)
    return sub

@router.get("/admin/subscribers/list")
def list_all_subscribers(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    subs = get_all_subscribers()
    return {"subscribers": subs}

@router.get("/admin/subscribers/categories")
def get_categories(type: Optional[str] = None, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    from ..db import get_session
    from ..models.orm import Category
    with get_session() as s:
        q = s.query(Category)
        if type:
            q = q.filter(Category.category_type == type)
        return {"categories": [{"type": c.category_type, "name": c.name, "desc": c.description} for c in q.all()]}

@router.get("/admin/subscribers/{sub_id}")
def get_subscriber(sub_id: str, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    sub = get_or_create(sub_id)
    return sub

@router.patch("/admin/subscribers/{sub_id}")
def admin_update_profile(sub_id: str, req: ProfileUpdateReq, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    sub = update_profile(sub_id, fields, by_operator=True)
    return sub


# ─────────────────────────────────────────
# D-C22: assume_saved 전용 토글 + AuditLog
# ─────────────────────────────────────────
class AssumeSavedReq(BaseModel):
    value: bool
    reason: Optional[str] = None
    # 동시에 salvation_status 도 변경 가능 (선택)
    also_set_status: Optional[str] = None


@router.patch("/admin/subscribers/{sub_id}/assume-saved")
def toggle_assume_saved(
    sub_id: str,
    req: AssumeSavedReq,
    authorization: Optional[str] = Header(default=None),
):
    """D-C22: assume_saved 토글 + AuditLog 기록.

    신학적 안전장치: assume_saved 와 salvation_status 는 독립.
    assume_saved=True 가 되어도 LLM 구원 신호 감지는 계속 진행됨.
    """
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import Subscriber, AuditLog
    from datetime import datetime

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="subscriber not found")

        prev_value = sub.assume_saved
        sub.assume_saved = req.value

        if req.also_set_status and req.also_set_status in (
            "unknown", "seeker", "uncertain", "assured", "mature"
        ):
            sub.salvation_status = req.also_set_status

        s.add(AuditLog(
            who="admin",
            action="subscriber.assume_saved_toggle",
            entity_type="subscriber",
            entity_id=sub_id,
            from_state=str(prev_value),
            to_state=str(req.value),
            note={"reason": req.reason or "", "also_set_status": req.also_set_status},
        ))

    return {
        "subscriber_id": sub_id,
        "assume_saved": req.value,
        "prev": prev_value,
        "also_set_status": req.also_set_status,
    }


# ─────────────────────────────────────────
# D-C20: 영적 상태 대시보드 API
# ─────────────────────────────────────────
@router.get("/admin/spiritual/stats")
def spiritual_stats(authorization: Optional[str] = Header(default=None)):
    """D-C20 탭 1: salvation_status 분포 + 다락방·assume_saved 현황."""
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import Subscriber

    with get_session() as s:
        subs = s.query(Subscriber).all()

    total = len(subs)
    status_dist: dict[str, int] = {}
    darakbang_verified = 0
    assume_saved_count = 0
    for sub in subs:
        st = sub.salvation_status or "unknown"
        status_dist[st] = status_dist.get(st, 0) + 1
        if sub.darakbang_verified:
            darakbang_verified += 1
        if sub.assume_saved:
            assume_saved_count += 1

    return {
        "total": total,
        "salvation_status_dist": status_dist,
        "darakbang_verified": darakbang_verified,
        "assume_saved_count": assume_saved_count,
    }


@router.get("/admin/spiritual/journey")
def spiritual_journey(days: int = 30, authorization: Optional[str] = Header(default=None)):
    """D-C20 탭 2: SalvationJourney 전환 흐름 (Sankey 데이터)."""
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import SalvationJourney
    from datetime import datetime, timedelta

    since = datetime.now(datetime.UTC) - timedelta(days=days)
    with get_session() as s:
        rows = s.query(SalvationJourney).filter(
            SalvationJourney.created_at >= since
        ).all()

    flows: dict[str, int] = {}
    for r in rows:
        key = f"{r.from_status}→{r.to_status}"
        flows[key] = flows.get(key, 0) + 1

    return {"period_days": days, "total_transitions": len(rows), "flows": flows}


@router.get("/admin/spiritual/stagnant")
def spiritual_stagnant(
    stagnant_days: int = 30,
    authorization: Optional[str] = Header(default=None),
):
    """D-C20 탭 3: 장기 정체 사용자 (stagnant_days 이상 같은 status)."""
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import Subscriber
    from datetime import datetime, timedelta

    cutoff = datetime.now(datetime.UTC) - timedelta(days=stagnant_days)
    with get_session() as s:
        subs = s.query(Subscriber).filter(
            Subscriber.salvation_last_signal_at.isnot(None)
        ).all()
        # last_signal 이 없거나 cutoff 이전인 사람 = 정체
        stagnant = [
            {
                "subscriber_id": sub.subscriber_id,
                "display_name": sub.display_name,
                "salvation_status": sub.salvation_status,
                "last_signal_at": str(sub.salvation_last_signal_at),
                "total_questions": sub.total_questions,
            }
            for sub in subs
            if sub.salvation_last_signal_at and sub.salvation_last_signal_at < cutoff
        ]
        # last_signal 자체가 없는 사람 (unknown 에 고착)
        no_signal = s.query(Subscriber).filter(
            Subscriber.salvation_last_signal_at.is_(None),
            Subscriber.total_questions >= 3,
        ).all()
        stagnant += [
            {
                "subscriber_id": sub.subscriber_id,
                "display_name": sub.display_name,
                "salvation_status": sub.salvation_status or "unknown",
                "last_signal_at": None,
                "total_questions": sub.total_questions,
            }
            for sub in no_signal
        ]

    return {"stagnant_days": stagnant_days, "count": len(stagnant), "users": stagnant}


@router.get("/admin/spiritual/darakbang-matrix")
def darakbang_matrix(authorization: Optional[str] = Header(default=None)):
    """D-C20 탭 4: darakbang_role × salvation_status 매트릭스."""
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import Subscriber

    with get_session() as s:
        members = s.query(Subscriber).filter(
            Subscriber.is_darakbang_member.is_(True)
        ).all()

    matrix: dict[str, dict[str, int]] = {}
    for sub in members:
        role = sub.darakbang_role or "member"
        status = sub.salvation_status or "unknown"
        matrix.setdefault(role, {})
        matrix[role][status] = matrix[role].get(status, 0) + 1

    # 긴급: 인도자인데 uncertain/seeker
    urgent = [
        {
            "subscriber_id": sub.subscriber_id,
            "display_name": sub.display_name,
            "darakbang_role": sub.darakbang_role,
            "salvation_status": sub.salvation_status,
        }
        for sub in members
        if sub.darakbang_role in ("leader", "pastor")
        and sub.salvation_status in ("unknown", "seeker", "uncertain")
    ]

    return {"matrix": matrix, "urgent_count": len(urgent), "urgent": urgent}


# ─────────────────────────────────────────
# E-A: 토큰 쿼터 API
# ─────────────────────────────────────────

@router.get("/subscribers/me/quota")
def get_my_quota(current_user: str = Depends(get_current_user)):
    """현재 사용자 토큰 잔량 조회 (User UI 표시용)."""
    from ..services.token_service import get_quota_status
    return get_quota_status(current_user)


class GrantTokensReq(BaseModel):
    sub_id: str
    amount: int
    reason: Optional[str] = None


@router.post("/admin/tokens/grant")
def admin_grant_tokens(req: GrantTokensReq, authorization: Optional[str] = Header(default=None)):
    """운영자: 특정 사용자에게 보너스 토큰 지급."""
    from ..services.token_service import get_quota_status
    from ..db import get_session
    from ..models.orm import Subscriber
    _check_admin(authorization)
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == req.sub_id).first()
        if not sub:
            raise HTTPException(404, "subscriber not found")
        sub.tokens_bonus = (sub.tokens_bonus or 0) + req.amount
    return {"granted": req.amount, "reason": req.reason, **get_quota_status(req.sub_id)}


@router.get("/admin/tokens/stats")
def admin_token_stats(authorization: Optional[str] = Header(default=None)):
    """토큰 사용 현황 집계."""
    _check_admin(authorization)
    from ..db import get_session
    from ..models.orm import Subscriber
    from sqlalchemy import func
    with get_session() as s:
        rows = s.query(
            Subscriber.subscription_tier,
            func.count(Subscriber.subscriber_id).label("count"),
            func.sum(Subscriber.tokens_lifetime_used).label("total_used"),
            func.sum(Subscriber.tokens_daily).label("total_daily_remaining"),
        ).group_by(Subscriber.subscription_tier).all()
        return [
            {
                "tier": r.subscription_tier,
                "count": r.count,
                "total_used": r.total_used or 0,
                "total_daily_remaining": r.total_daily_remaining or 0,
            }
            for r in rows
        ]
