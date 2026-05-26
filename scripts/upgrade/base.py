"""
Tier 업그레이드 기본 클래스 및 인터페이스
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Callable
from datetime import datetime


@dataclass
class Check:
    """Pre-flight 체크"""
    name: str
    description: str
    passed: bool
    error: str = None


@dataclass
class UpgradeProgress:
    """진행 상황"""
    current_step: int
    total_steps: int
    current_task: str
    percentage: int
    details: str = ""


class UpgradeRunner(ABC):
    """업그레이드 실행 기본 클래스"""
    
    # 각 업그레이드에서 오버라이드
    name: str = "upgrade"
    estimated_minutes: int = 30
    requires_consent: bool = True
    rollback_window_hours: int = 24
    
    def __init__(self):
        self.snapshot_id = None
        self.start_time = None
        self.end_time = None
    
    @abstractmethod
    async def preflight(self) -> List[Check]:
        """사전 체크 — 모든 조건 확인"""
        pass
    
    @abstractmethod
    async def backup(self) -> str:
        """전체 스냅샷 생성 — 실패 시 되돌리기용"""
        pass
    
    @abstractmethod
    async def execute(self, progress_cb: Callable[[UpgradeProgress], None]):
        """단계별 실행 — progress_cb 로 진행률 업데이트"""
        pass
    
    @abstractmethod
    async def verify(self) -> bool:
        """성공 검증 — 모든 핵심 기능 동작 확인"""
        pass
    
    @abstractmethod
    async def rollback(self, snapshot_id: str):
        """스냅샷에서 복원 — 실패 시 또는 grace period 안 되돌리기"""
        pass
    
    async def run(self, progress_cb: Callable[[UpgradeProgress], None] = None) -> dict:
        """전체 업그레이드 실행"""
        self.start_time = datetime.now()
        
        try:
            # 1. Pre-flight 체크
            if progress_cb:
                await progress_cb(UpgradeProgress(0, 4, "사전 체크", 0))
            
            checks = await self.preflight()
            failed_checks = [c for c in checks if not c.passed]
            
            if failed_checks:
                return {
                    'success': False,
                    'phase': 'preflight',
                    'error': f"{len(failed_checks)}개 체크 실패",
                    'failed_checks': failed_checks,
                }
            
            # 2. 백업
            if progress_cb:
                await progress_cb(UpgradeProgress(1, 4, "백업 생성", 25))
            
            self.snapshot_id = await self.backup()
            
            # 3. 실행
            if progress_cb:
                await progress_cb(UpgradeProgress(2, 4, "업그레이드 실행", 50))
            
            await self.execute(progress_cb)
            
            # 4. 검증
            if progress_cb:
                await progress_cb(UpgradeProgress(3, 4, "검증", 75))
            
            verified = await self.verify()
            
            if not verified:
                # 실패 시 즉시 롤백
                await self.rollback(self.snapshot_id)
                return {
                    'success': False,
                    'phase': 'verify',
                    'error': '검증 실패 — 롤백 완료',
                    'snapshot_id': self.snapshot_id,
                }
            
            # 성공
            self.end_time = datetime.now()
            
            return {
                'success': True,
                'phase': 'complete',
                'snapshot_id': self.snapshot_id,
                'duration_minutes': (self.end_time - self.start_time).total_seconds() / 60,
                'rollback_available_until': self._get_grace_period_end(),
            }
        
        except Exception as e:
            # 예외 발생 시 롤백
            if self.snapshot_id:
                await self.rollback(self.snapshot_id)
            
            return {
                'success': False,
                'phase': 'error',
                'error': str(e),
                'snapshot_id': self.snapshot_id,
            }
    
    def _get_grace_period_end(self) -> str:
        """Grace period 만료 시간"""
        from datetime import timedelta
        grace_end = self.end_time + timedelta(hours=self.rollback_window_hours)
        return grace_end.isoformat()


# 업그레이드 레지스트리
UPGRADES_REGISTRY = {}


def register_upgrade(upgrade_class):
    """업그레이드 등록"""
    UPGRADES_REGISTRY[upgrade_class.name] = upgrade_class
    return upgrade_class


def get_upgrade(name: str) -> UpgradeRunner:
    """업그레이드 가져오기"""
    if name in UPGRADES_REGISTRY:
        return UPGRADES_REGISTRY[name]()
    
    raise ValueError(f"Unknown upgrade: {name}")


def list_upgrades() -> dict:
    """모든 업그레이드 목록"""
    return {
        name: upgrade_class.estimated_minutes
        for name, upgrade_class in UPGRADES_REGISTRY.items()
    }
