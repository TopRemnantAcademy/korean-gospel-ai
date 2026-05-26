"""E-C: 이메일 가입/로그인 인증 API.

POST /auth/signup    이메일 + 비밀번호 가입 (기존 guest 업그레이드 포함)
POST /auth/login     로그인 → JWT 반환
GET  /auth/me        현재 사용자 프로필 (토큰 잔량 포함)
POST /auth/logout    (client-side only, 토큰 블랙리스트 미구현)
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: E-C — 이메일 가입/로그인 + guest→member 업그레이드
# Reason: ORDERS.md EPIC E-C
# Status: COMPLETED
# =============================================================================
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr

from ..config import settings
from ..db import get_session
from ..models.orm import Subscriber
from ..services.token_service import grant_signup_bonus_sync, get_quota_status
from ..services.audit_service import log as audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


# ── 간단한 JWT 없이 HMAC 서명 토큰 (의존성 0) ────────────────────────────
_SECRET = (settings.admin_api_key + "_auth_secret").encode()


def _make_token(sub_id: str) -> str:
    ts = int(time.time())
    payload = f"{sub_id}:{ts}"
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def _verify_token(token: str) -> Optional[str]:
    """검증 성공 시 sub_id 반환, 실패 시 None."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        sub_id, ts_str, sig = parts
        ts = int(ts_str)
        if time.time() - ts > 86400 * 30:  # 30일 만료
            return None
        payload = f"{sub_id}:{ts_str}"
        expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        return sub_id
    except Exception:
        return None


def _hash_pw(password: str) -> str:
    return hashlib.sha256((password + settings.admin_api_key).encode()).hexdigest()


def get_current_user(authorization: Optional[str] = Header(default=None)) -> str:
    """Bearer 토큰 → sub_id. 실패 시 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "인증이 필요합니다.")
    token = authorization[7:]
    sub_id = _verify_token(token)
    if not sub_id:
        raise HTTPException(401, "유효하지 않거나 만료된 토큰입니다.")
    return sub_id


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────
class SignupReq(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    guest_sub_id: Optional[str] = None   # 기존 guest 대화 승계


class LoginReq(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    sub_id: str
    token: str
    subscription_tier: str
    tokens_bonus: int
    tokens_monthly: int
    tokens_daily: int
    display_name: Optional[str]
    is_new: bool


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse)
def signup(req: SignupReq):
    """이메일 가입. guest_sub_id 있으면 기존 대화 승계."""
    if not req.email or not req.password:
        raise HTTPException(400, "이메일과 비밀번호를 입력하세요.")
    if len(req.password) < 6:
        raise HTTPException(400, "비밀번호는 6자 이상이어야 합니다.")

    pw_hash = _hash_pw(req.password)

    with get_session() as s:
        # 이메일 중복 확인
        existing = s.query(Subscriber).filter(Subscriber.email == req.email).first()
        if existing and existing.auth_status == "email":
            raise HTTPException(409, "이미 가입된 이메일입니다.")

        if req.guest_sub_id:
            # 기존 guest 업그레이드
            sub = s.query(Subscriber).filter(Subscriber.subscriber_id == req.guest_sub_id).first()
            if sub and sub.subscription_tier == "guest":
                sub.email = req.email
                sub.display_name = req.display_name
                sub.auth_status = "email"
                sub.subscription_tier = "member"
                sub.subscribed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                sub.subscription_source = "email_signup"
                # password hash 는 별도 저장이 없으므로 consent 에 저장 (임시 — 별도 auth 테이블 FUTURE)
                sub.consent = {**(sub.consent or {}), "pw_hash": pw_hash}
                sub.tokens_monthly = settings.tokens_monthly_member
                sub_id = sub.subscriber_id
                is_new = False
            else:
                # guest 없거나 이미 member — 새로 생성
                sub = Subscriber(
                    email=req.email,
                    display_name=req.display_name,
                    auth_status="email",
                    subscription_tier="member",
                    subscribed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    subscription_source="email_signup",
                    tokens_daily=settings.tokens_daily_guest,
                    tokens_monthly=settings.tokens_monthly_member,
                    consent={"pw_hash": pw_hash},
                )
                s.add(sub)
                s.flush()
                sub_id = sub.subscriber_id
                is_new = True
        else:
            sub = Subscriber(
                email=req.email,
                display_name=req.display_name,
                auth_status="email",
                subscription_tier="member",
                subscribed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                subscription_source="email_signup",
                tokens_daily=settings.tokens_daily_guest,
                tokens_monthly=settings.tokens_monthly_member,
                consent={"pw_hash": pw_hash},
            )
            s.add(sub)
            s.flush()
            sub_id = sub.subscriber_id
            is_new = True

    # 가입 보너스 지급 (멱등)
    grant_signup_bonus_sync(sub_id)

    try:
        from ..db import get_session as _gs
        with _gs() as _s:
            audit_log(_s, action="auth.signup", entity_type="subscriber",
                      entity_id=sub_id, who=req.email, note={"source": "email", "is_new": is_new})
    except Exception:
        pass

    token = _make_token(sub_id)
    quota = get_quota_status(sub_id)
    return AuthResponse(
        sub_id=sub_id,
        token=token,
        subscription_tier=quota.get("subscription_tier", "member"),
        tokens_bonus=quota.get("tokens_bonus", 0),
        tokens_monthly=quota.get("tokens_monthly", 0),
        tokens_daily=quota.get("tokens_daily", 0),
        display_name=req.display_name,
        is_new=is_new,
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginReq):
    """이메일 로그인."""
    pw_hash = _hash_pw(req.password)
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.email == req.email).first()
        if not sub:
            raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")
        stored_hash = (sub.consent or {}).get("pw_hash")
        if stored_hash != pw_hash:
            raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")
        sub_id = sub.subscriber_id
        display_name = sub.display_name

    token = _make_token(sub_id)
    quota = get_quota_status(sub_id)
    return AuthResponse(
        sub_id=sub_id,
        token=token,
        subscription_tier=quota.get("subscription_tier", "member"),
        tokens_bonus=quota.get("tokens_bonus", 0),
        tokens_monthly=quota.get("tokens_monthly", 0),
        tokens_daily=quota.get("tokens_daily", 0),
        display_name=display_name,
        is_new=False,
    )


@router.get("/me")
def get_me(authorization: Optional[str] = Header(default=None)):
    """현재 로그인 사용자 프로필 + 토큰 잔량."""
    sub_id = get_current_user(authorization)
    from ..services.subscriber_service import get_or_create
    profile = get_or_create(sub_id)
    quota = get_quota_status(sub_id)
    return {**profile, **quota}
