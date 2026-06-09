# Efficiency Audit Report — korean-gospel-ai

**일시**: 2026-06-09
**범위**: 전체 프로젝트 (로직, 프로세스, 코드, 배포, 스크립트)

---

## 점수 요약

| 영역 | 점수 | 등급 |
|------|------|------|
| 핵심 로직 | 7/10 | 양호 |
| 코드 품질 | 5/10 | 중복 많음 |
| 배포 환경 | 4/10 | 통합 후 미반영 |
| 데드코드 | 3/10 | 1,100줄+ 제거 가능 |
| 배치 스크립트 | 4/10 | 중복, 구버전 참조 |

---

## 🔴 HIGH — 로직 버그 / 기능 불일치

### 1. /chat vs /chat/stream 파이프라인 200줄 중복 + 6개 기능 차이

**파일**: `backend/app/api/chat.py`

두 엔드포인트가 전체 파이프라인을 각자 구현. 다음 기능이 **stream 미구현**:

| 기능 | /chat | /chat/stream | 영향 |
|------|-------|-------------|------|
| 토큰 쿼터 체크 | O | **X** | 사용자가 stream으로 쿼터 우회 가능 |
| 토큰 소비 정산 | O | **X** | stream 사용량 집계 누락 |
| 온보딩 질문 | O | **X** | stream 사용자는 온보딩 못 봄 |
| 구원 감지 | 백그라운드 | **인라인 (블로킹)** | stream 레이턴시 불필요 증가 |
| 플러터리 필터 B/C | Layer A+B+C | Layer A+C만 | 품질 검증 비대칭 |
| 출력 정책 심사 | 백그라운드 | **X** | stream 응답 정책 위반 탐지 불가 |

**권장**: `ChatPipeline` 공통 클래스로 추출, 양쪽 엔드포인트에서 호출

### 2. 구원 감지가 stream에서 인라인 실행

`/chat/stream`의 577-591행: LLM 호출로 구원 신호를 **매 응답마다 동기적으로** 감지함. `/chat`에서는 백그라운드 작업.

→ stream 모드 사용자에게 불필요한 1~3초 지연 추가

---

## 🟡 MEDIUM — 중복 / 유지보수 부담

### 3. 22개 Pydantic 스키마가 8개 API 파일에 분산

- `chat.py`: FeedbackRequest, GreetingResponse
- `documents.py`: DraftMetaIn, DocMetaIn, BodyPatchIn 등 7개
- `subscriber.py`: UserProfileUpdateReq 등 4개
- `auth.py`: SignupReq, LoginReq, AuthResponse
- `prompts.py`: PromptIn
- `glossary.py`: ApproveIn, MergeIn, PatchTermIn
- `memory.py`: FeedbackIn
- `drafts.py`: DraftIn

**권장**: `models/schemas.py`에 통합 (이미 존재하는 파일). 약 150줄 이관 + import 간소화.

### 4. docker-compose.prod.yml 통합 미반영

UI 통합(app.py 생성) 후에도 docker-compose.prod.yml은:
- `user-ui` 서비스 (user/app.py 포트 8501)
- `admin-ui` 서비스 (admin/app.py 포트 8502)

→ 통합 app.py 하나만 실행하는 구조로 업데이트 필요

### 5. Dockerfile도 구버전 구조

`Dockerfile`이 `admin/`, `user/`를 별도로 복사하지만 통합 앱은 루트 `app.py` 하나만 필요.

### 6. 배치 스크립트 4개에 구버전 참조

| 파일 | 문제 |
|------|------|
| STEP4_TUNNEL.bat:96 | `user/app.py --server.port 8502` |
| STEP4_TUNNEL.bat:97 | `admin/app.py --server.port 8501 (선택)` |
| scripts/install_cloudflared.bat:117-118 | 같은 구버전 참조 |

### 7. Admin 비밀번호 게이트 2중 구현

- `app.py:56-73`: `_admin_login_ui()` — APP_PASSWORD 검사
- `admin/lib/auth.py:18-31`: `gate()` — 같은 검사

`app.py`가 명시적으로 `st.session_state.auth_ok = True`를 설정해 "gate() 호환" 주석. 취약한 결합.

### 8. subscriber_service.py의 미사용 함수 3개

- `increment_session()` (189행) — 전역 임포트 0건
- `increment_question()` (196행) — 전역 임포트 0건
- `merge_auto_signal()` (212행) — 전역 임포트 0건

전부 `prepare_profile()`에 흡수되었으나 정리되지 않음. 약 40줄.

---

## 🟢 LOW — 데드코드 / 정리

### 9. tier_monitor.py — 320줄 (백엔드 임포트 0건)

관리자 UI `4_📊_Status.py`에서만 직접 임포트. `sys.path` 조작으로 backend 모듈을 우회 로딩.

### 10. feature_flags.py — 196줄 (전역 임포트 0건)

Tier 기반 기능 게이트 로직. `config.py`의 boolean 플래그가 대신 사용 중.

### 11. requirements-mentoring.txt

`motor==3.6.0` (MongoDB 드라이버) — 프로젝트 전체에서 motor/MongoDB 참조 0건.

### 12. 오래된 __pycache__

- Python 3.10 / 3.14 bytecode 잔존
- 삭제된 소스의 .pyc 생존: `mentoring.cpython-312.pyc`, `admin_agent.cpython-312.pyc`, `ingest.cpython-312.pyc`

### 13. 삭제된 Admin 페이지의 .pyc 잔존

admin/pages/__pycache__/ 에 6개 오펀 .pyc:
- 초대코드, 영적상태, 봇관리, 정제검토, Tier_업그레이드, 재방문_관리

### 14. _archive/ingest_documents.py — 깨진 임포트

18행: `from backend.app.services.document_indexer import index_documents_folder` → 모듈이 이미 아카이브됨.

### 15. 배치 스크립트 10개 — 통합 가능성

| 스크립트 | 행 | 기능 |
|----------|----|------|
| BACKUP.bat | 28 | .bak 생성 |
| RESTORE.bat | 19 | .bak 복원 |
| SCHEDULE_BACKUP.bat | 35 | 작업 스케줄러 등록 |
| UNSCHEDULE_BACKUP.bat | 15 | 작업 스케줄러 해제 |
| RESET_ALL.bat | 58 | DB 초기화 + 재시작 |
| DIAGNOSE.bat | 34 | 진단 실행 |

→ BACKUP + RESTORE + SCHEDULE + UNSCHEDULE 4개 → 1개로 통합 가능. RESET_ALL은 RESTORE와 겹침.

---

## 🛑 발견된 추가 이슈 (audit 중 발견)

### 16. Dockerfile이 admin/, user/ 분리 복사

```dockerfile
COPY user ./user
COPY admin ./admin
```

통합 후 불필요 (admin/, user/는 app.py가 참조하는 서브모듈일 뿐).

---

## 추천 액션 (우선순위순)

| # | 액션 | 절약 | 난이도 |
|---|------|------|--------|
| 1 | `/chat` + `/chat/stream` 파이프라인 통합 | 중복 200줄 + 버그 6개 해결 | 중 |
| 2 | docker-compose.prod.yml → 통합 app.py 반영 | 서비스 4→3개 | 하 |
| 3 | 데드코드 삭제 (tier_monitor + feature_flags + 미사용 함수) | 556줄 | 하 |
| 4 | 배치 스크립트 구버전 참조 수정 (2파일) | 버그 해결 | 하 |
| 5 | Pydantic 스키마 통합 | 150줄 이관 | 중 |
| 6 | Dockerfile → app.py 기반으로 단순화 | 의존성 정리 | 하 |
| 7 | __pycache__ 정리 + requirements-mentoring.txt 삭제 | 정리 | 하 |
