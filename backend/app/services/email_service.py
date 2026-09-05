"""이메일 발송 서비스 (2026-07-23).

- email_mode='smtp' → 실제 SMTP 발송 (TLS).
- email_mode='console' → 발송 생략 + 확인 링크를 로그에 출력 (dev/test, 메일 서버 불필요).
- 인증 토큰은 HMAC 서명 (stateless, 위변조 불가). 만료는 토큰에 포함.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import smtplib
import time
from email.message import EmailMessage
from typing import Optional

from ..config import settings as _cfg

logger = logging.getLogger("gospel-api.email")

_TOKEN_TTL_SECONDS = _cfg.email_verify_token_ttl_hours * 3600
_PURPOSE = b"email-verify"
_PURPOSE_RESET = b"password-reset"


def _secret() -> bytes:
    return (_cfg.auth_secret or "dev-insecure-verify-secret-change-me").encode("utf-8")


def generate_verify_token(sub_id: str, purpose: str = "email-verify") -> str:
    """sub_id + 만료시각을 HMAC 서명한 토큰 생성.

    purpose: 'email-verify'(기본) | 'password-reset' — 용도별 서명 분리로
    인증 토큰과 비밀번호 재설정 토큰의 상호 재사용을 차단.
    """
    purpose_bytes = _PURPOSE_RESET if purpose == "password-reset" else _PURPOSE
    expiry = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{sub_id}|{expiry}".encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii")
    sig = hmac.new(_secret(), body.encode("ascii") + purpose_bytes, hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token_signature(token: str, purpose: str = "email-verify") -> Optional[str]:
    """토큰 검증 → 유효하면 sub_id, 만료/위변조 시 None."""
    try:
        body, sig = token.split(".", 1)
        purpose_bytes = _PURPOSE_RESET if purpose == "password-reset" else _PURPOSE
        expected = hmac.new(_secret(), body.encode("ascii") + purpose_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        payload = base64.urlsafe_b64decode(body.encode("ascii")).decode("utf-8")
        sub_id, expiry = payload.split("|", 1)
        if int(expiry) < int(time.time()):
            return None
        return sub_id
    except Exception:
        return None


# ---- 다국어 템플릿 ----
_TPL = {
    "ko": {
        "subject": "복음 AI — 이메일 인증을 완료해 주세요",
        "title": "이메일 인증",
        "greeting": "안녕하세요{name}님,",
        "body": "가입을 완료하려면 아래 버튼을 눌러 이메일을 인증해 주세요. "
                "버튼을 누르면 계정이 활성화됩니다.",
        "button": "이메일 인증하고 활성화",
        "expire": "이 링크는 {hours}시간 동안 유효합니다.",
        "footer": "본 메일은 발신 전용입니다.",
    },
    "zh": {
        "subject": "福音 AI — 请完成邮箱验证",
        "title": "邮箱验证",
        "greeting": "你好{name}，",
        "body": "请点击下面的按钮验证邮箱以完成注册。点击后账户将被激活。",
        "button": "验证邮箱并激活",
        "expire": "此链接在 {hours} 小时内有效。",
        "footer": "本邮件为系统自动发送，请勿回复。",
    },
    "en": {
        "subject": "Gospel AI — Please verify your email",
        "title": "Email Verification",
        "greeting": "Hi{name},",
        "body": "Click the button below to verify your email and finish signing up. "
                "Your account will be activated.",
        "button": "Verify email & activate",
        "expire": "This link is valid for {hours} hours.",
        "footer": "This is an automated message.",
    },
}


def build_verification_email(name: str, verify_url: str, lang: str = "ko"):
    t = _TPL.get(lang, _TPL["ko"])
    name_part = f" {name}" if name else ""
    greeting = t["greeting"].format(name=name_part)
    expire = t["expire"].format(hours=_cfg.email_verify_token_ttl_hours)
    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto">
  <h2 style="color:#1a56db">{t['title']}</h2>
  <p>{greeting}</p>
  <p>{t['body']}</p>
  <p style="margin:24px 0">
    <a href="{verify_url}" style="background:#1a56db;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block">{t['button']}</a>
  </p>
  <p style="color:#666;font-size:13px">{expire}</p>
  <p style="color:#999;font-size:12px;border-top:1px solid #eee;padding-top:8px">{t['footer']}</p>
</div>"""
    text = f"{greeting}\n\n{t['body']}\n\n{verify_url}\n\n{expire}\n\n{t['footer']}"
    return t["subject"], html, text


def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """발송. console 모드면 로그만. 성공 여부 반환."""
    if _cfg.email_mode != "smtp" or not _cfg.smtp_host:
        logger.info(
            "[email:console] to=%s subject=%s\n--- verify link ---\n%s\n---",
            to, subject, text.splitlines()[-3] if "http" in text else text,
        )
        return True
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{_cfg.mail_from_name} <{_cfg.mail_from}>"
        msg["To"] = to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(_cfg.smtp_host, _cfg.smtp_port, timeout=15) as s:
            if _cfg.smtp_tls:
                s.starttls()
            if _cfg.smtp_user:
                s.login(_cfg.smtp_user, _cfg.smtp_pass or "")
            s.send_message(msg)
        logger.info("[email:smtp] sent to=%s", to)
        return True
    except Exception as e:
        logger.error("[email:smtp] failed to=%s err=%s", to, e)
        return False


def send_verification_email(to: str, name: str, verify_url: str, lang: str = "ko") -> bool:
    subject, html, text = build_verification_email(name, verify_url, lang)
    return send_email(to, subject, html, text)


# ---- 비밀번호 재설정 이메일 템플릿 (2026-08-18) ----
_RESET_TPL = {
    "ko": {
        "subject": "복음 AI — 비밀번호 재설정",
        "title": "비밀번호 재설정",
        "greeting": "안녕하세요{name}님,",
        "body": "비밀번호 재설정 요청을 받았습니다. 아래 버튼을 눌러 새 비밀번호를 설정해 주세요. "
                "본인이 요청하지 않았다면 이 메일을 무시해도 됩니다.",
        "button": "비밀번호 재설정",
        "expire": "이 링크는 {hours}시간 동안 유효합니다.",
        "footer": "본 메일은 발신 전용입니다.",
    },
    "zh": {
        "subject": "福音 AI — 重置密码",
        "title": "重置密码",
        "greeting": "你好{name}，",
        "body": "我们收到了重置密码的请求。请点击下面的按钮设置新密码。"
                "如果您没有请求重置，请忽略此邮件。",
        "button": "重置密码",
        "expire": "此链接在 {hours} 小时内有效。",
        "footer": "本邮件为系统自动发送，请勿回复。",
    },
    "en": {
        "subject": "Gospel AI — Reset your password",
        "title": "Reset Password",
        "greeting": "Hi{name},",
        "body": "We received a request to reset your password. Click the button below to set a new one. "
                "If you didn't request this, you can safely ignore this email.",
        "button": "Reset password",
        "expire": "This link is valid for {hours} hours.",
        "footer": "This is an automated message.",
    },
}


def build_reset_email(name: str, reset_url: str, lang: str = "ko"):
    t = _RESET_TPL.get(lang, _RESET_TPL["ko"])
    name_part = f" {name}" if name else ""
    greeting = t["greeting"].format(name=name_part)
    expire = t["expire"].format(hours=_cfg.email_verify_token_ttl_hours)
    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto">
  <h2 style="color:#1a56db">{t['title']}</h2>
  <p>{greeting}</p>
  <p>{t['body']}</p>
  <p style="margin:24px 0">
    <a href="{reset_url}" style="background:#1a56db;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block">{t['button']}</a>
  </p>
  <p style="color:#666;font-size:13px">{expire}</p>
  <p style="color:#999;font-size:12px;border-top:1px solid #eee;padding-top:8px">{t['footer']}</p>
</div>"""
    text = f"{greeting}\n\n{t['body']}\n\n{reset_url}\n\n{expire}\n\n{t['footer']}"
    return t["subject"], html, text


def send_reset_email(to: str, name: str, reset_url: str, lang: str = "ko") -> bool:
    subject, html, text = build_reset_email(name, reset_url, lang)
    return send_email(to, subject, html, text)
