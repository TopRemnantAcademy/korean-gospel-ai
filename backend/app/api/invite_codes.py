"""
API — 초대 코드 엔드포인트
- POST /api/invite-codes/validate — 코드 검증
- POST /api/invite-codes/generate — 코드 생성 (Admin)
- GET /api/invite-codes — 모든 코드 조회 (Admin)
- GET /api/invite-codes/{code}/stats — 코드 통계
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from ..db import get_db
from ..services.invite_code_service import InviteCodeService

router = APIRouter(prefix="/api/invite-codes", tags=["invite-codes"])


# ----- 스키마 -----
class InviteCodeValidateRequest(BaseModel):
    code: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class InviteCodeValidateResponse(BaseModel):
    valid: bool
    reason: str
    code_info: Optional[dict] = None


class InviteCodeGenerateRequest(BaseModel):
    invited_by: Optional[str] = "admin"
    max_uses: int = 1
    expires_hours: Optional[int] = 24 * 7
    grants_tokens: int = 20000
    note: Optional[str] = None


class InviteCodeGenerateResponse(BaseModel):
    code: str
    expires_at: Optional[str] = None
    grants_tokens: int


# ----- 엔드포인트 -----

@router.post("/validate", response_model=InviteCodeValidateResponse)
async def validate_code(
    req: InviteCodeValidateRequest,
    db: Session = Depends(get_db),
) -> InviteCodeValidateResponse:
    """초대 코드 검증"""
    valid, reason, invite_code = InviteCodeService.validate_code(
        db,
        code=req.code,
        ip_address=req.ip_address,
        user_agent=req.user_agent,
    )
    
    code_info = None
    if valid and invite_code:
        code_info = {
            "code": invite_code.code,
            "grants_tokens": invite_code.grants_tokens,
            "expires_at": invite_code.expires_at.isoformat() if invite_code.expires_at else None,
        }
    
    return InviteCodeValidateResponse(
        valid=valid,
        reason=reason,
        code_info=code_info,
    )


@router.post("/generate", response_model=InviteCodeGenerateResponse)
async def generate_code(
    req: InviteCodeGenerateRequest,
    admin_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> InviteCodeGenerateResponse:
    """초대 코드 생성 (Admin 전용)"""
    # 간단한 인증 (실제는 JWT 사용)
    expected_key = "local-admin-key"  # .env 에서 로드
    
    if admin_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    code = InviteCodeService.generate_code(
        db,
        invited_by=req.invited_by,
        max_uses=req.max_uses,
        expires_hours=req.expires_hours,
        grants_tokens=req.grants_tokens,
        note=req.note,
    )
    
    # 만료 시간 계산
    expires_at = None
    if req.expires_hours:
        from datetime import timedelta
        expires_at = (datetime.utcnow() + timedelta(hours=req.expires_hours)).isoformat()
    
    return InviteCodeGenerateResponse(
        code=code,
        expires_at=expires_at,
        grants_tokens=req.grants_tokens,
    )


@router.get("/")
async def list_codes(
    admin_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """모든 초대 코드 조회 (Admin 전용)"""
    expected_key = "local-admin-key"
    
    if admin_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    codes = InviteCodeService.get_all_codes(db, active_only=False)
    
    return {
        "total": len(codes),
        "codes": codes,
    }


@router.get("/{code}/stats")
async def get_code_stats(
    code: str,
    admin_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """코드 통계"""
    expected_key = "local-admin-key"
    
    if admin_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    stats = InviteCodeService.get_code_stats(db, code)
    
    if not stats:
        raise HTTPException(status_code=404, detail="Code not found")
    
    return stats


@router.get("/{code}/usage-history")
async def get_usage_history(
    code: str,
    limit: int = 50,
    admin_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """코드 사용 기록"""
    expected_key = "local-admin-key"
    
    if admin_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    history = InviteCodeService.get_usage_history(db, code=code, limit=limit)
    
    return {
        "code": code,
        "total": len(history),
        "history": history,
    }


@router.post("/{code}/deactivate")
async def deactivate_code(
    code: str,
    admin_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """코드 비활성화"""
    expected_key = "local-admin-key"
    
    if admin_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    success = InviteCodeService.deactivate_code(db, code)
    
    if not success:
        raise HTTPException(status_code=404, detail="Code not found")
    
    return {"success": True, "code": code}
