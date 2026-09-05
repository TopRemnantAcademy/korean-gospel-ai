"""PortOne 결제 API 라우터.

엔드포인트:
  GET  /api/payment/plans     — 공개: 구독 플랜 목록 + store_id
  POST /api/payment/prepare   — 인증: 플랜 선택 → PortOne 예약 결제(txId) 발급 + DB 기록
  POST /api/payment/complete  — 인증: 클라이언트 결제 완료 후 서버 검증 → 구독 승급
  POST /api/payment/webhook   — 공개: PortOne 웹훅(서명 검증 후 동일 승급 처리)

결제 금액은 항상 서버(prepare)가 결정한다(클라이언트 변조 방지).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from ..config import settings
from ..db import get_session_immediate
from ..models.orm import Payment, Subscriber
from ..api.auth import get_current_user
from ..services import portone_service as portone

log = logging.getLogger("payment")

router = APIRouter(prefix="/api/payment", tags=["payment"])

# ── 구독 플랜 (KRW) ───────────────────────────────────────────────────────────
# tier: subscriber.subscription_tier 로 매핑. lifetime 는 평생 멤버.
_PLANS: dict = {
    "standard_monthly": {
        "tier": "standard", "name": "스탠다드 (월간)", "amount": 3900,
        "currency": "KRW", "duration_days": 30, "pay_method": "CARD",
    },
    "premium_monthly": {
        "tier": "premium", "name": "프리미엄 (월간)", "amount": 9900,
        "currency": "KRW", "duration_days": 30, "pay_method": "CARD",
    },
    "premium_yearly": {
        "tier": "premium", "name": "프리미엄 (연간)", "amount": 99000,
        "currency": "KRW", "duration_days": 365, "pay_method": "CARD",
    },
    "lifetime": {
        "tier": "lifetime", "name": "평생 멤버 (1회 결제)", "amount": 299000,
        "currency": "KRW", "duration_days": 36500, "pay_method": "CARD",
    },
}


class PrepareReq(BaseModel):
    plan_id: str


class CompleteReq(BaseModel):
    payment_id: str


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def _dig(d: dict, *keys: str) -> Optional[object]:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _public_plans() -> list[dict]:
    return [{"plan_id": k, **v} for k, v in _PLANS.items()]


def _paid_amount(p: dict) -> Optional[int]:
    """PortOne 결제 응답에서 실제 결제된 총액 추출 (V2 amount.total / V1 호환 필드)."""
    amt = _dig(p, "amount", "total")
    if amt is None:
        amt = (
            _dig(p, "amount", "paid")
            or _dig(p, "paidAmount")
            or p.get("totalAmount")
        )
    try:
        return int(amt) if amt is not None else None
    except (TypeError, ValueError):
        return None


def _verify_paid_amount(rec: Payment, p: dict) -> Optional[str]:
    """[P0-4] 결제 금액이 플랜 금액과 일치하는지 서버 측 재검증.

    미검증 시 1원 결제로 프리미엄 구독을 여는 변조가 가능했다.
    불일치 시 오류 메시지, 일치 시 None 반환.
    """
    plan = _PLANS.get(rec.plan_id)
    if not plan:
        return f"알 수 없는 플랜: {rec.plan_id}"
    paid = _paid_amount(p)
    if paid is None:
        return "결제 금액 정보를 확인할 수 없습니다."
    if paid != plan["amount"]:
        return f"결제 금액 불일치: 플랜 {plan['amount']}원 / 실결제 {paid}원"
    return None


def _apply_subscription(s, rec: Payment, p: dict) -> None:
    """결제 완료 → subscriber 구독 승급 + Payment 기록 갱신."""
    plan = _PLANS.get(rec.plan_id)
    now = datetime.now(timezone.utc)
    sub = s.get(Subscriber, rec.subscriber_id)
    if sub and plan:
        if plan["tier"] == "lifetime":
            sub.subscription_tier = "lifetime"
            sub.is_lifetime_member = True
            sub.subscription_expires_at = None
        else:
            base = sub.subscription_expires_at
            new_exp = (
                base + timedelta(days=plan["duration_days"])
                if base and base > now
                else now + timedelta(days=plan["duration_days"])
            )
            sub.subscription_tier = plan["tier"]
            sub.subscription_expires_at = new_exp
    rec.status = "paid"
    rec.paid_at = now
    rec.portone_tx_id = p.get("txId")
    m = p.get("method")
    rec.method = m.get("type") if isinstance(m, dict) else m
    rec.raw = p
    s.commit()


# ── 라우트 ───────────────────────────────────────────────────────────────────
@router.get("/plans")
async def plans():
    return {"plans": _public_plans(), "store_id": settings.portone_store_id}


@router.post("/prepare")
async def prepare(body: PrepareReq, sub_id: str = Depends(get_current_user)):
    plan = _PLANS.get(body.plan_id)
    if not plan:
        return JSONResponse(status_code=400, content={"detail": "알 수 없는 플랜입니다."})

    if not settings.portone_store_id or not settings.portone_api_secret:
        return JSONResponse(status_code=503, content={"detail": "PortOne 가 미설정되었습니다."})
    if not settings.portone_channel_key:
        return JSONResponse(
            status_code=503,
            content={"detail": "PortOne 채널키(PORTONE_CHANNEL_KEY)가 설정되지 않았습니다. 포트원 콘솔에서 발급하세요."},
        )

    payment_id = "pay_" + uuid.uuid4().hex
    try:
        # V2 pre-register: 서버가 금액 결정(클라이언트 변조 방지). 채널/주문명은 클라이언트 SDK에서.
        await portone.create_payment(
            payment_id=payment_id,
            store_id=settings.portone_store_id,
            total_amount=plan["amount"],
            currency=plan["currency"],
        )
    except Exception as e:  # noqa: BLE001
        log.exception("[payment] PortOne 사전등록 실패")
        return JSONResponse(
            status_code=502, content={"detail": "결제 생성 실패: " + str(e)}
        )

    with get_session_immediate() as s:
        s.add(
            Payment(
                payment_id=payment_id,
                subscriber_id=sub_id,
                plan_id=body.plan_id,
                tier=plan["tier"],
                amount=plan["amount"],
                currency=plan["currency"],
                status="pending",
                portone_payment_id=payment_id,
            )
        )
        s.commit()

    # 클라이언트는 paymentId + 채널키로 PortOne.requestPayment({ paymentId, channelKey, ... }) 수행
    return {
        "payment_id": payment_id,
        "store_id": settings.portone_store_id,
        "channel_key": settings.portone_channel_key,
        "order_name": plan["name"],
        "total_amount": plan["amount"],
        "currency": plan["currency"],
        "pay_method": plan["pay_method"],
        "customer": {"id": sub_id},
    }


@router.post("/complete")
async def complete(body: CompleteReq, sub_id: str = Depends(get_current_user)):
    with get_session_immediate() as s:
        rec = s.get(Payment, body.payment_id)
        if not rec or rec.subscriber_id != sub_id:
            return JSONResponse(status_code=404, content={"detail": "결제 정보를 찾을 수 없습니다."})
        if rec.status == "paid":
            return {"status": "paid", "tier": rec.tier,
                    "expires_at": rec.paid_at.isoformat() if rec.paid_at else None}
        try:
            p = await portone.get_payment(rec.portone_payment_id or body.payment_id)
        except Exception as e:  # noqa: BLE001
            log.exception("[payment] PortOne 결제 조회 실패")
            return JSONResponse(status_code=502, content={"detail": "결제 조회 실패: " + str(e)})

        if not portone.is_paid(p.get("status")):
            rec.status = (p.get("status") or "unknown").lower()
            s.commit()
            return JSONResponse(
                status_code=402,
                content={"detail": "결제가 완료되지 않았습니다.", "status": p.get("status")},
            )
        # [P0-4] 결제 금액 서버 측 재검증 — 플랜 금액과 불일치 시 승급 거부
        amt_err = _verify_paid_amount(rec, p)
        if amt_err:
            rec.status = "amount_mismatch"
            s.commit()
            log.error("[payment] 금액 검증 실패 (payment_id=%s): %s", rec.payment_id, amt_err)
            return JSONResponse(status_code=402, content={"detail": amt_err})
        _apply_subscription(s, rec, p)
        return {
            "status": "paid",
            "tier": rec.tier,
            "expires_at": rec.paid_at.isoformat() if rec.paid_at else None,
        }


def _verify_webhook_signature(raw: bytes, headers) -> None:
    # [P0-3] fail-closed: 시크릿 미설정 시 검증 생략이 아니라 거부한다.
    # (기존에는 미설정 시 silently return → 위조 웹훅 무제한 허용)
    if not settings.portone_webhook_secret:
        log.error(
            "[payment] PORTONE_WEBHOOK_SECRET 미설정 — 웹훅을 거부합니다(fail-closed). "
            "PortOne 콘솔에서 웹훅 시크릿을 발급해 .env 에 설정하세요."
        )
        raise HTTPException(status_code=503, detail="webhook secret not configured")
    sig = headers.get("webhook-signature")
    if not sig:
        raise HTTPException(status_code=403, detail="missing signature")
    parts = dict(x.split("=", 1) for x in sig.split(",") if "=" in x)
    v1 = parts.get("v1")
    t = parts.get("t", "")
    if not v1:
        raise HTTPException(status_code=403, detail="bad signature")
    expected = hmac.new(
        settings.portone_webhook_secret.encode(),
        t.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, v1):
        raise HTTPException(status_code=403, detail="invalid signature")


@router.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    _verify_webhook_signature(raw, request.headers)  # 미설정/검증실패 시 403
    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    pid = (
        _dig(payload, "data", "paymentId")
        or _dig(payload, "data", "payment", "id")
        or payload.get("paymentId")
        or _dig(payload, "payment", "id")
    )
    if not pid:
        return JSONResponse({"received": True})

    with get_session_immediate() as s:
        rec = s.query(Payment).filter(Payment.portone_payment_id == str(pid)).first()
        if not rec:
            return JSONResponse({"received": True})
        # [P0-2] 멱등성 가드: 이미 승급 처리된 결제는 재적용하지 않는다.
        # PortOne 웹훅 재시도가 구독 기간을 이중 연장하는 것을 방지.
        if rec.status == "paid":
            return JSONResponse({"received": True})
        try:
            p = await portone.get_payment(str(pid))
        except Exception as e:  # noqa: BLE001
            log.warning("[payment] webhook 결제 조회 실패 (무시): %s", e)
            return JSONResponse({"received": True})
        if portone.is_paid(p.get("status")):
            # [P0-4] 웹훅 경로에서도 금액 재검증 — 불일치 시 승급 거부
            amt_err = _verify_paid_amount(rec, p)
            if amt_err:
                rec.status = "amount_mismatch"
                s.commit()
                log.error(
                    "[payment] webhook 금액 검증 실패 (payment_id=%s): %s",
                    rec.payment_id, amt_err,
                )
                return JSONResponse({"received": True})
            _apply_subscription(s, rec, p)
    return JSONResponse({"received": True})
