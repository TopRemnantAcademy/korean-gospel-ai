"""사용자 관리 및 관제탑 API"""
from __future__ import annotations
import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from pydantic import BaseModel

from ..services.subscriber_service import get_or_create, update_profile, get_all_subscribers
from ..services import email_service, settings_service
from ..db import get_session
from ..models.orm import Subscriber
from ..models.schemas import (
    UserProfileUpdateReq, ProfileUpdateReq,
    AssumeSavedReq,
)
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

# 요청/응답 모델 → models/schemas.py 로 이전됨
# (UserProfileUpdateReq, ProfileUpdateReq, AssumeSavedReq)


from .auth import check_admin as _check_admin

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
def list_all_subscribers(
    limit: int = Query(10000, ge=1, le=10000, description="반환할 최대 사용자 수"),
    offset: int = Query(0, ge=0, description="건너뛸 사용자 수"),
    authorization: Optional[str] = Header(default=None),
):
    """BUG-09 수정: limit/offset 쿼리 파라미터 지원.

    기존에는 프론트엔드가 전달한 limit/offset 을 무시하고 전체 목록을 반환했음.
    호환성 유지를 위해 기본 limit=10000 (사실상 전체) 사용.
    """
    _check_admin(authorization)
    subs = get_all_subscribers(limit=limit, offset=offset)
    return {"subscribers": subs, "total": len(subs), "limit": limit, "offset": offset}

@router.get("/admin/subscribers/categories")
def get_categories(category_type: Optional[str] = None, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    from ..db import get_session
    from ..models.orm import Category
    with get_session() as s:
        q = s.query(Category)
        if category_type:
            q = q.filter(Category.category_type == category_type)
        return {"categories": [{"type": c.category_type, "name": c.name, "desc": c.description} for c in q.all()]}

@router.get("/admin/subscribers/{sub_id}")
def get_subscriber(sub_id: str, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    # ⚠️ get_or_create 가 아닌 조회 전용: 존재하지 않는 sub_id 로 요청 시
    # 레코드를 자동 생성하는 부수효과를 막기 위해 404 처리.
    from ..db import get_session
    from ..models.orm import Subscriber
    from ..services.subscriber_service import _row_to_dict
    with get_session() as s:
        row = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
    if row is None:
        raise HTTPException(404, "Subscriber not found")
    return _row_to_dict(row)

@router.patch("/admin/subscribers/{sub_id}")
def admin_update_profile(sub_id: str, req: ProfileUpdateReq, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    sub = update_profile(sub_id, fields, by_operator=True)
    return sub


# ─────────────────────────────────────────
# D-C22: assume_saved 전용 토글 + AuditLog
# ─────────────────────────────────────────
# AssumeSavedReq → models/schemas.py 로 이전됨

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
    from sqlalchemy import func

    with get_session() as s:
        # 전체 로드 대신 DB 집계(GROUP BY + COUNT)로 처리 → 전체 테이블 스캔/메모리 폭발 방지
        total = s.query(func.count(Subscriber.subscriber_id)).scalar() or 0

        status_rows = (
            s.query(
                Subscriber.salvation_status,
                func.count(Subscriber.subscriber_id),
            )
            .group_by(Subscriber.salvation_status)
            .all()
        )
        status_dist = {st or "unknown": cnt for st, cnt in status_rows}

        darakbang_verified = (
            s.query(func.count(Subscriber.subscriber_id))
            .filter(Subscriber.darakbang_verified.is_(True))
            .scalar()
            or 0
        )
        assume_saved_count = (
            s.query(func.count(Subscriber.subscriber_id))
            .filter(Subscriber.assume_saved.is_(True))
            .scalar()
            or 0
        )

    return {
        "total": total,
        "salvation_status_dist": status_dist,
        "darakbang_verified": darakbang_verified,
        "assume_saved_count": assume_saved_count,
    }


# ─────────────────────────────────────────
# 🤖 봇 관리 API
# ─────────────────────────────────────────
@router.get("/admin/bot/stats")
def bot_stats(authorization: Optional[str] = Header(default=None)):
    """봇 관리 통계: flagged_as_bot 분포, bot_score 분포."""
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import Subscriber
    from sqlalchemy import func

    with get_session() as s:
        total = s.query(func.count(Subscriber.subscriber_id)).scalar() or 0

        # flagged_as_bot count
        flagged_count = (
            s.query(func.count(Subscriber.subscriber_id))
            .filter(Subscriber.flagged_as_bot.is_(True))
            .scalar()
            or 0
        )

        # high bot_score (>0.5, not flagged yet) — 의심
        suspicious_count = (
            s.query(func.count(Subscriber.subscriber_id))
            .filter(
                Subscriber.flagged_as_bot.is_(False),
                Subscriber.bot_score >= 0.5,
            )
            .scalar()
            or 0
        )

        # 평균 bot_score
        avg_score = (
            s.query(func.avg(Subscriber.bot_score)).scalar() or 0.0
        )

    return {
        "total_subscribers": total,
        "flagged_as_bot": flagged_count,
        "suspicious": suspicious_count,
        "avg_bot_score": round(float(avg_score), 4),
    }


@router.get("/admin/bot/list")
def bot_list(
    filter_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    authorization: Optional[str] = Header(default=None),
):
    """봇 관리 대상 사용자 목록.
    
    filter_type:
      - "flagged"  → flagged_as_bot = True
      - "suspicious" → flagged_as_bot = False AND bot_score >= 0.5
      - None → 전체 (기본)
    """
    _check_admin(authorization)

    from ..db import get_session
    from ..models.orm import Subscriber

    limit = max(1, min(limit, 1000))
    offset = max(0, offset)

    with get_session() as s:
        q = s.query(Subscriber)

        if filter_type == "flagged":
            q = q.filter(Subscriber.flagged_as_bot.is_(True))
        elif filter_type == "suspicious":
            q = q.filter(
                Subscriber.flagged_as_bot.is_(False),
                Subscriber.bot_score >= 0.5,
            )

        total_count = q.count()
        rows = q.order_by(Subscriber.bot_score.desc()).offset(offset).limit(limit).all()

        subscribers = [
            {
                "subscriber_id": row.subscriber_id,
                "display_name": row.display_name,
                "flagged_as_bot": row.flagged_as_bot,
                "bot_score": row.bot_score or 0.0,
                "total_questions": row.total_questions or 0,
                "salvation_status": row.salvation_status,
                "last_active_at": str(row.last_active_at) if row.last_active_at else None,
                "first_seen_at": str(row.first_seen_at) if row.first_seen_at else None,
                "emotional_state": row.emotional_state,
                "current_struggle": row.current_struggle,
            }
            for row in rows
        ]

    return {
        "subscribers": subscribers,
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


# ─────────────────────────────────────────
# 📧 이메일 인증 / 티어 관리 API (2026-07-23)
# ─────────────────────────────────────────
class _SetTierReq(BaseModel):
    tier: str  # free | standard | premium | lifetime
    expires_at: Optional[str] = None  # 구독 만료일(YYYY-MM-DD), free/lifetime 는 미사용



class _SetSettingReq(BaseModel):
    key: str
    value: object


@router.post("/admin/subscribers/{sub_id}/resend-verification")
def admin_resend_verification(sub_id: str, request: Request, authorization: Optional[str] = Header(default=None)):
    """관리자: 인증 메일 재발송."""
    _check_admin(authorization)
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(404, "사용자를 찾을 수 없습니다.")
        if sub.email_verified:
            raise HTTPException(400, "이미 인증된 사용자입니다.")
        if not sub.email:
            raise HTTPException(400, "이메일이 없는 사용자입니다.")
        vtoken = email_service.generate_verify_token(sub.subscriber_id)
        sub.email_verify_token = vtoken
        sub.email_verify_sent_at = datetime.datetime.utcnow()
        s.flush()
        verify_url = str(request.base_url).rstrip("/") + "/auth/verify-email?token=" + vtoken
        ok = email_service.send_verification_email(
            to=sub.email, name=sub.display_name or "", verify_url=verify_url, lang="ko"
        )
    return {"ok": ok, "message": "인증 메일을 재발송했습니다."}


@router.post("/admin/subscribers/{sub_id}/verify")
def admin_verify_override(sub_id: str, authorization: Optional[str] = Header(default=None)):
    """관리자: 이메일 인증을 수동으로 완료 처리 (오버라이드)."""
    _check_admin(authorization)
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(404, "사용자를 찾을 수 없습니다.")
        sub.email_verified = True
        sub.email_verified_at = datetime.datetime.utcnow()
        sub.email_verify_token = None
        s.flush()
    return {"ok": True, "email_verified": True}


@router.post("/admin/subscribers/{sub_id}/set-tier")
def admin_set_tier(sub_id: str, req: _SetTierReq, authorization: Optional[str] = Header(default=None)):
    """관리자: 구독 티어/만료일 변경 (free/standard/premium/lifetime)."""
    _check_admin(authorization)
    if req.tier not in ("free", "standard", "premium", "lifetime"):
        raise HTTPException(400, "잘못된 티어입니다.")
    fields = {"subscription_tier": req.tier}
    if req.tier == "lifetime":
        fields["is_lifetime_member"] = True
        fields["subscription_expires_at"] = None
    elif req.tier == "free":
        fields["is_lifetime_member"] = False
        fields["subscription_expires_at"] = None
    else:
        fields["is_lifetime_member"] = False
        if req.expires_at:
            try:
                fields["subscription_expires_at"] = datetime.datetime.strptime(req.expires_at, "%Y-%m-%d")
            except (ValueError, TypeError):
                raise HTTPException(400, "만료일 형식이 올바르지 않습니다 (YYYY-MM-DD).")
    return update_profile(sub_id, fields, by_operator=True)


@router.get("/admin/settings/app")
def admin_get_settings(authorization: Optional[str] = Header(default=None)):
    """관리자: 런타임 설정(이메일 인증/질문 할당량 토글) 조회."""
    _check_admin(authorization)
    return {"settings": settings_service.all_settings()}


@router.post("/admin/settings/app")
def admin_set_settings(req: _SetSettingReq, authorization: Optional[str] = Header(default=None)):
    """관리자: 런타임 설정 저장 (bool/int 자동 판별)."""
    _check_admin(authorization)
    if isinstance(req.value, bool):
        settings_service.set_bool(req.key, req.value)
    elif isinstance(req.value, str):
        # greeting_sub 등 문자열 설정도 저장 가능
        try:
            int(req.value)
            settings_service.set_int(req.key, int(req.value))
        except (TypeError, ValueError):
            settings_service.set_str(req.key, req.value)
    else:
        try:
            settings_service.set_int(req.key, int(req.value))
        except (TypeError, ValueError):
            raise HTTPException(400, "정수, 불, 또는 문자열 값만 저장할 수 있습니다.")
    return {"ok": True, "key": req.key, "value": req.value}
