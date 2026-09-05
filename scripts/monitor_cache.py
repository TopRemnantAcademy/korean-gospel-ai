#!/usr/bin/env python3
"""
캐시 성능 라이브 모니터링 스크립트

사용법:
    python scripts/monitor_cache.py
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))


async def main():
    print("🌱 캐시 모니터링 시스템을 초기화 중...")

    try:
        from app.services.cache_monitor import cache_monitor
        from app.services.retriever import get_retriever
    except ImportError as e:
        print(f"❌ import 오류: {e}")
        print("   프로젝트 루트에서 실행해 주세요.")
        return

    # 리트리버 로드 (인스턴스 캐시 워밍업)
    print("📦 리트리버 로딩 중...")
    retriever = get_retriever()
    print("✅ 준비 완료!\n")

    # 간단한 테스트 쿼리로 워밍업
    print("🔄 워밍업 쿼리 실행 중...")
    await retriever.retrieve("하나님의 사랑")
    await retriever.retrieve("예수님의 사역")
    print("✅ 워밍업 완료!\n")

    # 통계 출력
    cache_monitor.print_dashboard()

    print("\n💡 팁:")
    print("   - 채팅 서버 실행 중에 이 모듈의 통계를 API로 노출할 수 있습니다")
    print("   - 캐시 히트율이 60% 이상이면 좋은 상태입니다")
    print("   - 히트율이 낮으면 TTL을 늘리거나 쿼리 정규화를 고려하세요")
    print("   - 레이턴시 차이가 크면 캐시가 정말 효과적이라는 의미입니다")


if __name__ == "__main__":
    asyncio.run(main())
