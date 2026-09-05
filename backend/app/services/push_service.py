"""Web Push 알림 서비스.

pywebpush 기반 Web Push (VAPID) + FCM 호환.
모바일 PWA 의 Service Worker push 구독과 연동.

설정 (.env):
  VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY — 키쌍 (없으면 자동 생성 후 .vapid_keys 에 저장)
  VAPID_SUBJECT=mailto:admin@example.com
  PUSH_ENABLED=true — 스케줄러 활성화 여부

자동 발송: push_scheduler 가 APScheduler 로 매일 오전 7시(KST) 실행.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from ..config import settings

log = logging.getLogger("gospel-api.push")

_VAPID_KEYS: Optional[tuple[str, str]] = None


def _load_vapid_keys() -> tuple[str, str]:
    """VAPID 키쌍 로드. 환경변수 우선, 없으면 파일에서, 그것도 없으면 생성."""
    global _VAPID_KEYS
    if _VAPID_KEYS:
        return _VAPID_KEYS

    pub = settings.vapid_public_key or ""
    priv = settings.vapid_private_key or ""

    if pub and priv:
        _VAPID_KEYS = (pub, priv)
        return _VAPID_KEYS

    key_file = settings.root_dir / ".vapid_keys"
    if key_file.exists():
        try:
            data = json.loads(key_file.read_text(encoding="utf-8"))
            _VAPID_KEYS = (data["public"], data["private"])
            return _VAPID_KEYS
        except Exception as _e:
            log.warning("failed to read VAPID key file, will regenerate: %s", _e)

    # 자동 생성 (cryptography 로 SECP256R1 키쌍 생성)
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        import base64 as _b64

        _k = ec.generate_private_key(ec.SECP256R1())
        priv_pem = _k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("utf-8")
        raw_pub = _k.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        # 브라우저 applicationServerKey 는 base64url(raw 65바이트 비압축 공개키) 여야 함
        pub_b64 = _b64.urlsafe_b64encode(raw_pub).decode("ascii").rstrip("=")
        key_file.write_text(
            json.dumps({"public": pub_b64, "private": priv_pem}), encoding="utf-8"
        )
        log.info("[push] VAPID 키 자동 생성 → %s (이 파일은 git에 커밋하지 마세요)", key_file)
        _VAPID_KEYS = (pub_b64, priv_pem)
        return _VAPID_KEYS
    except Exception as _e:
        log.warning("[push] VAPID 키 생성 실패: %s", _e)
        _VAPID_KEYS = ("", "")
        return _VAPID_KEYS


def get_vapid_public_key() -> str:
    """클라이언트에 전달할 VAPID 공개키."""
    return _load_vapid_keys()[0]


def _get_subscriptions(sub_id: str) -> list[dict]:
    """특정 사용자의 푸시 구독 토큰 목록 조회."""
    from ..db import get_session
    from ..models.orm import Subscriber

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            return []
        consent = dict(sub.consent or {})
        return consent.get("push_tokens", [])


def _get_all_subscribed() -> list[tuple[str, list[dict]]]:
    """푸시 구독 중인 전체 사용자 반환."""
    from ..db import get_session
    from ..models.orm import Subscriber

    out = []
    with get_session() as s:
        subs = s.query(Subscriber).all()
        for sub in subs:
            consent = dict(sub.consent or {})
            tokens = consent.get("push_tokens", [])
            if tokens and consent.get("push_enabled", True):
                out.append((sub.subscriber_id, tokens))
    return out


def send_to_subscriber(
    sub_id: str, title: str, body: str, data: Optional[dict] = None
) -> dict:
    """특정 사용자에게 푸시 발송. 성공/실패 카운트 반환."""
    tokens = _get_subscriptions(sub_id)
    if not tokens:
        return {"ok": False, "sent": 0, "reason": "구독된 토큰이 없습니다."}
    return _send(tokens, title, body, data)


def _send(tokens: list[dict], title: str, body: str, data: Optional[dict]) -> dict:
    """실제 발송. pywebpush 가 없으면 로그만 남기고 스킵 (graceful degradation)."""
    pub, priv = _load_vapid_keys()
    if not pub or not priv:
        log.info("[push] VAPID 키 없음 — 발송 스킵 (제목: %s)", title)
        return {"ok": False, "sent": 0, "reason": "VAPID 키 미설정"}

    subject = settings.vapid_subject or "mailto:admin@example.com"

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("[push] pywebpush 미설치 — 발송 스킵. pip install pywebpush 필요.")
        return {"ok": False, "sent": 0, "reason": "pywebpush 미설치"}

    payload = json.dumps(
        {"title": title, "body": body, "data": data or {}},
        ensure_ascii=False,
    )
    sent = 0
    failed = 0
    skipped = 0
    for entry in tokens:
        # entry 는 {"token": ..., "platform": ...} 형태 (push_subscribe 에서 저장)
        if isinstance(entry, dict):
            token = entry.get("token", "")
            platform = entry.get("platform", "web")
        else:
            token = str(entry)
            platform = "web"

        # platform 기반 분기
        if platform in ("android", "ios") or token.startswith("firebase:"):
            # FCM 네이티브 토큰 — firebase-admin 필요 (현재 미구현)
            skipped += 1
            log.info("[push] FCM 토큰 발송 스킵 (firebase-admin 필요): %s...", str(token)[:20])
            continue

        try:
            # Web Push 구독 — 유효한 JSON 구독 객체여야 함
            if token.startswith("{"):
                subscription_info = json.loads(token)
            else:
                # 단순 endpoint URL만 있는 경우 — keys 가 없으면 webpush 실패
                skipped += 1
                log.info("[push] Web Push 구독 정보 불완전 (keys 없음), 스킵: %s...", token[:20])
                continue

            # 필수 필드 검증
            if not subscription_info.get("endpoint") or not subscription_info.get("keys"):
                skipped += 1
                log.info("[push] 구독 객체에 endpoint/keys 누락, 스킵")
                continue

            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=priv,
                vapid_claims={"sub": subject},
                timeout=10,  # 푸시 서비스는 보통 1초 이내 응답 — 무한 대기 방지
            )
            sent += 1
        except WebPushException as exc:
            failed += 1
            log.warning("[push] 발송 실패: %s", exc)
        except Exception as exc:
            failed += 1
            log.warning("[push] 알 수 없는 발송 오류: %s", exc)

    return {"ok": sent > 0, "sent": sent, "failed": failed, "skipped": skipped}


def broadcast_media_update(items: list[dict]) -> dict:
    """새 찬양/설교 업로드 알림을 구독 중인 전 기기에 브로드캐스트.

    items: [{"id": str, "title": str, "category": "worship"|"sermon"}, ...]
    - 카테고리별 개수 집계 → 한국어 요약 메시지 1건 구성
    - 구독 기기 전체에 Web Push 발송 (pywebpush 미설치/키 없으면 graceful 스킵)
    반환: {"sent", "failed", "skipped", "subscribers"}
    """
    if not items:
        return {"sent": 0, "failed": 0, "skipped": 0, "subscribers": 0, "reason": "보낼 항목 없음"}

    worship = [i for i in items if i.get("category") == "worship"]
    sermon = [i for i in items if i.get("category") == "sermon"]

    parts = []
    if worship:
        parts.append(f"찬양 {len(worship)}곡")
    if sermon:
        parts.append(f"설교 {len(sermon)}편")
    summary = " · ".join(parts) if parts else "새 콘텐츠"

    title = "새로운 찬양·설교가 올라왔어요"
    body = f"{summary}이(가) 추가되었어요"
    data = {
        "type": "new_media",
        "title": title,
        "body": body,
        "items": [
            {"id": i.get("id"), "title": i.get("title"), "category": i.get("category")}
            for i in items
        ],
        # 알림 탭 기본값: 찬양 우선, 없으면 설교
        "tab": "worship" if worship else ("sermon" if sermon else "today"),
    }

    subscribers = _get_all_subscribed()
    total_sent = 0
    total_failed = 0
    total_skipped = 0
    for sub_id, tokens in subscribers:
        res = _send(tokens, title, body, data)
        total_sent += res.get("sent", 0)
        total_failed += res.get("failed", 0)
        total_skipped += res.get("skipped", 0)

    log.info(
        "[push] 미디어 브로드캐스트: 대상 %d기기, sent=%d failed=%d skipped=%d",
        len(subscribers), total_sent, total_failed, total_skipped,
    )
    return {
        "sent": total_sent,
        "failed": total_failed,
        "skipped": total_skipped,
        "subscribers": len(subscribers),
    }
