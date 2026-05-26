"""
초대 코드 서비스 — ORM 기반
- 초대 코드 생성/관리
- 코드 검증
- Subscriber 에 토큰 부여
- 사용 기록 추적
"""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from ..models.orm import InviteCode, InviteCodeUsage


class InviteCodeService:
    """초대 코드 비즈니스 로직"""
    
    @staticmethod
    def generate_code(
        db: Session,
        invited_by: str = "admin",
        max_uses: int = 1,
        expires_hours: Optional[int] = 24 * 7,
        grants_tokens: int = 20000,
        note: Optional[str] = None,
    ) -> str:
        """초대 코드 생성
        
        Returns:
            생성된 코드 (BETA-GOSPEL-XXXXXX 형태)
        """
        import uuid
        import string
        import random
        
        # 코드 생성: BETA-GOSPEL-ABC123 (6자 영숫자)
        code_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code = f"BETA-GOSPEL-{code_suffix}"
        
        expires_at = None
        if expires_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
        
        invite_code = InviteCode(
            code=code,
            invited_by=invited_by,
            max_uses=max_uses,
            used_count=0,
            expires_at=expires_at,
            grants_tokens=grants_tokens,
            note=note,
            active=True,
            created_at=datetime.utcnow(),
        )
        
        db.add(invite_code)
        db.commit()
        db.refresh(invite_code)
        
        return code
    
    @staticmethod
    def validate_code(
        db: Session,
        code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[bool, str, Optional[InviteCode]]:
        """초대 코드 검증
        
        Returns:
            (valid, reason, invite_code_obj)
        """
        # 코드 조회
        stmt = select(InviteCode).where(InviteCode.code == code)
        invite_code = db.execute(stmt).scalars().first()
        
        if not invite_code:
            return False, "존재하지 않는 코드입니다.", None
        
        # 활성화 여부
        if not invite_code.active:
            return False, "비활성화된 코드입니다.", None
        
        # 만료 여부
        if invite_code.expires_at and datetime.utcnow() > invite_code.expires_at:
            return False, "만료된 코드입니다.", None
        
        # 사용 횟수 초과
        if invite_code.max_uses > 0 and invite_code.used_count >= invite_code.max_uses:
            return False, f"사용 횟수 초과입니다. (최대 {invite_code.max_uses}회)", None
        
        # 사용 횟수 증가
        invite_code.used_count += 1
        
        # 사용 기록 저장
        usage = InviteCodeUsage(
            code=code,
            ip_address=ip_address,
            user_agent=user_agent,
            used_at=datetime.utcnow(),
        )
        db.add(usage)
        db.commit()
        db.refresh(invite_code)
        
        return True, "OK", invite_code
    
    @staticmethod
    def link_subscriber(
        db: Session,
        code: str,
        subscriber_id: str,
    ) -> bool:
        """초대 코드와 Subscriber 연결 (가입 완료 후)
        
        - 마지막 InviteCodeUsage 에 subscriber_id 할당
        - Subscriber 에 토큰 부여
        """
        # 마지막 usage 찾기
        stmt = select(InviteCodeUsage).where(
            InviteCodeUsage.code == code
        ).order_by(InviteCodeUsage.used_at.desc())
        
        usage = db.execute(stmt).scalars().first()
        
        if not usage:
            return False
        
        # subscriber_id 할당
        usage.subscriber_id = subscriber_id
        
        # InviteCode 에서 tokens 읽기
        stmt = select(InviteCode).where(InviteCode.code == code)
        invite_code = db.execute(stmt).scalars().first()
        
        if invite_code:
            # Subscriber 에 tokens_bonus 부여 (별도 로직)
            # subscriber_service.add_tokens_bonus(db, subscriber_id, invite_code.grants_tokens)
            pass
        
        db.commit()
        return True
    
    @staticmethod
    def get_code_stats(db: Session, code: str) -> dict:
        """코드 통계"""
        stmt = select(InviteCode).where(InviteCode.code == code)
        invite_code = db.execute(stmt).scalars().first()
        
        if not invite_code:
            return {}
        
        # 사용 기록 개수
        usage_count_stmt = select(InviteCodeUsage).where(InviteCodeUsage.code == code)
        usage_count = len(db.execute(usage_count_stmt).scalars().all())
        
        return {
            "code": code,
            "invited_by": invite_code.invited_by,
            "max_uses": invite_code.max_uses,
            "used_count": invite_code.used_count,
            "usage_count": usage_count,  # 시도 횟수
            "expires_at": invite_code.expires_at.isoformat() if invite_code.expires_at else None,
            "grants_tokens": invite_code.grants_tokens,
            "note": invite_code.note,
            "active": invite_code.active,
            "created_at": invite_code.created_at.isoformat(),
        }
    
    @staticmethod
    def get_all_codes(db: Session, active_only: bool = True) -> List[dict]:
        """모든 초대 코드 조회"""
        stmt = select(InviteCode)
        
        if active_only:
            stmt = stmt.where(InviteCode.active == True)
        
        codes = db.execute(stmt).scalars().all()
        
        return [
            {
                "code": c.code,
                "invited_by": c.invited_by,
                "used_count": c.used_count,
                "max_uses": c.max_uses,
                "note": c.note,
                "created_at": c.created_at.isoformat(),
            }
            for c in codes
        ]
    
    @staticmethod
    def deactivate_code(db: Session, code: str) -> bool:
        """코드 비활성화"""
        stmt = select(InviteCode).where(InviteCode.code == code)
        invite_code = db.execute(stmt).scalars().first()
        
        if not invite_code:
            return False
        
        invite_code.active = False
        db.commit()
        
        return True
    
    @staticmethod
    def get_usage_history(
        db: Session,
        code: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """사용 기록 조회"""
        stmt = select(InviteCodeUsage)
        
        if code:
            stmt = stmt.where(InviteCodeUsage.code == code)
        
        stmt = stmt.order_by(InviteCodeUsage.used_at.desc()).limit(limit)
        
        usages = db.execute(stmt).scalars().all()
        
        return [
            {
                "code": u.code,
                "subscriber_id": u.subscriber_id,
                "ip_address": u.ip_address,
                "user_agent": u.user_agent[:100] if u.user_agent else None,
                "used_at": u.used_at.isoformat(),
            }
            for u in usages
        ]


# 테스트
if __name__ == "__main__":
    # 수동 테스트 (실제 DB 필요)
    print("✅ InviteCodeService 정의 완료")
    print("   - generate_code()")
    print("   - validate_code()")
    print("   - link_subscriber()")
    print("   - get_code_stats()")
    print("   - get_all_codes()")
    print("   - deactivate_code()")
    print("   - get_usage_history()")
