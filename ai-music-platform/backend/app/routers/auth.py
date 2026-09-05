"""鉴权路由：注册 / 登录 / 当前用户依赖。"""
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User, UserLink
from app.ratelimit import rate_limit_login
from app.entitlements import resolve_limits, VALID_TIERS
from app.schemas import (
    FlowExchangeReq,
    FlowExchangeResp,
    FlowLinkReq,
    LoginReq,
    MeResp,
    RegisterReq,
    TokenResp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


# [D37] 공개된 기본 서명 키 — 이 값으로 서명하면 **누구나 위조 토큰을 만들 수 있다**.
# config.py:11 의 기본값 "change-me-please" 가 그대로 운영에 쓰이는 것을 막는다.
# docker-compose.yml:45 가 `JWT_SECRET: ${JWT_SECRET:-change-me-please}` 로
# **기본값을 능동적으로 주입** 하고 있어, 환경변수 미설정 시 그대로 확정된다.
# 같은 파일의 `require_admin`(admin_token 미설정 → 503) 과 동일한 fail-closed 패턴을 따른다.
_INSECURE_JWT_SECRETS = frozenset(
    {"", "change-me-please", "changeme", "change-me", "secret", "test"}
)
_JWT_MISCONFIG_DETAIL = (
    "JWT 서명 키(jwt_secret) 가 설정되지 않았거나 공개된 기본값입니다. "
    "JWT_SECRET 환경변수에 충분한 엔트로피의 값을 설정하세요."
)


def _assert_jwt_secret_configured() -> None:
    """서명 키가 공개 기본값이면 503(fail-closed).

    ⚠ **서명(sign) 과 검증(verify) 양쪽에서 모두 호출** 해야 한다.
    서명만 막으면 공격자가 `change-me-please` 로 직접 위조한 토큰이
    그대로 검증을 통과한다 — 즉 편측 가드는 무의미하다.
    """
    if settings.jwt_secret.strip().lower() in _INSECURE_JWT_SECRETS:
        raise HTTPException(status_code=503, detail=_JWT_MISCONFIG_DETAIL)


def create_token(
    user_id: int,
    scope: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    """签发 JWT。默认全权限(登录/注册返回的普通令牌)。

    scope 给定时写入 scope 声明(最小权限令牌, 如 sync:flow)。
    expires_minutes 给定时覆盖默认寿命(用于短期交换令牌)。
    """
    exp_min = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    exp = datetime.now(timezone.utc) + timedelta(minutes=exp_min)
    payload: dict = {"sub": str(user_id), "exp": exp}
    if scope:
        payload["scope"] = scope
    # [D37] 서명 전 fail-closed — 공개 기본값으로는 토큰을 발급하지 않는다.
    _assert_jwt_secret_configured()
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    cred_exc = HTTPException(401, "无效或过期的凭证", headers={"WWW-Authenticate": "Bearer"})
    # [D37] 검증 전 fail-closed — 공개 기본값으로 위조된 토큰을 거부한다.
    _assert_jwt_secret_configured()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        uid = int(payload.get("sub"))
        # 最小权限: scope 한정 토큰(sync:flow 등)은 전권한 엔드포인트 접근 불가.
        # scope 클레임이 있으면 get_current_user_scoped 전용으로 격리.
        if "scope" in payload:
            raise cred_exc
    except (JWTError, ValueError, TypeError):
        raise cred_exc
    user = db.get(User, uid)
    if not user:
        raise cred_exc
    return user


def get_current_user_scoped(required_scope: str):
    """scope 限定 JWT 校验依赖工厂。

    sync:flow 等最小权限令牌만 특정 엔드포인트 접근 허용.
    scope 클레임 누락/불일치 시 401(fail-closed) —— 普通全权限令牌도 접근 불가.
    🔴A 闭合: FLOW APP 不再复用"同一 JWT", 而是持有音乐发放的 scope 限定交换令牌.
    """

    def _dep(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
        cred_exc = HTTPException(401, "无效或过期的凭证", headers={"WWW-Authenticate": "Bearer"})
        # [D37] scope 한정 토큰 검증 경로도 동일하게 fail-closed.
        _assert_jwt_secret_configured()
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            uid = int(payload.get("sub"))
            if payload.get("scope") != required_scope:
                raise cred_exc
        except (JWTError, ValueError, TypeError):
            raise cred_exc
        user = db.get(User, uid)
        if not user:
            raise cred_exc
        return user

    return _dep


# 密码最小长度（防弱口令；业务规则，不依赖外部配置）
PASSWORD_MIN_LENGTH = 8


@router.post("/register", response_model=TokenResp)
def register(req: RegisterReq, db: Session = Depends(get_db)):
    if len(req.password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"密码至少 {PASSWORD_MIN_LENGTH} 位")
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="邮箱已注册")
    user = User(email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResp(access_token=create_token(user.id))


@router.post("/login", response_model=TokenResp)
def login(req: LoginReq, request: Request, db: Session = Depends(get_db)):
    rate_limit_login(request.client.host if request.client else "unknown")
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return TokenResp(access_token=create_token(user.id))


def _resolve_admin_role(token: str | None) -> str | None:
    """返回令牌角色：super(主管理员) / viewer(只读) / None(无效)。"""
    if not token:
        return None
    if settings.admin_token and hmac.compare_digest(token, settings.admin_token):
        return "super"
    if settings.admin_viewer_token and hmac.compare_digest(token, settings.admin_viewer_token):
        return "viewer"
    return None


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """管理后台鉴权：校验 X-Admin-Token。

    - admin_token 未配置 → 503（功能未启用），而非 500（避免暗示服务端 bug）。
    - 接受 super(admin_token) 与 viewer(admin_viewer_token) 两种令牌；
      viewer 仅可访问只读接口，变更类接口由 main.admin_rbac_audit 中间件返回 403。
    - 令牌用恒定时间比较（hmac.compare_digest），防时序侧信道。
    """
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="管理后台未启用（admin_token 未配置）")
    if _resolve_admin_role(x_admin_token) is None:
        raise HTTPException(status_code=401, detail="无效的管理密钥")


@router.get("/me", response_model=MeResp)
def me(user: User = Depends(get_current_user)) -> MeResp:
    """返回当前登录用户（id + email），供前端展示用户名。"""
    return MeResp(id=user.id, email=user.email)


class SubscribeReq(BaseModel):
    tier_key: str


@router.post("/subscribe")
def subscribe(
    req: SubscribeReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[GAP-004 mock] 실제 PG 결제 미연동 — 결제 완료를 시뮬레이션해 티어만 전환.

    실 PG(Stripe/Kakao Pay/Naver Pay 등) 연동 시 이 엔드포인트는
    웹훅/결제완료 검증 핸들러로 교체되며, 그때는 결제 영수증 검증 후에만
    `user.tier_key` 를 설정한다. 현재는 권한 게이팅 로직을 E2E 로 검증하기 위한
    테스트/데모용이다.
    """
    # ⚠ live 모드에서는 410 으로 폐기 — 결제 우회(무료 직접 승급) 백도어 방지.
    #   실결제는 /api/billing/checkout → webhook/confirm 흐름을 따른다.
    if settings.billing_mode == "live":
        raise HTTPException(
            status_code=410,
            detail="직접 구독은 비활성화되었습니다. 결제 flow(/api/billing/checkout) 를 이용하세요.",
        )
    if req.tier_key not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="unknown tier_key")
    user.tier_key = req.tier_key
    db.commit()
    db.refresh(user)
    return {"tier_key": user.tier_key, "limits": resolve_limits(db, user.tier_key)}


@router.post("/flow-link")
def flow_link(
    req: FlowLinkReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户授权绑定 FLOW subscriber_id ↔ 本音乐账号(user_id)。

    幂等 upsert: 同一 subscriber_id 는 항상 동일 music_user_id 로 매핑.
    호출 전제: APP 이 음악 JWT(본 의존성 검증) 와 FLOW subscriber_id 를 동시 보유.
    실제 sync 호출은 flow-exchange 로 발급된 scope 한정 토큰을 사용.
    """
    link = db.query(UserLink).filter_by(flow_subscriber_id=req.subscriber_id).first()
    if link:
        link.music_user_id = user.id
    else:
        link = UserLink(flow_subscriber_id=req.subscriber_id, music_user_id=user.id)
        db.add(link)
    db.commit()
    return {"status": "linked", "subscriber_id": req.subscriber_id, "music_user_id": user.id}


@router.post("/flow-exchange", response_model=FlowExchangeResp)
def flow_exchange(
    req: FlowExchangeReq,
    x_flow_internal_token: str | None = Header(default=None, alias="X-Flow-Internal-Token"),
    db: Session = Depends(get_db),
):
    """FLOW 后端 server-to-server: subscriber_id → scope 한정(sync:flow) JWT。

    - 내부 FLOW_INTERNAL_TOKEN 으로 보호(상수시간 비교, 시퀀스 사이드채널 방지).
    - 미설정 시 503(기능 미활성).
    - 매핑(user_link) 없으면 404(바인딩 선행 필요).
    - 발급되는 JWT 는 sync 전용 —— 음악 생성/관리/결제 권한 0(최소 권한).
    """
    if not settings.flow_internal_token:
        raise HTTPException(status_code=503, detail="FLOW 令牌交换未启用（flow_internal_token 未配置）")
    if not x_flow_internal_token or not hmac.compare_digest(x_flow_internal_token, settings.flow_internal_token):
        raise HTTPException(status_code=401, detail="无效的内部密钥")
    link = db.query(UserLink).filter_by(flow_subscriber_id=req.subscriber_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="未找到 FLOW 账号绑定，请先绑定")
    token = create_token(
        link.music_user_id,
        scope="sync:flow",
        expires_minutes=settings.flow_exchange_token_expire_minutes,
    )
    return FlowExchangeResp(access_token=token)
