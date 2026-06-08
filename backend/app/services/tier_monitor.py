"""
Tier 모니터링 — 리소스 사용량 추적 & 한계 근접 알림
- 5초마다 사용량 측정
- Tier 별 한계치 초과 감지
- Admin 알림 발송
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path

# Tier별 한계치 정의
TIER_LIMITS = {
    "tier_0": {
        "max_users": 1,
        "max_sessions": 1,
        "max_db_size_mb": 50,
        "max_qdrant_size_mb": 500,
        "max_daily_llm_cost": None,  # 무제한
    },
    "tier_0_5": {
        "max_users": 10,
        "max_sessions": 5,
        "max_db_size_mb": 500,
        "max_qdrant_size_mb": 1000,
        "max_daily_llm_cost": None,  # 무제한
    },
    "tier_1": {
        "max_users": 50,
        "max_sessions": 30,
        "max_db_size_mb": 5000,
        "max_qdrant_size_mb": 5000,
        "max_daily_llm_cost": None,  # 무제한
    },
    "tier_1_5": {
        "max_users": 200,
        "max_sessions": 100,
        "max_db_size_mb": 20000,
        "max_qdrant_size_mb": 20000,
        "max_daily_llm_cost": 100,  # $100/일
    },
    "tier_2": {
        "max_users": 500,
        "max_sessions": 300,
        "max_db_size_mb": None,  # 무제한
        "max_qdrant_size_mb": None,  # 무제한
        "max_daily_llm_cost": 1000,  # $1000/일
    },
}


@dataclass
class TierUsage:
    """리소스 사용량"""
    timestamp: str
    
    subscriber_count: int
    active_sessions: int
    db_size_mb: float
    qdrant_index_mb: float
    daily_llm_cost_usd: float
    streamlit_response_time_ms: float
    
    # 경고 플래그
    warnings: list = None


@dataclass
class ResourceThreshold:
    """리소스 한계 기록"""
    metric: str  # 'user_count', 'db_size', etc.
    current: float
    limit: float
    percentage: float  # 0-100
    status: str  # 'normal', 'warning' (70%), 'critical' (90%)


class TierMonitor:
    """Tier 리소스 모니터링"""
    
    def __init__(self, current_tier: str = "tier_0_5"):
        self.current_tier = current_tier
        self.limits = TIER_LIMITS.get(current_tier, {})
        self.usage_history = []  # 최근 100개 기록
        self.alert_history = []  # 최근 50개 알림
    
    def measure_sync(self) -> TierUsage:
        """현재 리소스 사용량 실측 (동기 버전).
        Streamlit 등 이미 이벤트 루프가 실행 중인 컨텍스트에서 사용.
        """
        usage = TierUsage(
            timestamp=datetime.now().isoformat(),
            subscriber_count=self._count_subscribers(),
            active_sessions=0,  # 향후 Redis 기반으로 대체
            db_size_mb=self._db_size_mb(),
            qdrant_index_mb=self._qdrant_size_mb(),
            daily_llm_cost_usd=0.0,  # 향후 E-A tokens_lifetime_used 집계로 대체
            streamlit_response_time_ms=0.0,
            warnings=[],
        )
        self.usage_history.append(usage)
        if len(self.usage_history) > 100:
            self.usage_history = self.usage_history[-100:]
        return usage

    async def measure(self) -> TierUsage:
        """현재 리소스 사용량 실측 (비동기 버전)."""
        return self.measure_sync()

    def _count_subscribers(self) -> int:
        try:
            import sys
            from pathlib import Path
            _root = Path(__file__).resolve().parent.parent.parent.parent
            if str(_root) not in sys.path:
                sys.path.insert(0, str(_root))
            from backend.app.db import get_session
            from backend.app.models.orm import Subscriber
            with get_session() as s:
                return s.query(Subscriber).count()
        except Exception:
            return 0

    def _db_size_mb(self) -> float:
        import os
        from pathlib import Path
        candidates = [".gospel.db", "gospel.db", "data/gospel.db"]
        for c in candidates:
            p = Path(c)
            if p.exists():
                return round(p.stat().st_size / (1024 * 1024), 2)
        return 0.0

    def _qdrant_size_mb(self) -> float:
        """Qdrant 컬렉션 크기 조회. 실패 시 0 반환."""
        try:
            from qdrant_client import QdrantClient
            import os
            url = os.getenv("QDRANT_URL", "http://localhost:6333")
            key = os.getenv("QDRANT_API_KEY") or None
            client = QdrantClient(url=url, api_key=key, timeout=3)
            total = 0
            for col in client.get_collections().collections:
                info = client.get_collection(col.name)
                total += getattr(info, "vectors_count", 0) or 0
            # 벡터 수 × 평균 벡터 크기(768dim float32 ≈ 3KB) 로 MB 추정
            return round(total * 3 / 1024, 1)
        except Exception:
            return 0.0
    
    async def check_thresholds(self, usage: TierUsage) -> list:
        """한계치 초과 확인"""
        thresholds = []
        limits = self.limits
        
        # 사용자 수
        if limits.get("max_users"):
            pct = (usage.subscriber_count / limits["max_users"]) * 100
            if pct >= 90:
                thresholds.append(ResourceThreshold(
                    metric="subscriber_count",
                    current=usage.subscriber_count,
                    limit=limits["max_users"],
                    percentage=pct,
                    status="critical",
                ))
                usage.warnings.append(f"🔴 사용자 수 임계: {usage.subscriber_count}/{limits['max_users']} ({pct:.0f}%)")
            elif pct >= 70:
                thresholds.append(ResourceThreshold(
                    metric="subscriber_count",
                    current=usage.subscriber_count,
                    limit=limits["max_users"],
                    percentage=pct,
                    status="warning",
                ))
                usage.warnings.append(f"🟡 사용자 수 주의: {usage.subscriber_count}/{limits['max_users']} ({pct:.0f}%)")
        
        # DB 크기
        if limits.get("max_db_size_mb"):
            pct = (usage.db_size_mb / limits["max_db_size_mb"]) * 100
            if pct >= 90:
                thresholds.append(ResourceThreshold(
                    metric="db_size_mb",
                    current=usage.db_size_mb,
                    limit=limits["max_db_size_mb"],
                    percentage=pct,
                    status="critical",
                ))
                usage.warnings.append(f"🔴 DB 크기 임계: {usage.db_size_mb:.0f}MB/{limits['max_db_size_mb']}MB ({pct:.0f}%)")
            elif pct >= 70:
                thresholds.append(ResourceThreshold(
                    metric="db_size_mb",
                    current=usage.db_size_mb,
                    limit=limits["max_db_size_mb"],
                    percentage=pct,
                    status="warning",
                ))
        
        # Qdrant 인덱스 크기
        if limits.get("max_qdrant_size_mb"):
            pct = (usage.qdrant_index_mb / limits["max_qdrant_size_mb"]) * 100
            if pct >= 90:
                thresholds.append(ResourceThreshold(
                    metric="qdrant_index_mb",
                    current=usage.qdrant_index_mb,
                    limit=limits["max_qdrant_size_mb"],
                    percentage=pct,
                    status="critical",
                ))
        
        # LLM 비용
        if limits.get("max_daily_llm_cost"):
            pct = (usage.daily_llm_cost_usd / limits["max_daily_llm_cost"]) * 100
            if pct >= 90:
                thresholds.append(ResourceThreshold(
                    metric="daily_llm_cost",
                    current=usage.daily_llm_cost_usd,
                    limit=limits["max_daily_llm_cost"],
                    percentage=pct,
                    status="critical",
                ))
        
        return thresholds
    
    async def suggest_upgrade(self, thresholds: list) -> str:
        """업그레이드 제안"""
        if not thresholds:
            return None
        
        critical_count = sum(1 for t in thresholds if t.status == "critical")
        
        if critical_count > 0:
            return "🚀 Tier 업그레이드를 시작하세요! (admin/pages/18_🚀_Tier_업그레이드.py)"
        
        return "⏰ Tier 업그레이드를 준비하세요."
    
    async def run_monitoring_loop(self, interval_seconds: int = 5):
        """백그라운드 모니터링 루프"""
        while True:
            try:
                usage = await self.measure()
                thresholds = await self.check_thresholds(usage)
                
                if thresholds:
                    suggestion = await self.suggest_upgrade(thresholds)
                    self.alert_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'thresholds': thresholds,
                        'suggestion': suggestion,
                    })
                    
                    # 마지막 50개만 보관
                    if len(self.alert_history) > 50:
                        self.alert_history = self.alert_history[-50:]
                
                await asyncio.sleep(interval_seconds)
            
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                await asyncio.sleep(interval_seconds)
    
    def get_latest_usage(self) -> TierUsage:
        """최근 측정 데이터"""
        return self.usage_history[-1] if self.usage_history else None
    
    def get_alert_history(self, limit: int = 10) -> list:
        """최근 알림 기록"""
        return self.alert_history[-limit:]
    
    def export_metrics(self, output_path: str = None) -> str:
        """메트릭 내보내기 (CSV)"""
        if not output_path:
            output_path = f"tier_metrics_{datetime.now().date()}.csv"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("timestamp,subscriber_count,active_sessions,db_size_mb,qdrant_index_mb,daily_llm_cost\n")
            for usage in self.usage_history:
                f.write(f"{usage.timestamp},{usage.subscriber_count},{usage.active_sessions},"
                        f"{usage.db_size_mb:.1f},{usage.qdrant_index_mb:.1f},{usage.daily_llm_cost_usd:.2f}\n")
        
        return output_path


# 글로벌 모니터 인스턴스
_monitor = None


def get_monitor() -> TierMonitor:
    """글로벌 모니터 인스턴스 가져오기"""
    global _monitor
    if _monitor is None:
        current_tier = os.getenv("CURRENT_TIER", "tier_0_5")
        _monitor = TierMonitor(current_tier)
    
    return _monitor


if __name__ == "__main__":
    # 테스트
    import asyncio
    
    async def test():
        monitor = TierMonitor("tier_0_5")
        
        # 측정
        usage = await monitor.measure()
        print(f"📊 Usage: {usage.subscriber_count} users, {usage.active_sessions} sessions")
        
        # 한계치 확인
        thresholds = await monitor.check_thresholds(usage)
        print(f"📈 Thresholds: {len(thresholds)} alerts")
        
        # 제안
        suggestion = await monitor.suggest_upgrade(thresholds)
        if suggestion:
            print(f"💡 {suggestion}")
    
    asyncio.run(test())
