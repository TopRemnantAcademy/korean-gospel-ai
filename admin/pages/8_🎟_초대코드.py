"""
Admin Page: 초대 코드 관리 (Tier 0.5 베타)
- 초대 코드 생성/관리
- 사용 기록 추적
- 일일 접속 리포트
- 남용 감지

실행: streamlit run admin/app.py
메뉴: 8️⃣ 초대 코드 관리
"""
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from user.invite_code import (
    generate_invite_code,
    validate_invite_code,
    get_invite_code_stats,
    get_daily_access_report,
    export_access_logs,
    init_db,
)

st.set_page_config(
    page_title="초대 코드 관리",
    page_icon="🎟",
    layout="wide",
)

st.title("🎟 초대 코드 관리 — Tier 0.5 베타")

st.markdown(
    "친구 5명 시범 운영을 위한 초대 코드 생성, 관리, 추적"
)

# 초기화
init_db()

# ===== 탭 구성 =====
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 개요",
    "📋 코드 생성",
    "📊 통계 & 리포트",
    "⚠️ 남용 감지",
])


# ===== Tab 1: 개요 =====
with tab1:
    st.subheader("📌 Tier 0.5 베타 운영 상태")
    
    stats = get_invite_code_stats()
    access_report = get_daily_access_report()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "🎟 활성 초대 코드",
            stats['total_codes'],
            help="생성된 코드 중 활성화된 개수"
        )
    
    with col2:
        st.metric(
            "✅ 총 사용 횟수",
            stats['total_uses'],
            help="모든 코드의 누적 사용 횟수"
        )
    
    with col3:
        st.metric(
            "👥 오늘 고유 IP",
            stats['today_unique_ips'],
            help="오늘 접속한 고유 IP 주소 개수"
        )
    
    st.markdown("---")
    
    st.subheader("🎯 운영 목표")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### 현재 단계
        **Tier 0.5**: 친구 5명 시범 운영
        - ✅ Cloudflare Tunnel 운영 중
        - ✅ 베타 초대 코드 배포
        - ✅ 접속 및 사용량 모니터링
        
        ### 목표
        1. 5명 전원 가입 완료
        2. 기본 기능 테스트 (진단, 기도, 채팅)
        3. 피드백 수집 (Google Forms)
        4. EPIC D/E 방향 검증
        """)
    
    with col2:
        st.markdown("""
        ### 일일 체크리스트
        - [ ] 초대 코드 생성 완료
        - [ ] 친구 5명에게 공유
        - [ ] 접속 현황 확인
        - [ ] 피드백 정리
        - [ ] 버그 리포트 처리
        
        ### 예상 일정
        - Day 1: 초대, 2명 가입
        - Day 2-3: 5명 전원 가입
        - Day 4-5: 버그 수집 & 패치
        - Day 6-7: 최종 피드백 정리
        """)


# ===== Tab 2: 코드 생성 =====
with tab2:
    st.subheader("📋 초대 코드 생성")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        max_uses = st.number_input(
            "최대 사용 횟수",
            min_value=1,
            max_value=100,
            value=1,
            help="코드를 몇 번 사용할 수 있는가 (1 = 1명만 사용 가능)"
        )
    
    with col2:
        expires_hours = st.number_input(
            "만료 시간 (시간)",
            min_value=1,
            max_value=24*365,
            value=24*7,  # 기본: 7일
            help="코드가 언제 만료되는가"
        )
    
    with col3:
        created_by = st.text_input(
            "생성자",
            value="admin",
            help="코드를 생성한 사람 (기록용)"
        )
    
    col1, col2 = st.columns(2)
    
    with col1:
        num_codes = st.number_input(
            "생성할 코드 수",
            min_value=1,
            max_value=10,
            value=1,
        )
    
    with col2:
        st.write("")  # 공간
        st.write("")  # 공간
        generate_btn = st.button("🎟 코드 생성", use_container_width=True, type="primary")
    
    if generate_btn:
        codes = []
        for _ in range(num_codes):
            code = generate_invite_code(
                max_uses=max_uses,
                expires_hours=expires_hours,
                created_by=created_by,
            )
            codes.append(code)
        
        st.success(f"✅ {num_codes}개 코드 생성 완료!")
        
        # 코드 표시
        st.markdown("### 생성된 코드")
        for code in codes:
            st.code(code, language="text")
        
        # 복사 버튼용 전체 텍스트
        all_codes = "\n".join(codes)
        st.text_area(
            "모두 복사 (각 친구에게 공유)",
            value=all_codes,
            height=150,
            disabled=True,
        )
        
        st.info("""
        💡 **친구에게 공유하는 방법**:
        
        1. 위 코드를 복사
        2. 메일 또는 메시지로 전송
        3. 친구가 gospel-ai.trycloudflare.com 에서 코드 입력
        4. 가입 및 사용 시작
        """)


# ===== Tab 3: 통계 & 리포트 =====
with tab3:
    st.subheader("📊 통계 & 리포트")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 코드 통계")
        stats = get_invite_code_stats()
        st.metric("활성 코드", stats['total_codes'])
        st.metric("총 사용", stats['total_uses'])
        st.metric("오늘 고유 IP", stats['today_unique_ips'])
    
    with col2:
        st.markdown("### 일일 접속 현황")
        
        if not st.session_state.get("_refresh_access_log"):
            st.session_state._refresh_access_log = True
        
        refresh_btn = st.button("🔄 새로고침")
        if refresh_btn:
            st.rerun()
        
        access_report = get_daily_access_report()
        
        if access_report:
            df = pd.DataFrame([
                {
                    'IP 주소': r['ip'],
                    '접속 횟수': r['access_count'],
                    '사용자 ID': r['user_id'] or '(미등록)',
                    '사용한 코드': r['code_used'] or '(없음)',
                }
                for r in access_report
            ])
            
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("오늘 접속 기록이 없습니다.")
    
    st.markdown("---")
    
    # 로그 내보내기
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 접속 로그 내보내기 (CSV)", use_container_width=True):
            log_path = export_access_logs()
            st.success(f"✅ 로그가 저장되었습니다: {log_path}")
            with open(log_path, 'rb') as f:
                st.download_button(
                    "📥 다운로드",
                    f,
                    file_name=f"access_logs_{datetime.now().date()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )


# ===== Tab 4: 남용 감지 =====
with tab4:
    st.subheader("⚠️ 남용 감지 & 관리")
    
    st.markdown("""
    ### 모니터링 항목
    
    - 🔴 **단일 IP의 과도한 접속**: 동일 IP가 짧은 시간에 많이 접속
    - 🟡 **비정상적 코드 사용 패턴**: 코드 한 번에 과도한 계정 생성
    - 🟠 **VPN/프록시 의심**: 자동 감지 (추후 구현)
    - ⚠️ **시간대 이상 패턴**: 새벽 대량 접속 감지
    """)
    
    st.markdown("---")
    
    # 위험 지표
    access_report = get_daily_access_report()
    
    if access_report:
        suspicious = []
        
        for r in access_report:
            # 과도한 접속 (같은 IP에서 10회 이상)
            if r['access_count'] >= 10:
                suspicious.append({
                    '유형': '과도한 접속',
                    'IP': r['ip'],
                    '횟수': r['access_count'],
                    '위험도': '🔴 높음',
                })
            # 중간 정도 접속
            elif r['access_count'] >= 5:
                suspicious.append({
                    '유형': '증가된 접속',
                    'IP': r['ip'],
                    '횟수': r['access_count'],
                    '위험도': '🟡 중간',
                })
        
        if suspicious:
            st.warning(f"⚠️ {len(suspicious)}개의 의심 항목 감지")
            df_suspicious = pd.DataFrame(suspicious)
            st.dataframe(df_suspicious, use_container_width=True, hide_index=True)
            
            st.markdown("### 조치 방법")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔒 IP 차단 (추후 구현)", disabled=True, use_container_width=True):
                    pass
            
            with col2:
                if st.button("📝 주의 알림 (추후 구현)", disabled=True, use_container_width=True):
                    pass
        else:
            st.success("✅ 남용 의심 항목 없음 — 정상 운영 중")
    else:
        st.info("아직 접속 기록이 없습니다.")
    
    st.markdown("---")
    
    st.markdown("""
    ### 향후 개선 (Tier 1.5)
    
    1. **자동 IP 차단**: Cloudflare 규칙 연동
    2. **Rate Limiting**: 초당 요청 수 제한
    3. **지역 분석**: GeoIP 기반 비정상 접속 감지
    4. **봇 감지**: User-Agent 분석
    5. **이메일 알림**: 의심 활동 발생 시 즉시 알림
    """)
