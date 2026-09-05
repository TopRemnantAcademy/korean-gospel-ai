"""PortOne V2 결제 게이트웨이 연동 서비스.

인증 흐름:
  - ``POST /login/api-secret`` (apiSecret) → accessToken(30분) + refreshToken(1일)
  - ``POST /token/refresh`` (refreshToken) → 새 accessToken + refreshToken
  - accessToken 은 ``Authorization: Bearer`` 헤더로 전달.

결제 흐름(보안 권장 방식 — 금액은 서버가 결정):
  1. 서버가 ``POST /payments/{paymentId}/pre-register`` 로 금액 사전 등록(서버 결정)
  2. 클라이언트가 ``PortOne.requestPayment({ paymentId, channelKey, ... })`` 로 결제 수행
  3. 서버가 ``GET /payments/{paymentId}`` 로 상태 검증 → PAID 면 구독 승급

  ※ PortOne V2 에는 결제 '생성' 단일 엔드포인트(``POST /payments``)가 없으며,
    pre-register → requestPayment 흐름을 사용한다(직접 POST /payments 는 405).

토큰은 모듈 레벨에 캐시하며 코루틴 안전하게 갱신한다(만료 5분 전 갱신).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from ..config import settings

log = logging.getLogger("portone")

# ── 토큰 캐시 (단일 프로세스) ────────────────────────────────────────────────
_TOKEN: dict = {"access": None, "refresh": None, "exp": 0.0}
_LOCK = asyncio.Lock()
_EXPIRY_MARGIN = 5 * 60  # 5분 전부터 갱신


async def _post_json(path: str, json: dict) -> dict:
    async with httpx.AsyncClient(base_url=settings.portone_api_base, timeout=15) as c:
        r = await c.post(path, json=json)
        r.raise_for_status()
        return r.json()


async def _login() -> dict:
    if not settings.portone_api_secret:
        raise RuntimeError("PORTONE_API_SECRET 가 설정되지 않았습니다.")
    d = await _post_json("/login/api-secret", {"apiSecret": settings.portone_api_secret})
    return {
        "access": d["accessToken"],
        "refresh": d.get("refreshToken"),
        "exp": time.time() + 25 * 60,  # 실제 30분 → 25분으로 여유
    }


async def _refresh(refresh_token: str) -> dict:
    d = await _post_json("/token/refresh", {"refreshToken": refresh_token})
    return {
        "access": d["accessToken"],
        "refresh": d.get("refreshToken", refresh_token),
        "exp": time.time() + 25 * 60,
    }


async def get_access_token() -> str:
    """유효한 액세스 토큰 반환(필요 시 갱신)."""
    global _TOKEN
    async with _LOCK:
        if _TOKEN.get("access") and _TOKEN["exp"] > time.time() + _EXPIRY_MARGIN:
            return _TOKEN["access"]
        try:
            if _TOKEN.get("refresh"):
                _TOKEN = await _refresh(_TOKEN["refresh"])
            else:
                _TOKEN = await _login()
        except Exception:
            # 갱신 실패 → 재로그인(refresh 토큰 폐기 상태일 수 있음)
            log.warning("[portone] 토큰 갱신 실패 → 재로그인 시도")
            _TOKEN = await _login()
        return _TOKEN["access"]


async def _auth_headers() -> dict:
    return {
        "Authorization": "Bearer " + await get_access_token(),
        "Content-Type": "application/json",
    }


async def create_payment(
    *,
    payment_id: str,
    store_id: str,
    total_amount: int,
    currency: str = "KRW",
) -> None:
    """PortOne V2 사전 등록(pre-register): 서버가 금액을 결정해 등록한다.

    채널/주문명/고객정보는 클라이언트 SDK(``PortOne.requestPayment``)에서 처리하므로
    여기선 금액만 전송한다. (V2 에는 결제 '생성' 단일 엔드포인트가 없음 —
    ``POST /payments/{paymentId}/pre-register`` 를 사용. 직접 POST /payments 는 405.)
    """
    body = {
        "storeId": store_id,
        "totalAmount": total_amount,
        "currency": currency,
    }
    async with httpx.AsyncClient(base_url=settings.portone_api_base, timeout=30) as c:
        r = await c.post(
            f"/payments/{payment_id}/pre-register",
            headers=await _auth_headers(),
            json=body,
        )
        r.raise_for_status()
    return None


async def get_payment(payment_id: str) -> dict:
    """paymentId 로 결제 상태 조회."""
    async with httpx.AsyncClient(base_url=settings.portone_api_base, timeout=30) as c:
        r = await c.get(f"/payments/{payment_id}", headers=await _auth_headers())
        r.raise_for_status()
        return r.json()


def is_paid(status: Optional[str]) -> bool:
    return (status or "").upper() == "PAID"
