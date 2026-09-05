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
import copy
import os
import re
import hashlib
import hmac
import time
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..db import get_session
from ..models.orm import Subscriber
from ..models.schemas import SignupReq, LoginReq, AuthResponse
from ..services.audit_service import log as audit_log
from ..services import email_service
from ..services import settings_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _email_verify_enforced() -> bool:
    """이메일 인증이 실제로 로그인을 차단하는가.

    require_email_verification 가 켜져 있고, 실제 SMTP 발송 모드일 때만 차단.
    console 모드(메일 미발송)에서는 차단하지 않아 운영/개발 안전판.
    """
    return settings_service.get_bool(
        "require_email_verification", settings.require_email_verification
    ) and settings.email_mode == "smtp"


def _verify_page_html(ok: bool, title: str, msg: str) -> str:
    color = "#16a34a" if ok else "#dc2626"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
background:#f7f8fa;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center">
<div style="background:#fff;padding:32px 40px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);
max-width:420px;text-align:center">
<h2 style="color:{color};margin:0 0 12px">{title}</h2>
<p style="color:#374151;line-height:1.6">{msg}</p>
<p style="margin-top:24px"><a href="/" style="color:#1a56db;text-decoration:none">← 홈으로 돌아가기</a></p>
</div></body></html>"""

# 토큰 유효기간: 30일 (초 단위)
TOKEN_EXPIRE_SECONDS = 86400 * 30


# ── 간단한 JWT 없이 HMAC 서명 토큰 (의존성 0) ────────────────────────────
# ── 서명 비밀키 ─────────────────────────────────────────────────────────────
# AUTH_SECRET 환경 변수를 우선 사용합니다. 미설정 시 admin_api_key 파생값을 fallback으로
# 사용하지만, 이 경우 admin_api_key 변경 시 모든 사용자 세션이 즉시 무효화됩니다.
import logging as _auth_logging

_auth_log = _auth_logging.getLogger("gospel-api.auth")
if not settings.auth_secret:
    _auth_log.warning(
        "[SECURITY] AUTH_SECRET 환경 변수가 설정되지 않았습니다. "
        ".env 파일에 AUTH_SECRET=<random-64-char-string> 을 추가하세요. "
        "미설정 시 ADMIN_API_KEY 변경 때마다 모든 사용자가 강제 로그아웃됩니다."
    )
if settings.admin_api_key == "change-me":
    _auth_log.warning(
        "[SECURITY] ADMIN_API_KEY 가 기본값 'change-me' 입니다. "
        ".env 에 안전한 키를 설정하세요."
    )


def _load_auth_secret() -> bytes:
    # config.py(settings.auth_secret) 가 AUTH_SECRET 환경변수를 이미 로드함 — 단일 소스.
    if settings.auth_secret:
        return settings.auth_secret.encode()
    secret_file = settings.root_dir / ".auth_secret"
    try:
        if secret_file.exists():
            return secret_file.read_text().strip().encode()
        import secrets as _secrets

        new_secret = _secrets.token_hex(32)
        secret_file.write_text(new_secret)
        _auth_log.info(
            "[SECURITY] .auth_secret 파일 생성됨 — 이 파일을 버전 관리에 커밋하지 마세요."
        )
        return new_secret.encode()
    except OSError:
        # [P0-5] admin_api_key 파생 폴백 제거 — 유추 가능한 서명 키로 토큰 위조가
        # 가능했다. 운영(prod)에서는 기동을 거부(fail-closed), 그 외에는 휘발성
        # 랜덤 시크릿으로 대체(재시작 시 기존 토큰 전체 무효화 — 안전한 실패).
        if (settings.app_env or "").strip().lower() == "prod":
            raise RuntimeError(
                "AUTH_SECRET must be set (or .auth_secret file must be writable) "
                "when APP_ENV=prod. Refusing to start with a weak signing secret."
            )
        _auth_log.critical(
            "[SECURITY] .auth_secret 파일 생성 불가 — 휘발성 랜덤 시크릿 사용. "
            "재시작 시 모든 사용자 토큰이 무효화됩니다. AUTH_SECRET 환경 변수를 설정하세요."
        )
        import secrets as _secrets_ephemeral

        return _secrets_ephemeral.token_hex(32).encode()


_SECRET = _load_auth_secret()


def _make_token(sub_id: str, device_id: str = "web") -> str:
    """세션 토큰 생성. device_id를 포함해 기기별 세션 관리 지원.

    형식: sub_id:ts:device_id:sig (기존 3-part와 하위호환)
    device_id가 같으면 동일 서명 → 같은 기기로 취급.
    """
    ts = int(time.time())
    # device_id 는 영숫자/하이픈/언더스코어만 허용 (구분자 ':' 충돌 방지)
    safe_dev = re.sub(r"[^A-Za-z0-9_-]", "", device_id)[:32] or "web"
    payload = f"{sub_id}:{ts}:{safe_dev}"
    # [P0-14] 서명 128비트(16바이트=hex 32자) — NIST 최소 권장. 기존 16자(64비트) 확장.
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_token(token: str) -> Optional[str]:
    """검증 성공 시 sub_id 반환, 실패 시 None. (3-part 구버전도 호환)"""
    try:
        parts = token.split(":")
        if len(parts) == 3:
            # 구버전: sub_id:ts:sig
            sub_id, ts_str, sig = parts
            ts = int(ts_str)
            if time.time() - ts > TOKEN_EXPIRE_SECONDS:
                return None
            payload = f"{sub_id}:{ts_str}"
            expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
            if not hmac.compare_digest(sig, expected):
                return None
            return sub_id
        if len(parts) == 4:
            # 신버전: sub_id:ts:device_id:sig
            sub_id, ts_str, device_id, sig = parts
            ts = int(ts_str)
            if time.time() - ts > TOKEN_EXPIRE_SECONDS:
                return None
            payload = f"{sub_id}:{ts_str}:{device_id}"
            expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
            if not hmac.compare_digest(sig, expected):
                return None
            return sub_id
        return None
    except Exception:
        return None


def _token_device_id(token: str) -> str:
    """토큰에서 device_id 추출 (4-part). 3-part 구버전은 'web' 반환."""
    parts = token.split(":")
    if len(parts) == 4:
        return parts[2]
    return "web"


def _normalize_device_id(raw: str) -> str:
    """device_id 정규화: 영숫자/하이픈/언더스코어만, 32자 제한."""
    return re.sub(r"[^A-Za-z0-9_-]", "", raw)[:32] or "web"


def _hash_pw_scrypt(password: str, salt: str) -> str:
    """scrypt 기반 패스워드 해싱 (강도 보강)"""
    hashed = hashlib.scrypt(
        password.encode("utf-8"), salt=salt.encode("utf-8"), n=16384, r=8, p=1, dklen=32
    )
    return hashed.hex()


def _hash_pw(password: str) -> str:
    """[DEPRECATED] 구버전 SHA-256 해싱. 신규 가입은 scrypt(_hash_pw_scrypt)를 사용.

    ⚠️ 이 함수는 admin_api_key 를 솔트로 사용합니다. ADMIN_API_KEY 가 변경되면
    이 방식으로 해시된 패스워드를 가진 모든 구 사용자는 로그인이 불가합니다.
    로그인 시 자동으로 scrypt 로 업그레이드되므로, 한 번 로그인한 사용자는 이후 안전합니다.
    """
    _auth_log.warning(
        "[DEPRECATED] _hash_pw (SHA-256) 호출됨. 사용자가 scrypt 로 업그레이드되지 않은 상태입니다."
    )
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


def check_admin(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = None,
) -> None:
    """공통 관리자 권한 및 'change-me' 검사 (상수 시간 토큰 대조 적용).

    Authorization: Bearer 와 X-API-Key 를 모두 수용 — 두 인증 스타일을 통일해
    클라이언트가 보내는 헤더 형식과 무관하게 인증되도록 함.
    """
    # Header(default=None) 이 FastAPI 주입 없이 직접 호출될 때 Header 객체로
    # 남는 경우를 방지 — 항상 str/None 으로 정규화한다.
    authorization = authorization if isinstance(authorization, str) else None
    x_api_key = x_api_key if isinstance(x_api_key, str) else None
    if settings.admin_api_key == "change-me":
        raise HTTPException(
            status_code=503,
            detail="관리자 API 비활성화됨 — .env 파일에 ADMIN_API_KEY 를 설정하고 서버를 재시작하세요.",
        )
    # Authorization: Bearer 또는 X-API-Key 둘 다 수용
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    elif x_api_key:
        provided = x_api_key
    if not provided:
        raise HTTPException(status_code=403, detail="missing admin token")
    if not hmac.compare_digest(provided, settings.admin_api_key):
        raise HTTPException(status_code=403, detail="invalid admin token")


# 자주 쓰이는 약한 비밀번호 차단용 블랙리스트 (소문자 비교)
_COMMON_WEAK_PASSWORDS = {
    "password", "password1", "password12", "passw0rd", "p@ssw0rd",
    "12345678", "123456789", "1234567890", "1234567", "qwerty",
    "qwerty123", "abc123", "abcd1234", "11111111", "00000000",
    "iloveyou", "letmein", "admin123", "welcome1", "gospel",
    "google", "christ", "jesus123", "bible123", "korea123",
    # 6자리 완화로 인해 추가
    "123456", "000000", "111111", "123123", "654321", "abcdef",
}

# 기본 이메일 형식 (공백/연속 @ 금지, 도메인에 점 포함)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_password_strength(password: str) -> tuple[bool, str]:
    """비밀번호 유효성 검사.

    사용자 요구(2026-08-18): '일반적인 영문/숫자 조합만 사용 가능하면 됨'.
    → 최소 6자 + 영문/숫자/일반 문자만 허용하는 단순 규칙으로 완화.
    (특수문자 강제, 영문+숫자 동시 필수, 연속반복 금지 등은 제거)
    """
    if len(password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    if len(password) > 64:
        return False, "비밀번호는 64자 이하여야 합니다."
    # 영문/숫자/일반 기호만 허용 (한글·중국어 등 비ASCII 문자는 차단 — 입력 오류 방지)
    if not re.fullmatch(r"[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':\",./<>?`~ ]+", password):
        return False, "비밀번호는 영문과 숫자로만 입력해 주세요."
    # 자주 쓰이는 약한 비밀번호 차단 (예: 123456, password)
    if password.lower() in _COMMON_WEAK_PASSWORDS:
        return False, "너무 쉬운 비밀번호는 사용할 수 없습니다. 다른 비밀번호를 설정해 주세요."
    return True, ""


# ── Endpoints ─────────────────────────────────────────────────────────────
# 요청/응답 모델은 models/schemas.py 로 이전됨 (SignupReq, LoginReq, AuthResponse)


@router.post("/signup", response_model=AuthResponse)
def signup(req: SignupReq, request: Request):
    """이메일 가입. guest_sub_id 있으면 기존 대화 승계."""
    if not req.email or not req.password:
        raise HTTPException(400, "이메일과 비밀번호를 입력하세요.")
    email = str(req.email).strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "올바른 이메일 형식이 아닙니다.")
    pw_ok, pw_msg = _validate_password_strength(req.password)
    if not pw_ok:
        raise HTTPException(400, pw_msg)

    # ── 이용약관/개인정보 동의 필수 (2026-08-18) ──
    if not req.terms_accepted or not req.privacy_accepted:
        raise HTTPException(400, "이용약관과 개인정보 처리방침에 동의해야 가입할 수 있습니다.")

    # scrypt 솔트 생성 및 해싱
    pw_salt = os.urandom(16).hex()
    pw_hash = _hash_pw_scrypt(req.password, pw_salt)

    with get_session() as s:
        # 이메일 중복 확인 (모든 auth_status 차단 — guest/Google 계정도 포함.
        # DB unique 제약으로도 방어되지만, 명확한 안내 메시지를 위해 앱 레벨에서도 검사)
        existing = s.query(Subscriber).filter(Subscriber.email == email).first()
        if existing and existing.subscriber_id != (req.guest_sub_id or None):
            # ── 차단 계정의 이메일은 재가입 불가 (2026-08-18) ──
            if getattr(existing, "flagged_as_bot", False) or existing.auth_status == "blocked":
                raise HTTPException(403, "이 이메일로는 가입할 수 없습니다. 고객센터에 문의해 주세요.")
            if existing.auth_status == "google":
                raise HTTPException(409, "이미 구글 계정으로 가입된 이메일입니다. 구글 로그인을 이용해 주세요.")
            if existing.auth_status == "guest":
                raise HTTPException(409, "이미 사용 중인 이메일입니다.")
            raise HTTPException(409, "이미 가입된 이메일입니다.")

        if req.guest_sub_id:
            # 기존 guest 업그레이드 — 단, 진짜 guest(anonymous 상태)일 때만
            sub = (
                s.query(Subscriber)
                .filter(Subscriber.subscriber_id == req.guest_sub_id)
                .first()
            )
            # 보안: 이미 가입된 member(auth_status=="email")는 절대 덮어쓰지 않음
            # 차단 계정(flagged_as_bot/blocked)은 게스트 승계도 불가
            if sub and sub.auth_status != "email" and not (
                getattr(sub, "flagged_as_bot", False) or sub.auth_status == "blocked"
            ):
                sub.email = email
                sub.display_name = req.display_name
                sub.auth_status = "email"
                sub.consent = {
                    **(sub.consent or {}),
                    "pw_hash": pw_hash,
                    "pw_salt": pw_salt,
                    "terms_accepted_at": int(time.time()),
                    "privacy_accepted_at": int(time.time()),
                }
                try:
                    s.flush()
                except IntegrityError:
                    raise HTTPException(409, "이미 가입된 이메일입니다.")
                sub_id = sub.subscriber_id
                is_new = False
            else:
                # guest 없거나 이미 member — 새로 생성 (기존 member는 건드리지 않음)
                sub = Subscriber(
                    email=email,
                    display_name=req.display_name,
                    auth_status="email",
                    consent={
                        "pw_hash": pw_hash,
                        "pw_salt": pw_salt,
                        "terms_accepted_at": int(time.time()),
                        "privacy_accepted_at": int(time.time()),
                    },
                )
                s.add(sub)
                s.flush()
                sub_id = sub.subscriber_id
                is_new = True
        else:
            sub = Subscriber(
                email=email,
                display_name=req.display_name,
                auth_status="email",
                consent={
                    "pw_hash": pw_hash,
                    "pw_salt": pw_salt,
                    "terms_accepted_at": int(time.time()),
                    "privacy_accepted_at": int(time.time()),
                },
            )
            s.add(sub)
            try:
                s.flush()
            except IntegrityError:
                raise HTTPException(409, "이미 가입된 이메일입니다.")
            sub_id = sub.subscriber_id
            is_new = True

        # ── 이메일 인증 준비 (2026-07-23) ──
        # [P0-8] SMTP 강제 모드: 즉시 토큰 미발급, 인증 메일 클릭 시 활성화.
        # console 모드(비강제): 인증을 즉시 통과 처리하고 로그인 토큰을 바로 발급한다.
        #   기존에는 메일이 발송되지 않는 console 모드에서도 token="" +
        #   email_verification_required=True 를 반환해 가입 함정이 발생했다.
        _verify_enforced = _email_verify_enforced()
        vtoken = None
        if _verify_enforced:
            sub.email_verified = False
            vtoken = email_service.generate_verify_token(sub_id)
            sub.email_verify_token = vtoken
            sub.email_verify_sent_at = datetime.datetime.utcnow()
        else:
            sub.email_verified = True
            sub.email_verified_at = datetime.datetime.utcnow()

        try:
            audit_log(
                s,
                action="auth.signup",
                entity_type="subscriber",
                entity_id=sub_id,
                who=email,
                note={"source": "email", "is_new": is_new},
            )
        except Exception as _e:
            _auth_log.warning("audit log write failed (auth.signup): %s", _e, exc_info=True)

    if vtoken:
        # ── 이메일 인증 메일 발송 (세션 밖) ──
        verify_url = str(request.base_url).rstrip("/") + "/auth/verify-email?token=" + vtoken
        _lang = getattr(req, "target_lang", None) or "ko"
        email_service.send_verification_email(
            to=email, name=req.display_name or "", verify_url=verify_url, lang=_lang
        )

    return AuthResponse(
        sub_id=sub_id,
        token=_make_token(sub_id) if not _verify_enforced else "",  # 강제 모드에서만 인증 후 발급
        display_name=req.display_name,
        is_new=is_new,
        email=email,
        email_verified=not _verify_enforced,
        email_verification_required=_verify_enforced,
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginReq):
    """이메일 로그인."""
    email = str(req.email).strip().lower()
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.email == email).first()
        if not sub:
            raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")

        # ── 차단(blocked) 계정 차단 (2026-08-18) ──
        # flagged_as_bot=True 또는 auth_status=="blocked" 인 계정은
        # 비밀번호가 맞아도 로그인을 허용하지 않는다 (이메일 열거 방지 위해 401 유지).
        if getattr(sub, "flagged_as_bot", False) or sub.auth_status == "blocked":
            raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")

        consent_dict = sub.consent or {}
        stored_hash = consent_dict.get("pw_hash")
        stored_salt = consent_dict.get("pw_salt")

        # ── 로그인 실패 잠금 (2026-08-18) ──
        # 5회 연속 실패 시 15분간 로그인 차단 (브루트포스 방지).
        # 잠금이 만료되면 카운터 자동 초기화. consent jsonb에 상태 저장.
        now_ts = int(time.time())
        lock_until = consent_dict.get("login_lock_until")
        fails = consent_dict.get("login_fails", 0)
        if lock_until and int(lock_until) > now_ts:
            remain_min = (int(lock_until) - now_ts) // 60
            raise HTTPException(
                status_code=429,
                detail=f"로그인 시도가 너무 많습니다. {remain_min}분 후 다시 시도해 주세요.",
            )

        pw_ok = False
        if stored_salt:
            pw_hash = _hash_pw_scrypt(req.password, stored_salt)
            pw_ok = hmac.compare_digest(stored_hash, pw_hash)
        else:
            # 구버전 SHA-256 호환용 검증
            legacy_hash = hashlib.sha256(
                (req.password + settings.admin_api_key).encode()
            ).hexdigest()
            pw_ok = hmac.compare_digest(stored_hash, legacy_hash)

        if not pw_ok:
            # 실패 카운터 증가.
            # ⚠️ lock_until이 None(잠금된 적 없는 정상 상태)이면 리셋하지 말고
            #    기존 fails를 유지해야 연속 실패가 누적된다.
            #    이전 잠금이 만료된 경우(lock_until <= now_ts)에만 카운터 리셋.
            if lock_until and int(lock_until) <= now_ts:
                fails = 0
            fails += 1
            lock_until_new = None
            if fails >= 5:
                lock_until_new = now_ts + 15 * 60
                sub.consent = {
                    **consent_dict,
                    "login_fails": fails,
                    "login_lock_until": lock_until_new,
                }
                s.add(sub)
                # ⚠️ HTTPException이 with 블록을 벗어나며 rollback 되므로,
                # 반드시 commit을 먼저 수행해야 카운터가 유지된다 (get_session의
                # 정상 종료 commit은 raise로 도달하지 않음).
                s.commit()
                raise HTTPException(
                    status_code=429,
                    detail="로그인 시도가 너무 많습니다. 15분 후 다시 시도해 주세요.",
                )
            sub.consent = {**consent_dict, "login_fails": fails}
            s.add(sub)
            s.commit()
            raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")

            # 로그인 성공 시 scrypt 로 자동 업그레이드
            new_salt = os.urandom(16).hex()
            new_hash = _hash_pw_scrypt(req.password, new_salt)
            sub.consent = {**consent_dict, "pw_hash": new_hash, "pw_salt": new_salt}
            s.add(sub)
            s.flush()

        # ── 이메일 인증 차단 (2026-07-23) ──
        # 실제 SMTP 모드 + require_email_verification 켜짐일 때만 미인증 로그인 차단.
        if _email_verify_enforced() and not sub.email_verified:
            raise HTTPException(
                status_code=403,
                detail="EMAIL_VERIFICATION_REQUIRED",
            )

        # ── 로그인 성공: 실패 카운터/잠금 초기화 (2026-08-18) ──
        if consent_dict.get("login_fails") or consent_dict.get("login_lock_until"):
            sub.consent = {
                **consent_dict,
                "login_fails": 0,
                "login_lock_until": None,
            }
            s.add(sub)
            s.flush()

        sub_id = sub.subscriber_id
        display_name = sub.display_name

        # ── 기기/세션 기록 (2026-08-18) ──
        # consent.active_sessions: [{device_id, device_name, last_seen}] 최대 10개
        # ⚠️ consent_dict 는 요청 시작 시점의 스냅샷이므로, 최신 sub.consent 를
        #    다시 읽어 세션 목록을 안전하게 유지한다 (딥카피로 원본 참조 보호).
        device_id = _normalize_device_id(req.device_id or "web")
        device_name = str(req.device_name or "")[:60]
        now_ts = int(time.time())
        latest_consent = copy.deepcopy(sub.consent or {})
        sessions = latest_consent.get("active_sessions") or []
        # 같은 기기 재로그인 시 last_seen 갱신
        found = False
        for sess in sessions:
            if sess.get("device_id") == device_id:
                sess["last_seen"] = now_ts
                if device_name:
                    sess["device_name"] = device_name
                found = True
                break
        if not found:
            sessions.append({
                "device_id": device_id,
                "device_name": device_name or "Web",
                "last_seen": now_ts,
            })
            sessions = sessions[-10:]  # 최대 10개 유지
        latest_consent["active_sessions"] = sessions
        sub.consent = latest_consent
        s.add(sub)
        s.commit()  # ⚠️ with 블록 정상 종료 시에도 commit 되지만, 명시 commit 으로 보장

    token = _make_token(sub_id, device_id)
    return AuthResponse(
        sub_id=sub_id,
        token=token,
        display_name=display_name,
        is_new=False,
        email=email,
        email_verified=bool(sub.email_verified),
    )


class _ResendReq(BaseModel):
    email: str


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(token: str):
    """이메일 인증 링크 클릭 시 호출. 성공 시 계정 활성화 + HTML 안내."""
    sub_id = email_service.verify_token_signature(token)
    if not sub_id:
        return HTMLResponse(
            _verify_page_html(False, "인증 실패", "링크가 만료되었거나 올바르지 않습니다. "
                              "다시 가입하거나 인증 메일을 재발송해 주세요."),
            status_code=400,
        )
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            return HTMLResponse(
                _verify_page_html(False, "인증 실패", "계정을 찾을 수 없습니다."),
                status_code=400,
            )
        if sub.email_verified:
            return HTMLResponse(
                _verify_page_html(True, "이미 인증됨", "이미 인증된 계정입니다. 로그인해 주세요.")
            )
        sub.email_verified = True
        sub.email_verified_at = datetime.datetime.utcnow()
        sub.email_verify_token = None
        s.flush()
    return HTMLResponse(
        _verify_page_html(
            True, "인증 완료",
            "이메일 인증이 완료되어 계정이 활성화되었습니다. 이제 로그인하실 수 있습니다.",
        )
    )


@router.post("/resend-verification")
def resend_verification(req: _ResendReq, request: Request):
    """인증 메일 재발송 (rate limit 적용)."""
    if not _email_verify_enforced():
        raise HTTPException(400, "EMAIL_VERIFICATION_NOT_REQUIRED")
    email = str(req.email).strip().lower()
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.email == email).first()
        if not sub:
            raise HTTPException(404, "가입되지 않은 이메일입니다.")
        if sub.email_verified:
            raise HTTPException(400, "ALREADY_VERIFIED")
        sent = sub.email_verify_sent_at
        if sent:
            elapsed = (datetime.datetime.utcnow() - sent).total_seconds()
            if elapsed < settings.email_verify_resend_seconds:
                raise HTTPException(429, "RESEND_TOO_SOON")
        vtoken = email_service.generate_verify_token(sub.subscriber_id)
        sub.email_verify_token = vtoken
        sub.email_verify_sent_at = datetime.datetime.utcnow()
        s.flush()
    verify_url = str(request.base_url).rstrip("/") + "/auth/verify-email?token=" + vtoken
    email_service.send_verification_email(
        to=email, name=sub.display_name or "", verify_url=verify_url, lang="ko"
    )
    return {"ok": True, "message": "인증 메일을 재발송했습니다."}


class _ForgotPasswordReq(BaseModel):
    email: str
    lang: str = "ko"


class _ResetPasswordReq(BaseModel):
    token: str
    password: str
    lang: str = "ko"


@router.post("/forgot-password")
def forgot_password(req: _ForgotPasswordReq, request: Request):
    """비밀번호 재설정 링크 발송.

    보안: 계정 존재 여부를 노출하지 않기 위해 가입되지 않은 이메일에도 동일한
    성공 응답을 반환한다(사용자 열거 방지). 실제 발송은 가입된 계정에만 한다.
    """
    email = str(req.email).strip().lower()
    lang = req.lang if req.lang in ("ko", "en", "zh") else "ko"
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.email == email).first()
        if sub:
            reset_token = email_service.generate_verify_token(
                sub.subscriber_id, purpose="password-reset"
            )
            reset_url = (
                str(request.base_url).rstrip("/")
                + "/auth/reset-password?token="
                + reset_token
            )
            email_service.send_reset_email(
                to=email,
                name=sub.display_name or "",
                reset_url=reset_url,
                lang=lang,
            )
    return {"ok": True, "message": "비밀번호 재설정 링크를 이메일로 보냈습니다."}


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(token: str):
    """재설정 링크 클릭 시 안내 페이지. 토큰 유효성은 POST에서 검증.

    (모바일 앱에서는 별도 화면을 사용하므로, 이 페이지는 웹에서 링크를 직접
    열었을 때의 안내용이다.)
    """
    sub_id = email_service.verify_token_signature(token, purpose="password-reset")
    if not sub_id:
        return HTMLResponse(
            _verify_page_html(
                False, "비밀번호 재설정 실패",
                "링크가 만료되었거나 올바르지 않습니다. 다시 요청해 주세요.",
            ),
            status_code=400,
        )
    return HTMLResponse(
        _verify_page_html(
            True, "비밀번호 재설정",
            "링크가 유효합니다. 앱에서 새 비밀번호를 설정해 주세요.",
        )
    )


@router.post("/reset-password")
def reset_password(req: _ResetPasswordReq):
    """토큰 검증 후 새 비밀번호로 변경."""
    sub_id = email_service.verify_token_signature(req.token, purpose="password-reset")
    if not sub_id:
        raise HTTPException(400, "링크가 만료되었거나 올바르지 않습니다. 다시 요청해 주세요.")
    password = str(req.password)
    pw_ok, pw_msg = _validate_password_strength(password)
    if not pw_ok:
        raise HTTPException(400, pw_msg)
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        new_salt = os.urandom(16).hex()
        new_hash = _hash_pw_scrypt(password, new_salt)
        sub.consent = {**(sub.consent or {}), "pw_hash": new_hash, "pw_salt": new_salt}
        s.flush()
        audit_log(
            s,
            action="auth.reset_password",
            entity_type="subscriber",
            entity_id=sub_id,
            who=sub_id,
            note={"ok": True},
        )
    return {"ok": True, "message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요."}


@router.get("/me")
def get_me(authorization: Optional[str] = Header(default=None)):
    """현재 로그인 사용자 프로필."""
    sub_id = get_current_user(authorization)
    from ..services.subscriber_service import get_or_create

    profile = get_or_create(sub_id)
    return profile


# ── 기기/세션 관리 (2026-08-18) ───────────────────────────────────────────────
@router.get("/sessions")
def list_sessions(authorization: Optional[str] = Header(default=None)):
    """로그인된 기기 목록 (현재 기기 표시 포함)."""
    sub_id = get_current_user(authorization)
    current_dev = _token_device_id(authorization or "")
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        sessions = (sub.consent or {}).get("active_sessions") or []
    return {
        "sessions": sessions,
        "current_device_id": current_dev,
    }


@router.delete("/sessions/{device_id}")
def revoke_session(device_id: str, authorization: Optional[str] = Header(default=None)):
    """특정 기기 원격 로그아웃 (해당 기기 토큰 무효화).

    구현: consent.active_sessions 에서 해당 기기 제거.
    토큰은 sub_id:ts:device_id:sig 서명이라, 같은 device_id 재로그인 전까지
    해당 기기의 기존 토큰은 서명 불일치로 자동 무효화된다.
    """
    sub_id = get_current_user(authorization)
    dev = _normalize_device_id(device_id)
    if not dev:
        raise HTTPException(400, "유효하지 않은 기기입니다.")
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        consent = sub.consent or {}
        sessions = consent.get("active_sessions") or []
        before = len(sessions)
        sessions = [x for x in sessions if x.get("device_id") != dev]
        if len(sessions) == before:
            raise HTTPException(404, "해당 기기를 찾을 수 없습니다.")
        sub.consent = {**consent, "active_sessions": sessions}
        s.add(sub)
        s.commit()
        audit_log(
            s,
            action="auth.revoke_session",
            entity_type="subscriber",
            entity_id=sub_id,
            who=sub_id,
            note={"device_id": dev},
        )
    return {"ok": True, "message": "해당 기기에서 로그아웃되었습니다."}


# ── 비밀번호 변경 (로그인 상태, 2026-08-18) ───────────────────────────────────
class _ChangePasswordReq(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(req: _ChangePasswordReq, authorization: Optional[str] = Header(default=None)):
    """로그인 상태에서 비밀번호 변경.

    현재 비밀번호 검증 후 새 비밀번호로 교체. 변경 후 모든 기기에서 재로그인 필요
    (새 솔트로 해시 교체 → 기존 토큰은 유지되지만, 보안상 타 기기 로그아웃은
    원격 로그아웃 기능으로 별도 처리).
    """
    sub_id = get_current_user(authorization)
    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if not sub:
            raise HTTPException(404, "계정을 찾을 수 없습니다.")
        consent = sub.consent or {}
        stored_hash = consent.get("pw_hash")
        stored_salt = consent.get("pw_salt")
        if stored_salt:
            cur_hash = _hash_pw_scrypt(req.current_password, stored_salt)
            if not hmac.compare_digest(stored_hash, cur_hash):
                raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다.")
        else:
            legacy_hash = hashlib.sha256(
                (req.current_password + settings.admin_api_key).encode()
            ).hexdigest()
            if not hmac.compare_digest(stored_hash, legacy_hash):
                raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다.")

        pw_ok, pw_msg = _validate_password_strength(req.new_password)
        if not pw_ok:
            raise HTTPException(400, pw_msg)
        new_salt = os.urandom(16).hex()
        new_hash = _hash_pw_scrypt(req.new_password, new_salt)
        sub.consent = {**consent, "pw_hash": new_hash, "pw_salt": new_salt}
        s.add(sub)
        s.commit()
        audit_log(
            s,
            action="auth.change_password",
            entity_type="subscriber",
            entity_id=sub_id,
            who=sub_id,
            note={"ok": True},
        )
    return {"ok": True, "message": "비밀번호가 변경되었습니다."}


# ── Google OAuth ──────────────────────────────────────────────────────────────

class GoogleAuthReq(BaseModel):
    """Google ID 토큰 (클라이언트가 Google에서 받아 전송)."""
    id_token: str
    guest_sub_id: Optional[str] = None


@router.post("/google", response_model=AuthResponse)
async def auth_google(req: GoogleAuthReq):
    """Google ID 토큰 검증 → 회원가입/로그인.

    클라이언트가 Google Identity Services로 받은 ID 토큰을 전송하면
    백엔드에서 Google tokeninfo API로 검증 후 Subscriber 생성/조회.
    """
    if not settings.google_client_id:
        raise HTTPException(503, "Google 로그인이 설정되지 않았습니다. GOOGLE_CLIENT_ID를 .env에 추가하세요.")

    # Google tokeninfo API로 토큰 검증
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": req.id_token},
            )
        if resp.status_code != 200:
            raise HTTPException(401, "Google 토큰 검증 실패")
        token_data = resp.json()
    except _httpx.HTTPError as exc:
        raise HTTPException(502, f"Google 검증 서버 연결 실패: {exc}")

    # aud(대상) 검증 — GOOGLE_CLIENT_ID 에 콤마로 여러 클라이언트 ID 허용(웹+PWA+안드로이드)
    _allowed_ids = {c.strip() for c in settings.google_client_id.split(",") if c.strip()}
    if token_data.get("aud") not in _allowed_ids:
        raise HTTPException(401, "토큰 대상(aud)이 일치하지 않습니다.")

    # iss(발급자) 검증 — Google 이외 발급자의 토큰 거부 (방어적 심층)
    _iss = token_data.get("iss")
    if _iss not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(401, "토큰 발급자(iss)가 유효하지 않습니다.")

    email = (token_data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Google 계정에서 이메일을 가져올 수 없습니다.")

    name = token_data.get("name") or email.split("@")[0]
    # R-6: Google 이 boolean True 를 반환하는 경우도 수용 (문자열 "true" 비교 실패 방지)
    ev = token_data.get("email_verified")
    email_verified = ev is True or str(ev).lower() == "true"
    if not email_verified:
        raise HTTPException(403, "이메일 인증이 완료되지 않은 Google 계정입니다.")

    with get_session() as s:
        sub = s.query(Subscriber).filter(Subscriber.email == email).first()
        is_new = False

        if sub:
            # ── 차단 계정은 Google 로그인도 불가 (2026-08-18) ──
            if getattr(sub, "flagged_as_bot", False) or sub.auth_status == "blocked":
                raise HTTPException(403, "이 계정은 사용할 수 없습니다. 고객센터에 문의해 주세요.")
            # 기존 회원 — auth_status 업그레이드 (이미 google이면 유지)
            if sub.auth_status not in ("email", "google"):
                sub.auth_status = "google"
            if not sub.display_name:
                sub.display_name = name
            sub.email_verified = True  # Google이 이메일 인증함
            sub_id = sub.subscriber_id
        else:
            # 신규 Google 회원 또는 guest 승계
            is_new = True
            if req.guest_sub_id:
                guest = s.query(Subscriber).filter(
                    Subscriber.subscriber_id == req.guest_sub_id
                ).first()
                if guest and guest.auth_status not in ("email", "google"):
                    guest.email = email
                    guest.display_name = name
                    guest.auth_status = "google"
                    guest.email_verified = True
                    sub_id = guest.subscriber_id
                    is_new = False  # guest 승계는 신규 가입이 아님
                else:
                    sub = Subscriber(email=email, display_name=name, auth_status="google", email_verified=True)
                    s.add(sub); s.flush()
                    sub_id = sub.subscriber_id
            else:
                # ⚠️ 신규 Google 가입자는 이메일이 Google 에 의해 인증된 것으로 간주하므로
                # email_verified=True 로 생성해야 한다. 누락 시 enforce 모드에서 영구 로그인 차단.
                sub = Subscriber(
                    email=email, display_name=name, auth_status="google", email_verified=True
                )
                s.add(sub); s.flush()
                sub_id = sub.subscriber_id

        try:
            audit_log(s, action="auth.google", entity_type="subscriber",
                      entity_id=sub_id, who=email, note={"verified": email_verified, "is_new": is_new})
        except Exception as _e:
            _auth_log.warning("audit log write failed (auth.google): %s", _e, exc_info=True)

    token = _make_token(sub_id)
    return AuthResponse(sub_id=sub_id, token=token, display_name=name, is_new=is_new, email=email, email_verified=True)


@router.get("/google/config")
async def auth_google_config():
    """프론트엔드(웹/모바일)가 Google Client ID를 가져오는 공개 엔드포인트.

    인증 불필요. .env의 GOOGLE_CLIENT_ID가 비어 있으면 enabled=false.
    모바일은 이 값으로 Google Identity Services를 초기화한다.
    """
    return {
        "enabled": bool(settings.google_client_id),
        "client_id": settings.google_client_id or "",
    }
