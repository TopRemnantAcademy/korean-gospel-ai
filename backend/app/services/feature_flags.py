"""
Feature Flags — Tier 별 기능 관리
- Tier 에 따라 어떤 기능을 활성화할지 결정
- 코드 분기 없음 (설정으로만 관리)
- Tier 미만 기능 사용 시도 → 자동 거부 + 안내
"""
import os
from enum import Enum

# 현재 Tier (환경변수로 관리)
CURRENT_TIER = os.getenv("CURRENT_TIER", "tier_0_5")


class Tier(str, Enum):
    """Tier 정의"""
    TIER_0 = "tier_0"
    TIER_0_5 = "tier_0_5"
    TIER_1 = "tier_1"
    TIER_1_5 = "tier_1_5"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4 = "tier_4"


# Tier 계층 (숫자로 비교 가능하게)
TIER_LEVELS = {
    "tier_0": 0,
    "tier_0_5": 0.5,
    "tier_1": 1,
    "tier_1_5": 1.5,
    "tier_2": 2,
    "tier_3": 3,
    "tier_4": 4,
}


# 기능별 필요 Tier
TIER_FEATURES = {
    "tier_0": {
        "external_access": False,
        "cloudflare_tunnel": False,
        "invite_codes": False,
        "kakao_oauth": False,
        "crisis_router": False,
        "payment": False,
        "monitoring_basic": False,
        "monitoring_advanced": False,
        "domain": False,
        "supabase": False,
        "qdrant_cloud": False,
    },
    "tier_0_5": {
        "external_access": True,  # ✅ Cloudflare Tunnel
        "cloudflare_tunnel": True,
        "invite_codes": True,     # ✅ 베타 초대 코드
        "kakao_oauth": False,
        "crisis_router": False,   # 시범 단계 (운영자 직접 모니터)
        "payment": False,
        "monitoring_basic": False,
        "monitoring_advanced": False,
        "domain": False,
        "supabase": False,
        "qdrant_cloud": False,
    },
    "tier_1": {
        "external_access": True,
        "cloudflare_tunnel": True,
        "invite_codes": True,
        "kakao_oauth": False,     # 준비 (아직 활성화 X)
        "crisis_router": True,    # ✅ 위기 라우팅 자동 활성화
        "payment": False,
        "monitoring_basic": True, # ✅ 기본 모니터링
        "monitoring_advanced": False,
        "domain": False,
        "supabase": False,
        "qdrant_cloud": False,
    },
    "tier_1_5": {
        "external_access": True,
        "cloudflare_tunnel": True,
        "invite_codes": True,
        "kakao_oauth": True,      # ✅ OAuth 정식 운영
        "crisis_router": True,
        "payment": False,         # 준비 (아직 활성화 X)
        "monitoring_basic": True,
        "monitoring_advanced": True,  # ✅ 강화된 모니터링
        "domain": True,           # ✅ 커스텀 도메인
        "supabase": False,        # 준비 (Free 유지)
        "qdrant_cloud": False,
    },
    "tier_2": {
        "external_access": True,
        "cloudflare_tunnel": True,
        "invite_codes": True,
        "kakao_oauth": True,
        "crisis_router": True,
        "payment": True,          # ✅ 결제 기능
        "monitoring_basic": True,
        "monitoring_advanced": True,
        "domain": True,
        "supabase": True,         # ✅ Supabase Pro
        "qdrant_cloud": True,     # ✅ Qdrant Cloud
    },
    "tier_3": {
        "external_access": True,
        "cloudflare_tunnel": True,
        "invite_codes": True,
        "kakao_oauth": True,
        "crisis_router": True,
        "payment": True,
        "monitoring_basic": True,
        "monitoring_advanced": True,
        "domain": True,
        "supabase": True,
        "qdrant_cloud": True,
        # Tier 3+: 사역자 시스템, Read replicas 등
    },
}


class FeatureNotAvailable(Exception):
    """기능이 현재 Tier 에서 사용 불가"""
    pass


class FeatureFlags:
    """기능 플래그 관리"""
    
    @classmethod
    def is_enabled(cls, feature: str, tier: str = None) -> bool:
        """특정 기능이 활성화되어 있는가"""
        if tier is None:
            tier = CURRENT_TIER
        
        if tier not in TIER_FEATURES:
            return False
        
        return TIER_FEATURES[tier].get(feature, False)
    
    @classmethod
    def require(cls, feature: str, tier: str = None):
        """기능 사용 가능 확인, 불가 시 예외"""
        if tier is None:
            tier = CURRENT_TIER
        
        if not cls.is_enabled(feature, tier):
            required_tier = cls.get_tier_for_feature(feature)
            raise FeatureNotAvailable(
                f"'{feature}' 기능은 {required_tier} 이상이 필요합니다. "
                f"현재: {tier}"
            )
    
    @classmethod
    def get_tier_for_feature(cls, feature: str) -> str:
        """기능을 사용하기 위해 필요한 최소 Tier"""
        for tier in sorted(TIER_FEATURES.keys(), key=lambda t: TIER_LEVELS.get(t, 0)):
            if TIER_FEATURES[tier].get(feature, False):
                return tier
        
        return "tier_4"  # 어떤 Tier 에도 없으면
    
    @classmethod
    def get_enabled_features(cls, tier: str = None) -> dict:
        """특정 Tier의 활성화된 모든 기능"""
        if tier is None:
            tier = CURRENT_TIER
        
        return TIER_FEATURES.get(tier, {})
    
    @classmethod
    def get_current_tier(cls) -> str:
        """현재 Tier"""
        return CURRENT_TIER
    
    @classmethod
    def get_current_tier_level(cls) -> float:
        """현재 Tier 레벨 (숫자)"""
        return TIER_LEVELS.get(CURRENT_TIER, 0)


# 코드 사용 예시
if __name__ == "__main__":
    # 예시 1: 기능 활성화 여부 확인
    print(f"카카오 OAuth 활성화? {FeatureFlags.is_enabled('kakao_oauth')}")
    # 출력: 카카오 OAuth 활성화? False (Tier 0.5 에는 없음)
    
    # 예시 2: 기능 필수 확인 (불가 시 예외)
    try:
        FeatureFlags.require("payment")
    except FeatureNotAvailable as e:
        print(f"⚠️ {e}")
    # 출력: ⚠️ 'payment' 기능은 tier_2 이상이 필요합니다. 현재: tier_0_5
    
    # 예시 3: 특정 기능의 필요 Tier
    print(f"결제 기능 필요 Tier: {FeatureFlags.get_tier_for_feature('payment')}")
    # 출력: 결제 기능 필요 Tier: tier_2
    
    # 예시 4: 현재 Tier 의 모든 활성 기능
    enabled = FeatureFlags.get_enabled_features()
    print(f"현재 Tier 활성 기능: {[k for k, v in enabled.items() if v]}")
    # 출력: 현재 Tier 활성 기능: ['external_access', 'cloudflare_tunnel', 'invite_codes']
