"""
Admin Page 18: Tier Upgrade Wizard
- 현재 Tier 상태 패널
- Tier 카드 갤러리 (미리보기)
- Pre-flight 체크리스트 (Tier 별)
- 1클릭 업그레이드 버튼

실행: streamlit run admin/app.py
메뉴: 18️⃣ 🚀 Tier 업그레이드
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os

import streamlit as st

st.set_page_config(
    page_title="Tier 업그레이드 마법사",
    page_icon="🚀",
    layout="wide",
)

st.title("🚀 Tier 업그레이드 마법사")

st.markdown(
    "월 $0 에서 시작 → 사용자 수에 따라 자동 단계 업그레이드"
)

# ===== 실측 데이터 로드 =====
from backend.app.services.tier_monitor import get_monitor, TIER_LIMITS

_monitor = get_monitor()

@st.cache_data(ttl=30)
def _load_usage():
    try:
        usage = _monitor.measure_sync()
        return {
            "subscriber_count": usage.subscriber_count,
            "active_sessions": usage.active_sessions,
            "db_size_mb": usage.db_size_mb,
            "qdrant_index_mb": usage.qdrant_index_mb,
            "daily_llm_cost": usage.daily_llm_cost_usd,
        }
    except Exception:
        return {
            "subscriber_count": 0, "active_sessions": 0,
            "db_size_mb": 0.0, "qdrant_index_mb": 0.0, "daily_llm_cost": 0.0,
        }

CURRENT_TIER = os.getenv("CURRENT_TIER", "tier_0_5")
_raw = _load_usage()
_limits = TIER_LIMITS.get(CURRENT_TIER, {})

CURRENT_METRICS = {
    "subscriber_count": _raw["subscriber_count"],
    "max_users": _limits.get("max_users", 10),
    "active_sessions": _raw["active_sessions"],
    "max_sessions": _limits.get("max_sessions", 5),
    "db_size_mb": _raw["db_size_mb"],
    "max_db_size_mb": _limits.get("max_db_size_mb", 500),
    "qdrant_index_mb": _raw["qdrant_index_mb"],
    "max_qdrant_index_mb": _limits.get("max_qdrant_size_mb", 1000),
    "daily_llm_cost": _raw["daily_llm_cost"],
    "max_daily_llm_cost": _limits.get("max_daily_llm_cost"),
}

# Tier 메타데이터
TIER_INFO = {
    "tier_0": {
        "name": "Tier 0",
        "subtitle": "로컬 개발",
        "users": "1명",
        "cost": "$0/월",
        "cost_breakdown": "무료",
        "infra": "Localhost + SQLite + Streamlit + Qdrant Local",
        "features": [
            "✅ 단일 개발자",
            "✅ 로컬 호스트만 접근",
            "✅ 무료 LLM (로컬 테스트)",
        ],
        "requirements": [],
        "migration_time": "기본",
        "color": "#e8f5e9",
    },
    "tier_0_5": {
        "name": "Tier 0.5",
        "subtitle": "친구 5명 시범",
        "users": "~10명",
        "cost": "$0/월",
        "cost_breakdown": "무료 (Cloudflare Tunnel)",
        "infra": "Tier 0 + Cloudflare Tunnel + 초대 코드",
        "features": [
            "✅ 외부 접근 (Cloudflare Tunnel)",
            "✅ 베타 초대 코드",
            "✅ 일일 접속 로그",
            "✅ Admin UI 보호 (Cloudflare Access)",
        ],
        "requirements": [
            "Cloudflare 계정",
            "cloudflared 설치",
            "config.yml 설정",
        ],
        "migration_time": "1일",
        "color": "#fff9c4",
        "current": True,
    },
    "tier_1": {
        "name": "Tier 1",
        "subtitle": "소규모 운영",
        "users": "~50명",
        "cost": "$0/월",
        "cost_breakdown": "무료 (Fly.io free tier)",
        "infra": "무료 클라우드 (Fly.io/Render) + 24/7 안정성",
        "features": [
            "✅ 클라우드 호스팅 (24/7)",
            "✅ 기본 모니터링",
            "✅ 위기 라우팅 (Crisis Router) 자동",
            "✅ Kakao OAuth (대비)",
        ],
        "requirements": [
            "Fly.io 계정 생성",
            "Dockerfile 준비 (제공됨)",
            "환경변수 설정",
        ],
        "migration_time": "3일",
        "color": "#c8e6c9",
        "trigger": "사용자 50명 도달 또는 24/7 필요",
    },
    "tier_1_5": {
        "name": "Tier 1.5",
        "subtitle": "안정화 & 도메인",
        "users": "~200명",
        "cost": "$10~30/월",
        "cost_breakdown": "도메인($10/년) + 부분 유료 (Supabase Pro 일부 기능)",
        "infra": "도메인 + Supabase (Free→Pro 전환 시작) + Qdrant Free",
        "features": [
            "✅ 커스텀 도메인 (예: gospel-ai.kr)",
            "✅ 강화된 모니터링",
            "✅ Kakao OAuth (정식 운영)",
            "✅ 백업 & 복구 자동화",
        ],
        "requirements": [
            "도메인 구입 (.com 또는 .kr)",
            "Cloudflare 도메인 연결",
            "Supabase 계정 생성",
            "Qdrant Cloud 계정",
            "개인정보 처리방침 페이지",
            "카카오 OAuth 앱 등록",
        ],
        "migration_time": "1주",
        "color": "#a5d6a7",
        "trigger": "사용자 100명 근처 또는 도메인 필요",
    },
    "tier_2": {
        "name": "Tier 2",
        "subtitle": "중규모 운영",
        "users": "~500명",
        "cost": "$100~200/월",
        "cost_breakdown": "Supabase Pro ($25) + Qdrant Cloud Standard ($99+) + 운영 비용",
        "infra": "Postgres Pro + Qdrant Cloud Standard + 고급 모니터링",
        "features": [
            "✅ DB 무제한 확장",
            "✅ Vector 인덱스 무제한",
            "✅ 고급 모니터링 & 알림",
            "✅ 성능 최적화 지원",
        ],
        "requirements": [
            "Supabase Pro 구독",
            "Qdrant Cloud 표준 플랜",
            "결제 카드 등록",
            "SLA 검토",
        ],
        "migration_time": "1주",
        "color": "#81c784",
        "trigger": "사용자 500명 또는 무료 한도 100% 사용",
    },
}

# ===== 함수들 =====
def get_tier_progress():
    """현재 Tier의 리소스 사용율"""
    tier = CURRENT_TIER
    
    progress = {}
    if tier in ["tier_0_5", "tier_1"]:
        progress["users"] = CURRENT_METRICS["subscriber_count"] / CURRENT_METRICS["max_users"]
        progress["sessions"] = CURRENT_METRICS["active_sessions"] / CURRENT_METRICS["max_sessions"]
        progress["db"] = CURRENT_METRICS["db_size_mb"] / CURRENT_METRICS["max_db_size_mb"]
        progress["qdrant"] = CURRENT_METRICS["qdrant_index_mb"] / CURRENT_METRICS["max_qdrant_index_mb"]
    
    return progress

def render_tier_card(tier_key: str):
    """Tier 카드 렌더링"""
    tier = TIER_INFO[tier_key]
    is_current = tier.get("current", False)
    
    col = st.columns([1])[0]
    
    with col:
        st.markdown(f"""
        <div style='
            background-color: {tier["color"]};
            border: 2px {"solid green" if is_current else "solid #ddd"};
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            {"font-weight: bold;" if is_current else ""}
        '>
        <h4 style='margin-top: 0; margin-bottom: 4px;'>
            {tier["name"]} {" 🌟 현재" if is_current else ""}
        </h4>
        <p style='margin: 0; font-size: 0.9em; color: #666;'>{tier["subtitle"]}</p>
        <hr style='margin: 8px 0;'>
        <p style='margin: 4px 0; font-size: 0.85em;'>
            <b>사용자:</b> {tier["users"]} | <b>비용:</b> {tier["cost"]}
        </p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"📋 {tier['name']} 상세보기", key=f"detail_{tier_key}", use_container_width=True):
            st.session_state[f"show_detail_{tier_key}"] = True


def render_tier_detail(tier_key: str):
    """Tier 상세 정보"""
    tier = TIER_INFO[tier_key]
    
    st.markdown(f"## {tier['name']} — {tier['subtitle']}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📊 사양")
        st.markdown(f"""
        - **사용자 규모**: {tier['users']}
        - **월 비용**: {tier['cost']}
        - **비용 구성**: {tier['cost_breakdown']}
        - **마이그레이션 시간**: {tier['migration_time']}
        """)
        
        st.markdown("### 🏗️ 인프라")
        st.code(tier['infra'], language="text")
    
    with col2:
        st.markdown("### ✨ 주요 기능")
        for feature in tier['features']:
            st.markdown(f"- {feature}")
        
        if tier.get('trigger'):
            st.info(f"⏰ **업그레이드 시점**: {tier['trigger']}")
    
    st.markdown("### 📋 사전 준비 (Pre-flight Checklist)")
    
    requirements = tier.get('requirements', [])
    if requirements:
        for i, req in enumerate(requirements):
            col1, col2 = st.columns([0.1, 0.9])
            with col1:
                st.checkbox("", value=False, key=f"req_{tier_key}_{i}")
            with col2:
                st.text(req)
        
        st.info("💡 **모든 항목을 완료한 후 업그레이드를 시작하세요.**")
    
    st.markdown("---")


# ===== 메인 UI =====

# 탭 구성
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 현재 상태",
    "🃏 Tier 카드",
    "📊 비교 분석",
    "🚀 업그레이드 시뮬레이터",
])

# ===== Tab 1: 현재 상태 =====
with tab1:
    st.subheader("📊 현재 Tier 상태")
    
    tier = TIER_INFO.get(CURRENT_TIER, {})
    
    st.markdown(f"""
    **현재 Tier**: {tier.get('name', 'N/A')} ({tier.get('subtitle', 'N/A')})
    
    **비용**: {tier.get('cost', 'N/A')} — {tier.get('cost_breakdown', 'N/A')}
    """)
    
    st.markdown("### 📈 리소스 사용률")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("👥 사용자", f"{CURRENT_METRICS['subscriber_count']} / {CURRENT_METRICS['max_users']}")
        progress = get_tier_progress()
        if "users" in progress:
            st.progress(progress["users"], text=f"{progress['users']*100:.0f}%")
        
        st.metric("🔄 동시 세션", f"{CURRENT_METRICS['active_sessions']} / {CURRENT_METRICS['max_sessions']}")
        if "sessions" in progress:
            st.progress(progress["sessions"], text=f"{progress['sessions']*100:.0f}%")
    
    with col2:
        st.metric("💾 DB 크기", f"{CURRENT_METRICS['db_size_mb']}MB / {CURRENT_METRICS['max_db_size_mb']}MB")
        if "db" in progress:
            st.progress(progress["db"], text=f"{progress['db']*100:.0f}%")
        
        st.metric("🎯 Qdrant 인덱스", f"{CURRENT_METRICS['qdrant_index_mb']}MB / {CURRENT_METRICS['max_qdrant_index_mb']}MB")
        if "qdrant" in progress:
            st.progress(progress["qdrant"], text=f"{progress['qdrant']*100:.0f}%")
    
    st.markdown("### 💡 추천")
    
    progress = get_tier_progress()
    
    if CURRENT_TIER == "tier_0_5" and progress.get("users", 0) > 0.7:
        st.warning("⏰ **Tier 1 업그레이드 준비 권장** (사용자 70% 이상)")
        st.markdown("👉 아래 '🚀 업그레이드 시뮬레이터' 탭에서 Tier 1 체크리스트 확인")


# ===== Tab 2: Tier 카드 =====
with tab2:
    st.subheader("🃏 Tier 카드")
    
    st.markdown("각 Tier 의 개요를 한눈에 보세요.")
    
    # Tier 0 ~ Tier 2 카드 출력
    tier_keys = ["tier_0", "tier_0_5", "tier_1", "tier_1_5", "tier_2"]
    
    for i, tier_key in enumerate(tier_keys):
        tier = TIER_INFO.get(tier_key, {})
        
        cols = st.columns(5)
        with cols[i % 5]:
            is_current = tier.get("current", False)
            
            color = tier.get("color", "#f5f5f5")
            border = "4px solid green" if is_current else "2px solid #ddd"
            
            with st.container(border=True):
                st.markdown(f"### {tier['name']} {' 🌟' if is_current else ''}")
                st.markdown(f"*{tier['subtitle']}*")
                st.markdown(f"**{tier['users']}** | **{tier['cost']}**")
                
                if st.button("상세보기", key=f"btn_{tier_key}", use_container_width=True):
                    st.session_state[f"show_detail_{tier_key}"] = not st.session_state.get(f"show_detail_{tier_key}", False)
                    st.rerun()
            
            if st.session_state.get(f"show_detail_{tier_key}", False):
                st.divider()
                render_tier_detail(tier_key)


# ===== Tab 3: 비교 분석 =====
with tab3:
    st.subheader("📊 Tier 비교 분석")
    
    st.markdown("모든 Tier 의 사양을 비교하세요.")
    
    # 비교 테이블
    comparison = []
    for tier_key in ["tier_0", "tier_0_5", "tier_1", "tier_1_5", "tier_2"]:
        tier = TIER_INFO.get(tier_key, {})
        comparison.append({
            "Tier": tier.get("name", ""),
            "사용자": tier.get("users", ""),
            "비용": tier.get("cost", ""),
            "외부 접근": "❌" if tier_key in ["tier_0"] else "✅",
            "OAuth": "❌" if tier_key in ["tier_0", "tier_0_5"] else "✅",
            "도메인": "❌" if tier_key in ["tier_0", "tier_0_5", "tier_1"] else "✅",
            "클라우드": "❌" if tier_key in ["tier_0", "tier_0_5"] else "✅",
        })
    
    import pandas as pd
    df = pd.DataFrame(comparison)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ===== Tab 4: 업그레이드 시뮬레이터 =====
with tab4:
    st.subheader("🚀 업그레이드 시뮬레이터")
    
    st.markdown("특정 Tier 로의 업그레이드를 시뮬레이션합니다.")
    
    target_tier = st.selectbox(
        "목표 Tier 선택",
        options=["tier_1", "tier_1_5", "tier_2"],
        format_func=lambda x: TIER_INFO.get(x, {}).get("name", ""),
    )
    
    if target_tier:
        tier = TIER_INFO.get(target_tier, {})
        
        st.markdown(f"## {tier['name']} 으로 업그레이드")
        
        st.markdown("### 📋 Pre-flight 체크리스트")
        
        all_checked = True
        requirements = tier.get('requirements', [])
        
        for i, req in enumerate(requirements):
            checked = st.checkbox(req, key=f"sim_{target_tier}_{i}")
            all_checked = all_checked and checked
        
        st.markdown("---")
        
        if all_checked:
            st.success("✅ 모든 준비가 완료되었습니다!")
            
            if st.button("🚀 업그레이드 시작", type="primary", use_container_width=True):
                st.info(f"""
                업그레이드 진행 중...
                - 백업 생성
                - 설정 마이그레이션
                - 서비스 재시작
                - 검증
                
                예상 시간: {tier.get('migration_time', '1주')}
                """)
                st.success("✅ 업그레이드 완료! 24시간 이내 되돌리기 가능")
        else:
            st.warning(f"⚠️ {len([r for i, r in enumerate(requirements) if not st.session_state.get(f'sim_{target_tier}_{i}', False)])}개 항목 미완료")
            st.markdown("💡 모든 항목을 완료한 후 업그레이드를 시작하세요.")


st.markdown("---")

st.markdown("""
### 📞 지원
- 문제 발생: `admin/pages/9_👥_사람.py` 에서 운영자 연락
- 긴급: 한국생명의전화 1588-9191
""")
