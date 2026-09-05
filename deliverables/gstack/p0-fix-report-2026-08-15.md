# P0 블로커 14건 전수 수정 리포트 (Post-Fix Report)

**Date**: 2026-08-15
**Input**: `deliverables/gstack/pre-launch-check-full-inspection-2026-08-15.md` (14 P0 blockers)
**Process**: 전 항목 코드 레벨 더블 체크 → 14/14 실재 확인(오탐 0건) → 전부 수정 → 검증

---

## 검증 결과 요약

| 단계 | 결과 |
|------|------|
| 더블 체크 | 14/14 CONFIRMED — 오탐 없음, 전부 실재 버그 |
| 수정 | 14/14 완료 (백엔드 8건, Streamlit 3건, Admin 2건, 모바일 1건×3위치) |
| 문법 검사 | Python 7파일 py_compile/AST 통과, JS 3파일 node --check 통과 |
| 테스트 | **185 passed / 2 failed** — 2건은 기존 stale 테스트(M-10/M-11)로 수정 전과 동일, **회귀 0건** |
| 스모크 테스트 | 토큰 128비트 서명 검증, 웹훅 fail-closed(시크릿 있음=403 / 없음=503), 금액 검증 헬퍼 통과 |

---

## 수정 상세 (Root Cause → Resolution)

### P0-1 스트리밍 프롬프트 인젝션 — `backend/app/api/chat.py`
- **Root cause**: 비스트리밍 경로(392-398행)만 `sanitize_history()` 적용, 스트리밍 경로는 클라이언트 history를 그대로 `messages.extend()` → `{"role":"system"}` 주입으로 시스템 프롬프트 변조 가능.
- **Resolution**: 스트리밍 경로에도 동일한 `sanitize_history()` 적용. role 화이트리스트로 system 주입 차단.

### P0-2 웹훅 멱등성 부재 — `backend/app/api/payment.py`
- **Root cause**: `/webhook`이 `rec.status == "paid"` 재확인 없이 `_apply_subscription()` 호출 → PortOne 재시도 웹훅마다 구독 기간 이중 연장.
- **Resolution**: 웹훅 핸들러에 `if rec.status == "paid": return` 멱등성 가드 추가.

### P0-3 웹훅 서명 fail-open — `backend/app/api/payment.py`
- **Root cause**: `PORTONE_WEBHOOK_SECRET` 미설정 시 `_verify_webhook_signature()`가 silently return → 위조 웹훅 무제한 허용.
- **Resolution**: 미설정 시 503으로 거부(fail-closed) + 에러 로그. main.py 기동 경고 문구도 "거부됨"으로 갱신.

### P0-4 결제 금액 미검증 — `backend/app/api/payment.py`
- **Root cause**: `/complete`·`/webhook` 모두 결제 상태만 확인하고 금액 미비교 → 1원 결제로 프리미엄 구독 가능.
- **Resolution**: `_paid_amount()`(V2 `amount.total` + V1 호환 필드) + `_verify_paid_amount()` 헬퍼 추가. 양 경로에서 플랜 금액과 불일치 시 `status="amount_mismatch"` + 승급 거부.

### P0-5 AUTH_SECRET 약한 폴백 — `backend/app/api/auth.py`
- **Root cause**: `.auth_secret` 파일 생성 실패(OSError) 시 `admin_api_key + "_auth_secret"` 파생 → 유추 가능한 서명 키로 토큰 위조 가능.
- **Resolution**: 약한 파생 폴백 완전 제거. prod에서는 RuntimeError로 기동 거부, 그 외 환경은 휘발성 랜덤 시크릿(재시작 시 토큰 무효화 = 안전한 실패). main.py에 prod + AUTH_SECRET 미설정 시 기동 거부 추가.

### P0-6 빈 APP_PASSWORD 관리자 우회 — `app.py`
- **Root cause**: `APP_PASSWORD` 미설정 시 관리자 버튼 클릭만으로 `mode="admin"` + `auth_ok=True`.
- **Resolution**: 미설정 시 오류 메시지 표시 후 진입 거부(fail-closed). 현재 .env에는 비밀번호 설정되어 있으나 방어막 확보.

### P0-7 답변 캐시 사용자 간 누출 — `backend/app/api/chat.py`
- **Root cause**: 캐시 키가 `(정규화 질의 + 언어)`뿐 — `build_prompts()`가 사용자 프로필(구원 상태)·최근 3턴 메모리를 답변에 주입하므로 개인화 답변이 타 사용자에게 제공됨.
- **Resolution**: 조회(235행)·저장(629행) 양쪽 키에 `sub_id` 스코프 추가 → 사용자별 캐시 격리.

### P0-8 console 모드 가입 함정 — `backend/app/api/auth.py`
- **Root cause**: 메일이 발송되지 않는 console 모드에서도 가입이 `token=""` + `email_verification_required=True` 반환 → 사용자가 인증 없이는 로그인 불가(메일 영원히 안 옴).
- **Resolution**: `_email_verify_enforced()`가 False(console)면 가입 즉시 `email_verified=True` + 로그인 토큰 발급. SMTP 강제 모드는 기존대로 메일 인증 플로우 유지. main.py에 prod + EMAIL_MODE≠smtp 시 CRITICAL 로그 추가.

### P0-9 관리자 페이지 파일명 불일치 — `app.py`
- **Root cause**: `st.Page("admin/pages/9_👥_사람.py")` 참조 but 실제 파일은 `9_👥_유저관리.py` → :8501 admin 모드 전체 crash.
- **Resolution**: 올바른 파일명으로 수정 (title도 "유저 관리"로 갱신).

### P0-10 인사이트 API 경로 불일치 — `mobile/screens/index.js` + dist 2곳
- **Root cause**: 클라이언트가 `/trending/insight/{id}` 호출 but 백엔드 라우트는 `/insight/{id}` → 인기질문 통찰 패널 항상 404.
- **Resolution**: 소스 + `dist/web` + `dist/android` 3곳 모두 `/insight/{id}`로 수정 (dist는 비압축 카피라 직접 수정 — 재빌드 불필요).

### P0-11 bot_list() None crash — `admin/pages/4_📊_Status.py`
- **Root cause**: "정상만" 필터가 `bot_list()` 반환값(None 가능)을 가드 없이 반복 → 388행 `or []`는 리스트 컴프리헨션 이후라 늦음.
- **Resolution**: 컴프리헨션 내부에서 `(bot_list() or [])` 가드.

### P0-12 일괄 봇 작업 거짓 성공 — `admin/pages/4_📊_Status.py`
- **Root cause**: 3개 일괄 버튼(차단/해제/초기화)이 `bot_toggle_flag()` 반환값(None=실패) 무시하고 무조건 카운트+"✅ 완료" 표시.
- **Resolution**: 반환값 검증 후 성공/실패 분리 카운트. 실패 시 경고 표시(자동 rerun 안 함), 전부 성공 시에만 성공+rerun.

### P0-13 LLM usage 경쟁 상태 — `backend/app/services/llm/fallback.py`
- **Root cause**: `get_llm()`이 provider별 공유 싱글톤 반환 → 동시 스트림이 인스턴스 속성 `last_stream_usage`를 서로 덮어써 토큰 과금 귀속 오염.
- **Resolution**: `stream_with_fallback()`에서 `copy.copy(llm)` 요청별 shallow copy로 usage를 요청 스코프에 격리 (HTTP 클라이언트 등 무거운 리소스는 참조 공유 — 오버헤드 없음).

### P0-14 HMAC 서명 64비트 — `backend/app/api/auth.py`
- **Root cause**: 토큰 서명을 hex 16자(64비트)로 truncation — NIST 최소 128비트 미달.
- **Resolution**: `[:16]` → `[:32]`(128비트) — `_make_token`/`_verify_token` 양쪽. **기존 발급 토큰 전체 무효화(사용자 재로그인 필요 — 출시 전이므로 수용)**.

---

## 변경 파일 목록

| 파일 | 항목 |
|------|------|
| `backend/app/api/payment.py` | P0-2, P0-3, P0-4 |
| `backend/app/api/auth.py` | P0-5, P0-8, P0-14 |
| `backend/app/api/chat.py` | P0-1, P0-7 |
| `backend/app/main.py` | P0-5/P0-8 prod 강제 보강 |
| `backend/app/services/llm/fallback.py` | P0-13 |
| `app.py` | P0-6, P0-9 |
| `admin/pages/4_📊_Status.py` | P0-11, P0-12 |
| `mobile/screens/index.js` + `dist/web` + `dist/android` 동일 파일 | P0-10 |

---

## 잔여 항목 (P0 아님, 원 리포트 트리아지 유지)

- **P1 16건** (H-1~H-16): 금주 스프린트 권장 — 이메일 토큰 시크릿 폴백, XFF 스푸핑, 레거시 해시, 스트리밍 단절 정산 등
- **P2 18건 / P3 8건**: 백로그
- **stale 테스트 2건** (M-10 `test_config.py`, M-11 `test_no_silent_swallow.py`): 코드가 맞고 테스트가 오래됨 — 테스트 업데이트 필요
- **배포 전 확인**: `GOOGLE_CLIENT_ID`, `PORTONE_CHANNEL_KEY` 여전히 비어 있음 (503)

## 재감사 권고

원 리포트의 권고대로 P0 14건 해소 후 **출시 승인 전 재감사(re-audit) 필수**. 특히 결제 플로우(웹훅 멱등성+금액 검증)는 PortOne 샌드박스로 E2E 검증 권장.
