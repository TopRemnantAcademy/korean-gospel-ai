# 📡 Cloudflare Tunnel 운영 가이드 (gospel-ai)

> **목표**: 친구 5명이 운영자 PC 에서 안정적으로 gospel-ai 를 시범 사용 → 피드백 수집

---

## 🚀 1단계: 설치 & 초기 설정 (5분)

### 1.1 Cloudflared 설치
```bash
cd scripts
install_cloudflared.bat
```

**진행 과정**:
1. Cloudflared 다운로드 링크 제공 → 수동 다운로드 필요
2. `cloudflared --version` 확인
3. Cloudflare 계정 로그인 (브라우저 팝업)
4. Tunnel 자동 생성: `gospel-ai`
5. `config.yml` 자동 생성 (`~/.cloudflared/config.yml`)

✅ 완료 신호: 터미널에 "✅ 설치 완료!" 표시

### 1.2 credentials-file 경로 확인

```bash
# Windows PowerShell
dir $env:USERPROFILE\.cloudflared\*.json
```

**결과**: UUID 형식의 파일명 (예: `12345678-1234-1234-1234-123456789012.json`)

이 UUID 를 `config.yml` 의 `credentials-file` 에 입력:
```yaml
credentials-file: C:\Users\YourUsername\.cloudflared\12345678-1234-1234-1234-123456789012.json
```

---

## 🎬 2단계: Tunnel & 앱 실행 (3분)

### 2.1 Tunnel 시작 (별도 CMD 창 1)
```bash
STEP4_TUNNEL.bat run
```

**예상 출력**:
```
✅ Tunnel 이 실행 중이면 다음 URL 로 접속 가능:
   - User  : https://gospel-ai.trycloudflare.com
   - Admin : https://admin-gospel-ai.trycloudflare.com
```

### 2.2 User UI 시작 (별도 CMD 창 2)
```bash
python -m streamlit run user/app.py --server.port 8502 --server.address 127.0.0.1
```

**예상 출력**:
```
Local URL: http://127.0.0.1:8502
Tunnel URL: https://gospel-ai.trycloudflare.com
```

### 2.3 Admin UI 시작 (별도 CMD 창 3, 선택)
```bash
python -m streamlit run admin/app.py --server.port 8501 --server.address 127.0.0.1
```

✅ 완료: 3개 CMD 창이 모두 실행 중

---

## 👥 3단계: 친구 초대 & 피드백 (지속적)

### 3.1 초대 코드 발급

**User UI 의 관리 페이지**:
1. User 앱 접속: `https://gospel-ai.trycloudflare.com`
2. 좌측 메뉴 → "관리" → "초대 코드 생성"
3. 초대 코드 복사 (예: `BETA-GOSPEL-ABC123`)
4. **각 친구마다 새 코드 생성** (접근 추적 가능)

### 3.2 친구에게 공유

**이메일 또는 메시지**:
```
안녕하세요! 👋

gospel-ai 베타 시험에 초대합니다!

📱 접속 URL: https://gospel-ai.trycloudflare.com
🔑 초대 코드: BETA-GOSPEL-ABC123

사용법:
1. 위 URL 에서 "가입" 선택
2. 초대 코드 입력
3. 계정 생성 후 진단·기도·채팅 사용 가능

💬 피드백 양식: [Google Forms 링크]

감사합니다! 🙏
```

### 3.3 피드백 수집

**Google Forms 만들기** (`docs/FEEDBACK_FORM.md` 참조):
- 사용 난이도 (1~5)
- 기능 만족도
- 개선 요청
- 버그 리포트
- 연락처

---

## 🛡️ 4단계: Admin UI 보호 (필수)

### 4.1 Cloudflare Access 설정

> **목표**: Admin UI 는 운영자만 접근 가능

**절차**:
1. Cloudflare 대시보드: https://dash.cloudflare.com/
2. "Tunnel" 섹션 → "gospel-ai"
3. "Public Hostnames" → "admin-gospel-ai.trycloudflare.com"
4. "Application Settings" → "Access (Authentication Required)"
5. **Policy 추가**:
   - **Name**: "Operator Only"
   - **Action**: Allow
   - **Who can access**: Email
   - **Email list**: 운영자 이메일 (예: `gospel@church.kr`)

### 4.2 테스트
- 운영자 이메일로 접속: ✅ 로그인 후 접근 가능
- 다른 이메일로 접속: ❌ 접근 차단

---

## 📊 5단계: 모니터링 & 문제 해결

### 5.1 접속 현황 확인

**Streamlit 의 기본 메뉴**:
- "Manage app"
- "Rerun"
- "App analytics" (있는 경우)

**Cloudflare Dashboard**:
- https://dash.cloudflare.com/ → "Analytics" → Tunnel 트래픽

### 5.2 로그 확인

```bash
# Tunnel 로그
type TUNNEL_LOGS.txt

# Streamlit 로그
# User 앱 실행 중인 CMD 창 참조

# 접속 IP 기록 (daily)
type user\logs\access_ips.txt
```

### 5.3 일반적인 문제

| 증상 | 해결책 |
|---|---|
| "Tunnel 을 찾을 수 없음" | `install_cloudflared.bat` 다시 실행 |
| "지정된 포트는 이미 사용 중" | `netstat -ano` 로 프로세스 확인 후 종료 |
| "친구가 403 Forbidden 봄" | config.yml 의 hostname 이 잘못되었거나, Access Policy 확인 |
| "Admin UI 에 못 들어감" | Cloudflare Access Policy 설정 완료? |

---

## 🔄 6단계: 종료 & 정리

### 6.1 Tunnel 종료
```bash
STEP4_TUNNEL.bat stop
# 또는 Ctrl+C (Tunnel 실행 중인 CMD 창)
```

### 6.2 앱 종료
- User/Admin 앱 각각 Ctrl+C

### 6.3 자동 "점검 중" 페이지

Tunnel 종료 후 친구가 접속하면:
```
🚧 현재 점검 중입니다
gospel-ai 는 일시적으로 점검 중입니다.
잠시 후 다시 시도해주세요. 🙏
```

---

## 📈 예상 시나리오

### 일일 운영 루틴 (30분)

```
08:00 - Tunnel 시작 (STEP4_TUNNEL.bat run)
08:05 - User 앱 시작 (streamlit run user/app.py)
08:10 - 친구 5명 접속 시작
12:00 - 중간 피드백 확인 (Google Forms)
18:00 - 앱 종료, 로그 백업
        → 피드백 정리, CHANGELOG.md 기록
```

### 일주일 마일스톤

| Day | 목표 | 체크 |
|---|---|---|
| Day 1 | 초대 코드 생성, 친구 2명 가입 | ✅ |
| Day 2-3 | 친구 5명 전원 가입, 기본 기능 테스트 | ✅ |
| Day 4-5 | 버그 리포트 수집, 긴급 패치 | ✅ |
| Day 6-7 | 최종 피드백 정리, EPIC D/E 방향 검증 | ✅ |

---

## 🔐 보안 체크리스트

- [ ] Admin UI 는 Cloudflare Access 로 보호
- [ ] User UI 는 베타 초대 코드 검증 활성화
- [ ] 접속 IP 로그 활성화 (daily)
- [ ] 친구의 개인정보 처리 동의 수집 (개인정보 처리방침)
- [ ] 종료 후 config.yml 의 credentials-file 정보 삭제 또는 보관

---

## 📞 긴급 대응

| 상황 | 조치 |
|---|---|
| Tunnel 이 자꾸 끊김 | cloudflared 최신 버전 확인 |
| 친구가 느림 | Streamlit 재시작, 브라우저 캐시 삭제 |
| 오류 500 | 로그 확인, 백엔드 오류 있는지 진단 |
| DDoS 의심 | Cloudflare Dashboard 의 rate limiting 활성화 |

---

## 📚 참고 자료

- **Cloudflare Tunnel 공식 문서**: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- **Streamlit 배포**: https://docs.streamlit.io/deploy
- **PROCESS_MAP.md**: 시스템 아키텍처 확인
- **CHANGELOG.md**: 변경 사항 기록

---

**마지막 확인**: 이 가이드는 Tier 0.5 (시범 운영) 용입니다. 
5명 이상 지속 운영 시 Tier 1 업그레이드 검토하세요 (`admin/pages/18_🚀_Tier_업그레이드.py`).
