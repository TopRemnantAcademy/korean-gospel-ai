# 코드베이스 체계적 검토 프레임워크 (korean-gospel-ai)

> 본 문서는 프로젝트를 **10개 파트**로 분할하여, 각 파트를 매우 디테일하게 식별·검토할 수 있도록
> 구성한 검토 표준(Rubric)이다. 각 파트는 **핵심 검토항목 → 예상 문제유형 → 검토기준/체크리스트 →
> 우선순위 분류**로 구조화되어 있다. 마지막 장에서는 파트 간 의존성과 연관 문제를 다룬다.
>
> 작성일: 2026-07-15. 대상: `korean-gospel-ai` (FastAPI 백엔드 + Streamlit 관리자 + 모바일 PWA + Qdrant).
> **파트 1(API 레이어)**는 본 문서 작성과 동시에 실제 코드에 대하여 검토·수정 실행 완료(Part 1 절 참조).

---

## 🔟 파트 구성 개요 (목차)

| # | 파트 | 주요 디렉터리 / 모듈 | 중점 |
|---|------|----------------------|------|
| 1 | **API 레이어** | `backend/app/api/*`, `main.py`, `middleware/*` | 라우팅·인증·입력검증·예외·미들웨어 |
| 2 | 서비스 레이어 | `backend/app/services/*` (파이프라인·정책·안전) | 비즈니스 로직·상태·동시성 |
| 3 | 데이터베이스 / 영속성 | `backend/app/db.py`, `models/orm.py` | 세션·트랜잭션·ORM·스키마 일치 |
| 4 | 벡터 스토어 / 검색 / RAG | `services/enhanced_rag/*`, `retriever.py`, `bm25.py`, `sparse_index.py` | 하이브리드 검색·임베딩·인덱스 |
| 5 | LLM / AI 통합 | `services/llm/*`, `prompts/*`, `salvation_*` | 프로바이더 추상화·프롬프트·토큰 |
| 6 | 프론트엔드 (모바일 PWA) | `mobile/*` (vanilla JS, SW, 상태) | 렌더링·상태·오프라인·보안 |
| 7 | 관리자 대시보드 (Streamlit) | `admin/*` | 페이지·api_client·권한 |
| 8 | 인증 / 보안 | `api/auth.py`, `api/enhanced_rag.require_admin`, CORS, 시크릿 | 토큰·암호화·노출 |
| 9 | 배포 / 인프라 / 설정 | `docker*`, `deploy.sh`, `.env`, `config.py` | 컨테이너·env·CORS 오리진·비밀 |
| 10 | 로깅 / 모니터링 / 테스트 | `middleware/error_monitor`, `logging_setup`, `tests/*` | 관측성·커버리지·회귀 |

> 우선순위 분류 기준(P0~P3)은 **모든 파트 공통**으로 마지막 장에 정의되어 있다.

---

## 📘 파트 1 — API 레이어 (상세 예시)

### 1.1 검토 범위
- `backend/app/main.py` — 앱 생성, 미들웨어 등록 순서, lifespan, 라우터 include
- `backend/app/api/*.py` — 16개 라우터 (chat, retrieval, admin, documents, memory, prompts, subscriber, auth, glossary, drafts, jobs, mobile, content_admin, media, bible, enhanced_rag)
- `backend/app/middleware/*.py` — `rate_limit.py`, `error_monitor.py`, `RequestIDMiddleware`(main.py 내)

### 1.2 핵심 검토 항목 (Key Review Items)
1. **엔드포인트 설계** — RESTful 일관성, 버전 관리, 중복/orphan 라우트, 누락 엔드포인트
2. **인증·인가** — 보호 필요 경로에 실제 guard 적용 여부, admin 키 비교 방식(타이밍 공격), 토큰 만료
3. **입력 검증** — Pydantic 스키마 경계, 신뢰경계(Query/Header/Body) 검증, 타입·범위 클램프
4. **예외 처리** — 누락된 try/except, 내부 예외 문자열 외부 노출 여부, 4xx/5xx 매핑
5. **응답 형식 일관성** — `response_model`, 에러 바디 스키마, 스트리밍 응답 종료 처리
6. **미들웨어** — 등록 순서, 단기 상태(딕셔너리)의 동시성 안전성, 백그라운드 태스크 GC 안전성
7. **동시성 / 리소스** — `asyncio.create_task` 참조 보관, DB 세션 누수, 외부 클라이언트 락 경합
8. **CORS / 보안 헤더** — 오리진 allowlist, credential 노출, Rate-Limit 헤더 부재

### 1.3 예상 문제 유형 (Expected Problem Types)
| 유형 | 예시 |
|------|------|
| **논리적 오류** | rate-limit 경로를 `/chat`만 적용해 `/auth` 무방비, warmup 태스크가 lifespan과 경합 |
| **보안 취약점** | `!=` 평문 키 비교(타이밍 공격), 예외 메시지에 호스트/SQL 노출, 인증 우회 기본키 |
| **성능 병목** | 동기 I/O를 이벤트 루프에서 블로킹, N+1 쿼리, 매 요청 DB 상태 조회 |
| **예외 처리 누락** | 빈 `except: pass`, 미들웨어 내 미보호 분기 |
| **코드 품질** | 미사용 import, magic number, route doc-string과 실제 엔드포인트 불일치 |
| **동시성 결함** | 딕셔너리 순회 중 변경(`RuntimeError`), unreferenced task GC, embedded client 다중 루프 접근 |

### 1.4 검토 기준 & 체크리스트 (Checklist)
- [ ] 모든 보호 경로가 인가 의존성(`check_admin`/`get_current_user`)으로 감싸져 있는가?
- [ ] admin 키 비교는 `hmac.compare_digest`인가? (평문 `==`/`!=` 금지)
- [ ] 기본 키(`change-me`) 사용 시 쓰기 엔드포인트가 거부(503)되는가?
- [ ] Pydantic 스키마가 모든 신뢰경계 입력을 검증(길이/범위/타입)하는가?
- [ ] `limit`/`offset` 등 페이지 파라미터가 `min/max`로 클램프되는가?
- [ ] 예외 응답이 내부 정보(경로/호스트/SQL)를 누출하지 않는가? (`_safe_err` 패턴)
- [ ] 빈 `except: pass`가 없는가?(로깅은 남기는가?)
- [ ] 미들웨어 순서가 올바른가? (RequestID → ErrorMonitor → RateLimit → CORS)
- [ ] 공유 딕셔너리/리스트 순회 중 변경이 없는가? (iterate over `list(d.keys())`)
- [ ] `asyncio.create_task` 결과가 참조로 보관(`_bg_tasks` + `add_done_callback`)되는가?
- [ ] Rate-Limit이 무차별 공격 표면(로그인/회원가입)을 포함하는가?
- [ ] Rate-Limit 응답에 `Retry-After`, 정상 응답에 `X-RateLimit-*` 헤더가 있는가?
- [ ] CORS `allow_origins`가 명시적 allowlist인가?(`*`)와 `allow_credentials=True` 병용 금지)
- [ ] 스트리밍 응답이 정상/예외 모두 종료(generator close)되는가?

### 1.5 우선순위 분류 (본 파트 적용 예)
| ID | 발견 | 유형 | 우선순위 | 처리 |
|----|------|------|----------|------|
| P1-1 | `rate_limit._global_cleanup()`가 `_buckets`/`_blocked_ips` 순회 중 삭제 → 동시성 Crash | 동시성 결함 | **P1(중요)** | 수정 완료 |
| P1-2 | `main.py` warmup `asyncio.create_task` 미보관 + lifespan 경합(embedded Qdrant) | 리소스/경합 | **P1(중요)** | 수정 완료 |
| P1-3 | Rate-Limit이 `/chat`만 → `/auth` 무방비(brute-force) | 보안 | **P2(중요)** | 수정 완료 |
| P1-4 | Rate-Limit 응답에 `Retry-After`/잔여 헤더 부재 | 보안/UX | **P3(개선)** | 수정 완료 |
| — | auth.py(상수시간비교/aud검증), admin.py(timezone-aware/ `_safe_err`) | — | 이미 양호 | 유지 |

---

## 📗 파트 2 — 서비스 레이어
**범위**: `services/chat_pipeline.py`, `policy.py`, `safety_service.py`, `flattery_filter.py`, `regen.py`, `onboarding_service.py`, `memory_service.py`, `subscriber_service.py`, `token_service.py`, `push_service.py`, `dedup_service.py`, `faq_cache.py`.
- **항목**: 함수형 순수성/사이드이펙트, 캐시 일관성(LRU/TTL), 백그라운드 작업 추적, 예외 전파边界, 동시성(락/이벤트루프), 의존성 주입.
- **예상 문제**: `_profile_cache` 무한증가(메모리), unreferenced task GC, `any()` O(n) → set O(1), 데드 스텁(`grant_signup_bonus_sync` 미구현), 비효율 알고리즘.
- **체크리스트**: [ ] 캐시에 max/TTL/eviction 있는가? [ ] 모든 `create_task`가 보관되는가? [ ] 데드 스텁 없는가? [ ] 동기 I/O는 `to_thread`인가? [ ] 예외가 호출자에게 의미있게 전파되는가?

## 📗 파트 3 — 데이터베이스 / 영속성
**범위**: `db.py`, `models/orm.py`, `models/schemas.py`, 세션 컨텍스트매니저.
- **항목**: 세션 누수(close 누락), DetachedInstanceError, 마이그레이션 불일치, N+1, 인덱스, 트랜잭션 경계, 타입 매핑.
- **예상 문제**: `.query()` 결과 지연로드 세션 종료 후 접근, 자동 ALTER TABLE 마이그레이션의 위험(`DROP` 없음·타입 강제), `session.commit()` 누락.
- **체크리스트**: [ ] 모든 세션이 컨텍스트매니저로 닫히는가? [ ] 지연로드 속성은 세션 내에서 로드되는가(`_version_id` 패턴)? [ ] 마이그레이션이 ORM↔DB 불일치를 자동보정하는가(주의 필요)? [ ] FK/인덱스 누락 없는가?

## 📗 파트 4 — 벡터 스토어 / 검색 / RAG
**범위**: `services/enhanced_rag/*`, `retriever.py`, `bm25.py`, `sparse_index.py`, `search_v4.py`, `search_optimizer.py`.
- **항목**: hybrid fusion(RRF) 계산, dense/sparse 가중치, 청킹, 임베딩 차원 일치(1024), 인덱스 영속성, reranker.
- **예상 문제**: TF 계산 O(n)(`list.count`→`Counter`), list 기반 삭제 O(n)(`dict`로), 정렬 기반 캐시 eviction O(n log n)(`OrderedDict`), embedded client 다중 프로세스 락.
- **체크리스트**: [ ] 검색 지연시간 측정됨? [ ] 인덱스 add/remove가 O(1)? [ ] 청크 경계가 문장 단위? [ ] 차원 불일치 런타임 검증?

## 📗 파트 5 — LLM / AI 통합
**범위**: `services/llm/*`(base, factory, tencent, fallback), `prompts/system.py`, `salvation_prompt_wrapper.py`, `salvation_detector.py`, `spiritual_correction.py`.
- **항목**: 프로바이더 추상화 일관성, 스트리밍/논스트리밍 경로 동일성, 토큰 추정 공식 일치, 프롬프트 언어 분기(ko/en/zh/ja), fallback 체인.
- **예상 문제**: 토큰 추정 계수 불일치(0.55 vs 0.5), reasoning 모델 응답 필드(`reasoning_content`) 처리, 자식 프로세스 멀티프로세싱 누수.
- **체크리스트**: [ ] 동기/비동기 토큰 추정 공식 단일화? [ ] 프로바이더별 응답 파싱 분기 완결? [ ] 프롬프트 언어별 시스템 메시지 존재? [ ] timeout/재시도 설정?

## 📗 파트 6 — 프론트엔드 (모바일 PWA)
**범위**: `mobile/*.js`(app, screens, components, services, utils, sw).
- **항목**: 렌더링/상태 동기화, 이벤트 위임, 오프라인 캐시(SW), localStorage 파싱 안전성, 더미 로그인 노출, null 가드.
- **예상 문제**: 이중 렌더(API 2중호출), `JSON.parse` 크래시, 더미 로그인 프로덕션 노출, `verses[0].v` NPE, SW 중복 fetch 분기.
- **체크리스트**: [ ] 모든 외부 입력에 null 가드? [ ] localStorage 파싱이 try/catch? [ ] 더미 로그인 localhost 전용? [ ] SW 캐시 무효화 전략?

## 📗 파트 7 — 관리자 대시보드 (Streamlit)
**범위**: `admin/app.py`, `admin/pages/*`, `admin/lib/api_client.py`.
- **항목**: api_client 래퍼 누락(ImportError), 페이지별 권한, 입력 검증, long-poll/세션 상태, deprecated API 호출.
- **예상 문제**: `list_subscribers` 누락 → 페이지 ImportError, 버튼 key 충돌, 세션_state 직렬화 크기.
- **체크리스트**: [ ] 모든 호출이 api_client 경유? [ ] 페이지가 백엔드 스키마와 동기화? [ ] 위험 작업 확인 단계?

## 📗 파트 8 — 인증 / 보안
**범위**: `api/auth.py`, `api/enhanced_rag.require_admin`, `config` 시크릿, CORS, `.auth_secret` 파일.
- **항목**: 토큰 서명(HMAC), 만료, salt(scrypt), 비밀번호 강도, OAuth aud 검증, 시크릿 로테이션 영향.
- **예상 문제**: 상수시간비교 누락, 토큰 만료 없음, legacy SHA 해시 잔존, 시크릿 미설정 경고만, CORS `*`+credential.
- **체크리스트**: [ ] 모든 시크릿 비교 상수시간? [ ] 토큰 만료 존재? [ ] OAuth aud/clock 검증? [ ] 기본 키 거부? [ ] CORS 안전?

## 📗 파트 9 — 배포 / 인프라 / 설정
**범위**: `Dockerfile*`, `docker-compose*.yml`, `deploy.sh`, `.env`, `config.py`, `pyproject/requirements`.
- **항목**: 컨테이너 헬스프로브, env 검증, CORS 오리진, 비밀 주입, 포트/볼륨, PWA 호스팅(`:4174`).
- **예상 문제**: embedded Qdrant 다중 컨테이너 락, `.env` 누락 시 기본키, CORS 오리진에 모바일 URL 포함 여부, requirements 고정 버전.
- **체크리스트**: [ ] 헬스프로브 경로 존재? [ ] env 검증/기본값 안전? [ ] 비밀 외부 주입? [ ] 동시 프로세스 락 정책? [ ] 포트 충돌 없음?

## 📗 파트 10 — 로깅 / 모니터링 / 테스트
**범위**: `middleware/error_monitor.py`, `logging_setup.py`, `tests/*`, `services/tracing.py`.
- **항목**: 구조화 로깅, 에러 수집, 슬로우 리퀘스트, 알림, 테스트 커버리지, 회귀.
- **예상 문제**: 민감정보 로그 노출, 테스트 부재, 에러로그 DB 기록 실패 무시, tracing 누락.
- **체크리스트**: [ ] 로그에 시크릿/토큰 없음? [ ] 에러 수집 동작? [ ] 단위/통합 테스트 존재? [ ] CI에서 정적분석(pyflakes/compileall) 실행?

---

## 🔗 파트 간 의존성 & 연관 문제 (Cross-Part)

```
         ┌─────────────┐
         │  9 배포/설정 │──env, CORS, 시크릿, 컨테이너
         └──────┬──────┘
                │ settings
      ┌─────────┼──────────┐
      ▼         ▼          ▼
 ┌────────┐ ┌────────┐ ┌──────────┐
 │ 1 API  │◄│ 8 인증 │ │ 3 DB     │
 └───┬────┘ └────────┘ └────┬─────┘
     │ 호출                  │ ORM
     ▼                      ▼
 ┌────────┐         ┌──────────────┐
 │ 2 서비스├────────►│ 4 벡터/RAG   │
 └───┬────┘         └──────┬───────┘
     │                     │ 임베딩
     ▼                     ▼
 ┌────────┐         ┌──────────────┐
 │ 5 LLM  │         │ 10 로깅/테스트│
 └────────┘         └──────────────┘
      ▲                      ▲
      │                      │
 ┌────────┐         ┌──────────────┐
 │ 6 모바일├─────────┤ 7 관리자     │
 └────────┘  API 호출 └──────────────┘
```

### 연관 문제 매트릭스 (한 곳 수정 시 함께 봐야 할 파트)
| 트리거 변경 | 영향 파트 | 연관 검토 포인트 |
|------------|----------|------------------|
| `config.py` 설정 추가/변경 | 1,2,8,9 | env 검증, 기본값 안전성, CORS, 시크릿 로딩 |
| 인증 토큰 스키마 변경 | 1,6,7,8 | 헤더 파싱, 모바일 저장, 관리자 호출 |
| DB 모델 컬럼 추가 | 1,3,7 | 자동 마이그레이션, 관리자 페이지, 스키마 일치 |
| RAG 검색 파라미터 변경 | 1,2,4,5 | API 응답 스키마, 서비스 호출, 프롬프트 컨텍스트 |
| CORS 오리진 변경 | 1,6,9 | 모바일 도메인, 배포 호스트, credential 정책 |
| 에러 응답 바디 변경 | 6,7,10 | 프론트 파싱, 관리자 표시, 로깅 포맷 |

### 공통 우선순위 분류 기준 (P0~P3, 전 파트 적용)
- **P0 (긴급/차단)**: 인증 우회, 비밀노출, RCE/인젝션, 데이터 유실, 크래시(모든 요청). 즉시 수정.
- **P1 (중요)**: 특정 경로 크래시, 동시성 결함( Race/Crash), 보안 표면(brute-force), 리소스 누수. 이번 스프린트.
- **P2 (중요)**: 신뢰성/정확성(로직 오류, 잘못된 계산), 성능 병목, 누락된 예외 처리. 계획적 수정.
- **P3 (개선)**: 가독성, 미사용 코드, 매직넘버, 네이밍, 헤더/UX. 리팩터링 단계.

### 권장 검토 절차 (Runbook)
1. **정적 스캔**: `pyflakes`(undefined/redef), `compileall`, `node --check`(JS) → F821/재정의 0 목표.
2. **런타임 임포트**: `from backend.app.main import app` 실제 임포트(순환import·import-time 오류 검출).
3. **파트별 체크리스트**: 위 1~10 파트 순회, 발견 즉시 우선순위 태깅.
4. **의존성 교차검증**: 매트릭스 따라 영향 파트 재점검.
5. **수정 & 재검증**: 수정 후 동일 정적/런타임 검증 + 메모리 로그 기록.

---

## ✅ 파트 1 실행 결과 (본 문서와 함께 수정 적용)

| ID | 문제 | 파일 | 수정 |
|----|------|------|------|
| P1-1 | `_global_cleanup()`가 `_buckets`/`_blocked_ips` 순회 중 딕셔너리 변경 → 동시성 Crash | `middleware/rate_limit.py` | 순회 대상 key를 `list()`로 복사 후 삭제 |
| P1-2 | warmup `asyncio.create_task` 미보관 + lifespan 경합(embedded Qdrant 락) | `main.py` | `_bg_tasks` set + `add_done_callback`로 GC 방지 패턴 적용 |
| P1-3 | Rate-Limit이 `/chat`만 → `/auth` 무방비 | `middleware/rate_limit.py` | 보호 경로를 `/chat`,`/auth`,`/admin`(health 제외)로 확장 |
| P1-4 | Rate-Limit 응답에 `Retry-After`/잔여 헤더 부재 | `middleware/rate_limit.py` | 429에 `Retry-After`, 정상 응답에 `X-RateLimit-Limit`/`Remaining` 추가 |

검증: `compileall backend/app` exit 0, `from backend.app.main import app` 라우트 113개 로드 성공.
(상세 diff/설명은 본 대화의 파트1 수정 내역 및 `.workbuddy/memory/2026-07-15.md` 참조)

---

## ✅ 파트 2 실행 결과 (서비스 레이어)

파트2 체크리스트(캐시 max/TTL/eviction, create_task 보관, 데드 스텁, 동기 I/O to_thread, 예외 전파) 적용. 핵심 서비스 12개 전수 검토.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `token_service.py` | **수정** | `tokens_bonus` 미설정(노출 필드 항상 0) → 보너스 지급 시 갱신 |
| `publish_service.py` | **수정** | BM25 sparse 인덱스 갱신 실패를 `except: pass`로 침묵(검색 정확도 저하) → 로깅 |
| `subscriber_service.py` | 양호 | N10 화이트리스트, dict 반환(DetachedInstanceError 방지), IntegrityError 재시도 |
| `job_service.py` | 양호 | 세션별 즉시 커밋, 딕셔너리 반환, stale job 자동 실패 처리 |
| `dedup_service.py` | 양호 | `seen_docs`/`seen_doc_ids` set O(1), SQL LIKE 사전필터 |
| `faq_cache.py` | 양호 | RLock 스레드안전, TTL eviction, regex 정규화, hit 승격 |
| `policy.py` | 양호 | mtime 기반 룰 캐시, fallback judge, regex 오류 처리 |
| `safety_service.py` | 양호 | 하드블록/트리거/율법주의 패턴, safety 리소스 append |
| `memory_service.py` | 양호 | LIKE 이스케이프, 시간순 컨텍스트, 피드백 검증 |
| `chat_pipeline.py` | 양호 | `_profile_cache` TTL+max500+LRU, `_spawn_bg_task` GC-safe |
| `regen.py` | 양호 | 1회 재생성 제한, fail-open + 로깅 |
| `greeting_service.py` | 양호 | fail-open, parse 실패 None 반환, debug 로깅 |
| `onboarding_service.py` | 양호 | step gating, condition/filled 스킵 로직 일관 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P2-1 | `publish_service` BM25 sparse 인덱스 갱신 실패를 `except: pass` 침묵(2개소) → 하이브리드 검색 정확도 silently 저하 | 예외 처리 누락(데이터 정합성) | **P1(중요)** | `logger.warning(...exc_info=True)` 로 변경 (검색 정확도 영향 가시화) |
| P2-2 | `publish_service` 용어 자동추출 실패 `except: pass`(2개소) | 예외 처리 누락 | **P2(중요)** | `logger.warning` 로 변경 |
| P2-3 | `token_service.grant_signup_bonus_sync` 가 `tokens_bonus` 를 절대 갱신하지 않음 → `get_quota_status` 의 `bonus` 가 항상 0 | 불완전한 구현/데이터 불일치 | **P3(개선)** | 보너스 지급 시 `sub.tokens_bonus += bonus` 갱신 |

### 검토 중 확인된 "아님" 판정 (오탐 방지)
- `token_service` quota 차감 미커밋 의심 → `get_session_immediate()` 가 컨텍스트 종료 시 자동 커밋(db.py L104)이므로 정상. 버그 아님.
- 서비스 레이어 `asyncio.create_task` 미보관 → 전부 `_spawn_bg_task` 헬퍼로 교체 완료(파트1 이전 작업). 잔여 없음.
- `dedup_service` L75 `any(...)` → 이미 `seen_docs` set 으로 O(1) 스킵, 중복 로직일 뿐 버그 아님.

### 검증
- `compileall backend/app` exit 0. `pyflakes` 수정 파일 undefined-name 0.
- `from backend.app.main import app` → 라우트 113개 로드 성공.
- `tokens_bonus` 가 `models/orm.py` 실제 컬럼(Integer, default=0) 확인 → 타입 일치.

---

## ✅ 파트 3 실행 결과 (DB·영속성 레이어)

파트3 체크리스트(세션 관리·트랜잭션·커넥션 풀·N+1/전체스캔·DetachedInstanceError·인덱스·마이그레이션 정합성) 적용. 대상: `db.py`, `models/orm.py`, `scripts/migrate_db.py`, `scripts/init_db.py`, `get_effective_body` 호출 경로.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `db.py` | 양호 | `pool_pre_ping=True`, `future=True`, 세션 컨텍스트 자동커밋, SQLite WAL 적용 |
| `models/orm.py` | **수정** | `Subscriber.salvation_status` 에 `index=True` 누락 → 분석 쿼리 풀스캔 |
| `scripts/migrate_db.py` | **수정** | 신규 NOT NULL 컬럼에 항상 `DEFAULT ''` → 숫자/불린 컬럼 데이터 오염 + 인덱스 미생성 |
| `services/document_service.py` (`get_effective_body`) | **수정** | detached 세션에서 `version.artifact` 접근 시 `DetachedInstanceError` 가능 |
| `api/subscriber.py` (`spiritual_stats`) | **수정** | `Subscriber` 전체 `.all()` 로드 후 Python 집계 → 전체 테이블 스캔/메모리 폭발 |
| `api/subscriber.py` (stagnant/darakbang_matrix) | 양호 | 필터 적용(`.filter()`), 행 상세 필요량만 로드 |
| `scripts/init_db.py` | 양호 | `Base.metadata.create_all` + `.db` 존재 시 스킵 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P3-1 | `get_effective_body` 가 detached 세션에서 `version.artifact` (lazy 관계)에 접근 → `DetachedInstanceError` 크래시 가능 | 예외 처리 누락(안정성) | **P1(중요)** | `session` 인자 추가 + `inspect(version).session` 폴백 → `session.get(SourceArtifact, artifact_id)` 로 명시 조회(항상 로드 보장). 미로드 시 안전 폴백 |
| P3-2 | `Subscriber.salvation_status` 에 인덱스 없음 → 분석 `GROUP BY`/`COUNT`/필터가 풀 테이블 스캔 | 성능(인덱스 누락) | **P2(중요)** | `index=True` 추가 (마이그레이션이 자동 인덱스 생성하므로 운영 DB에도 즉시 반영) |
| P3-3 | `migrate_db.py` 신규 NOT NULL 컬럼에 무조건 `DEFAULT ''` → 정수/불린 컬럼에 빈 문자열 삽입(데이터 오염) + `index=True` 컬럼의 인덱스 생성 누락 | 데이터 정합성 / 마이그레이션 불완전 | **P1(중요)** | `_default_literal(col_type)` 추가(타입별 `0`/`0.0`/`'1970-...'`/`''`) + 기존 테이블 누락 인덱스 `CREATE INDEX IF NOT EXISTS` 루프 추가 |
| P3-4 | `spiritual_stats` 가 `s.query(Subscriber).all()` 로 전체 구독자 로드 후 Python 집계 | 성능(N+1/전체스캔) | **P2(중요)** | SQL 집계로 교체: `func.count` + `group_by(salvation_status)`, `darakbang_verified`/`assume_saved_count` 는 `filter().count()` 로 치환 |

### 검토 중 확인된 "아님" 판정 (오탐 방지)
- `source_service.ingest_file` 중복 해시 → `content_hash` UNIQUE 위반 시 graceful 처리 확인(업로드 중복은 안전). 별도 수정 불필요.
- `token_service` quota 차감 미커밋 → `get_session_immediate()` 자동커밋(db.py)으로 정상(파트2에서 이미 확인).
- `publish_version` 내 `get_effective_body(version, session=session)` — 열린 세션 전달로 P3-1 폴백 경로 비활성화(가장 빠른 경로).
- `init_db.py` 는 `create_all` 만 수행, 인덱스는 `migrate_db.py` 가 보완 → 역할 분담 정상.

### 검증
- `compileall backend/app` exit 0. `pyflakes` 수정 파일 undefined-name 0.
- `from backend.app.main import app` → 라우트 113개 로드 성공.
- `spiritual_stats` 집계 로직: 기존 Python 집계와 동일한 `{status: count}` + 총계 반환(동작 동치성 유지).

---

## ✅ 파트 4 실행 결과 (벡터 스토어 / 검색 / RAG)

파트4 체크리스트(RRF 융합, dense/sparse 가중치, 청킹, 임베딩 차원 일치, 인덱스 영속성, reranker, embedded 락) 적용. 대상: `services/enhanced_rag/*`, `services/retriever.py`, `services/bm25.py`, `services/sparse_index.py`, `services/search_v4.py`, `services/search_optimizer.py`.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `enhanced_rag/retrieval.py` | **수정** | `dense_primary + dense_source` 를 하나의 랭킹으로 연결 → bilingual 한국어 검색 rank-inflation. 쿼리 벡터 미`.tolist()` |
| `services/retriever.py` | 양호 | 다중쿼리 RRF 를 서브검색별 **독립 랭킹**으로 유지(no rank inflation), OrderedDict LRU, 프로필 캐시키 |
| `services/vector_store.py` (`QdrantStore`) | 양호 | 지수백오프 재시도, embedded 싱글톤 락, payload-schema 폴백, 동적 ef_search |
| `enhanced_rag/vector_store.py` | 양호 | manifest 영속, RLock, dual-storage 증분 갱신 |
| `enhanced_rag/reranker.py` | 양호 | 가중치 합 1.0(0.5/0.3/0.2), MMR λ=0.7, LLM/cross_encoder → heuristic 폴백 |
| `enhanced_rag/bm25.py` | 양호 | `Counter` O(1) TF (이전 세션 최적화 유지) |
| `services/sparse_index.py` | 양호 | dict O(1) add/remove (이전 세션 유지) |
| `services/retriever.py` (LRU) | 양호 | `OrderedDict` O(1) eviction (이전 세션 유지) |
| `enhanced_rag/chunking.py` | 양호 | recursive = 검증된 한국어 청킹 재사용, fixed/semantic 경계 정상 |
| `services/search_v4.py` | 양호 | `services/retriever` 에 정확히 바인딩(rerank_top_n/profile 수용), MMR/압축/신뢰도 스코어러 정상 |
| `services/search_optimizer.py` | 양호 | 쿼리타입→동적 가중치, 확장쿼리, dead `q_len` 이미 제거 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P4-1 | `enhanced_rag/retrieval.py` 가 `dense_res = dense_primary + dense_source` 를 **하나의 랭킹**으로 RRF 처리 → 한국어 쿼리의 `dense_source`(원문 벡터) 매치가 rank≈recall_k(40) 로 밀려 bilingual 검색 무력화 (cross-stream rank inflation) | 검색 정확도(논리오류) | **P1(중요)** | 3개 독립 스트림(`dense_primary`/`dense_source`/`keyword`)으로 RRF 융합하도록 `_rrf_fusion` → `_rrf_fusion_streams(streams, k)` 리팩터. 각 스트림 rank 0 부터 독립 취급 |
| P4-2 | `enhanced_rag/retrieval.py` 가 쿼리 임베딩(numpy)을 `.tolist()` 없이 `search_dense` 에 전달 → `np.float32` 스칼라가 쿼리 벡터로 들어감(`services/retriever.py` L282는 `.tolist()` 사용 중) | 타입 안정성/일관성 | **P3(개선)** | `np.asarray(vec, dtype=float).ravel().tolist()` 로 native float list 변환(주/원문 벡터 모두) |

### 검토 중 확인된 "아님" 판정 (오탐 방지)
- `search_v4.AdvancedSearchEngine` 가 `retrieve(..., rerank_top_n=, profile=)` 호출 → `enhanced_rag` `HybridRetriever` 가 아닌 `services/retriever.py` `HybridRetriever`(해당 kwarg 수용)에 바인딩 → TypeError 아님. 정상.
- `collections.collection` 차원 불일치: 컬렉션 생성 시 `dim=embedder.dim` 을 동일 임베더에서 파생 → 불일치 불가. 별도 런타임 검증 불필요.
- `bm25`/`sparse_index`/`retriever LRU`: 이전 세션 최적화(Counter/dict/OrderedDict) 그대로 유지 → 중복 수정 불필요.
- `enhanced_rag/reranker` 가중치 0.5+0.3+0.2=1.0, MMR λ=0.7 정상 → 조정 불필요.

### 검증
- `compileall backend/app` exit 0. `pyflakes` 수정 파일 undefined-name 0.
- `from backend.app.main import app` → 라우트 113개 로드 성공.
- 기능 테스트(`_rrf_fusion_streams`): recall_k=40 시나리오에서 한국어 정답이 **rank 41 → rank 2** 로 부상, RRF +1.7× (cross-stream rank inflation 해소 확인).

---

## ✅ 파트 5 실행 결과 (LLM·AI 통합 레이어)

대상: `services/llm/base.py`, `tencent.py`, `deepseek.py`, `openai.py`, `fallback.py`, `api/chat_pipeline.py`, `prompts/*`, `services/spiritual_correction.py`, `salvation_prompt_wrapper.py`.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `services/llm/base.py` | **수정** | reasoning-content 추출 헬퍼 중앙화 |
| `services/llm/tencent.py` | **수정** | reasoning_content 폴백 + `Optional[float]` 타입 힌트 |
| `services/llm/deepseek.py` | **수정** | `text_from_message`/`text_from_delta` 사용 |
| `services/llm/openai.py` | **수정** | `text_from_message` 사용 |
| `services/llm/fallback.py` | **수정** | 스트림 폴백 시 abandoned generator 누수 차단 |
| `api/chat_pipeline.py` | **수정** | `_estimate_tokens` → `chunker.estimate_tokens` 위임(단일 소스) |
| `prompts/system.py` | 양호 | 3개 언어+ja 프롬프트, `_safe_target_lang` 폴백 |
| `salvation_prompt_wrapper.py` | 양호 | 4-layer 인젝션 방어 |
| `spiritual_correction.py` | 양호 | `SpiritualError` 4값 ↔ 교정블록 1:1 매핑 일치 |
| `gemini.py`/`claude.py`/`ollama.py` | 양호 | 비 OpenAI → reasoning_content 문제 없음 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P5-1 | DeepSeek-V4(OpenAI 호환 reasoning 모델)가 답을 `reasoning_content` 에 담음 → `choice.message.content` 가 비어 응답 공백 | 버그(정확도) | **P1** | `base.py` 에 `text_from_message()`/`text_from_delta()` 헬퍼 추가, 모든 chat/stream 경로에서 `content or reasoning_content` 폴백 |
| P5-2 | `fallback.py` 스트림 폴백 예외 시 이전 provider generator 를 닫지 않음 → 커넥션 누수 | 리소스 누수 | **P2** | `except` 에서 `agen.aclose()` (None 체크 후) 재전파 |
| P5-3 | `tencent.py` `timeout_sec: float = None` → None 은 float 가 아님(타입 위반) | 코드 품질 | **P3** | `Optional[float] = None` |
| P5-4 | `_estimate_tokens` 가 0.55 배율 하드코딩 vs chunker 0.5 → 토큰 예산 산정 불일치 | 논리 오류 | **P3** | `chunker.estimate_tokens(text)` 위임(단일 소스) |

### 검증
- `pyflakes` 수정 LLM 파일 undefined-name 0. `compileall backend/app` exit 0. `from backend.app.main import app` → 113 routes.

---

## ✅ 파트 6 실행 결과 (프론트엔드: 모바일 PWA)

대상: `mobile/utils/state.js`, `mobile/screens/index.js`, `mobile/services/index.js`, `mobile/sw.js`, `mobile/components/index.js`, `mobile/utils/dom.js`, `mobile/app.js`.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `mobile/utils/state.js` | **수정** | 세션 영속성(`gospel_token`/`gospel_sub_id`/`gospel_user`) |
| `mobile/screens/index.js` | **수정** | 채팅 `history` 중복 질문 버그(P6-12) + 로그인 null-guard |
| `mobile/services/index.js` | **수정** | MeditationService JSON 파싱 방어 |
| `mobile/sw.js` | **수정** | `?api=` 딥링크 오프라인 캐시(`ignoreSearch`) |
| `mobile/app.js`/`components/index.js`/`utils/dom.js` | 양호 | pub/sub `AppState`, `h()` DOM 헬퍼 정상 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P6-12 | 채팅 `sendMessage` 가 **이미 현재 질문이 포함된** `chatMessages` 를 `history` 로 전송 → 백엔드가 `history`+`query` 를 합쳐 **질문이 2번** 들어감(챗봇 자문자답/반복) | 버그(논리) | **P1** | `history` 를 현재 메시지 추가 **전** 스냅샷 복사 후 전송 |
| P6-3 | 새로고침 시 `isLoggedIn`/`user` 가 복원 안 됨 → 매번 로그인 유도 | 버그(UX) | **P2** | `isLoggedIn` = localStorage 토큰 존재 여부, `user` = `gospel_user` JSON 로드. login/logout 영속화 |
| P6-4 | `renderLogin` 이 `AppState.get('user')` undefined 시 `.name` 접근 → 크래시 | 버그(NPE) | **P3** | `const user = AppState.get('user') \|\| {}` |
| P6-5 | MeditationService `getDaily`/`getCards` 무방비 `.json()` → 오프라인/비정상 JSON 시 화면 크래시 | 견고성 | **P2** | try/catch → `{}`/`[]` 폴백 |
| P6-7 | SW fetch 가 정확한 URL 만 매칭 → `?api=` 쿼리 딥링크 오프라인 실패 | 버그(오프라인) | **P3** | `caches.match(e.request, {ignoreSearch:true})` |

### 검토 중 확인된 "아님" 판정
- 더미 Google 로그인은 `localhost`/`127.0.0.1` 에만 동작(dev-only) → 보안 노출 아님.
- `verses[0].v` 가드 존재, `renderVerse` 는 `passage.verses` 기본값 `[]` 사용 → 인덱스 오류 아님.

### 검증
- `node --check` 7개 JS 파일 전부 통과.

---

## ✅ 파트 7 실행 결과 (관리자 대시보드: Streamlit)

대상: `admin/lib/api_client.py`, `admin/pages/*`, `admin/lib/auth.py`, `admin/lib/ui_components.py`.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `admin/lib/api_client.py` | **수정** | 24개 함수 예외 범위 확대(P7-1) |
| `admin/pages/11_🎵_미디어업로드.py` | **수정** | 삭제 확인 체크박스(P7-2) |
| `admin/pages/13_📖_성경관리.py` | **수정** | 삭제 확인 체크박스 |
| `admin/pages/5_💭_대화기록.py` | **수정** | 삭제 확인 체크박스 |
| `admin/pages/1_📚_Library.py` | **수정** | 아카이브 확인 체크박스 |
| `admin/pages/16_🌿_영성훈련.py` | **수정** | 콘텐츠링크 삭제 확인 체크박스 |
| `admin/lib/auth.py`, `ui_components.py` | 양호 | `list_subscribers` 존재, `st.cache_data` 정상, 버튼 key 고유 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P7-1 | 24개 함수가 `except httpx.ConnectError` 만 잡음 → 타임아웃/HTTP/JSON 오류 시 페이지 전체 트레이스백 | 견고성 | **P2** | 모두 `except (httpx.HTTPError, ValueError)` 확장(`get_job`/`check_backend_health` 세분화 `TimeoutException` 핸들러 보존, `@safe_api_call` 33개 유지) |
| P7-2 | 삭제/아카이브 액션 확인 없이 즉시 실행 → 잘못된 클릭으로 데이터 유실 | 보안(실수) | **P2** | 확인 체크박스 + 비활성화 버튼 게이팅 |

### 검증
- `py_compile` 수정 admin 파일 전부 OK. `pyflakes admin/lib/api_client.py` exit 0.

---

## ✅ 파트 8 실행 결과 (인증 / 보안)

대상: `api/auth.py`, `api/admin.py`, `services/security/*`, `main.py`(CORS), `models/orm.py`(subscriber_id).

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `api/auth.py` | **수정** | Google OAuth `iss` 검증 추가(P8-3) |
| `api/admin.py` (`check_admin`) | 양호 | `hmac.compare_digest` + `change-me`→503, 토큰 30일 만료 |
| `main.py` (CORS) | 양호 | 명시적 origin allowlist + `allow_credentials=False` + 명시적 methods/headers |
| `models/orm.py` | 양호 | `subscriber_id` = UUID4(콜론 없음) → 토큰 `split(":")` 안전 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P8-3 | Google OAuth 가 `aud` 만 검증 → 발급자(`iss`) 위조 토큰 수용 가능 | 보안(취약) | **P1** | `iss` 가 `https://accounts.google.com` 또는 `accounts.google.com` 인지 추가 검증, 아니면 401 |

### 검토 중 확인된 "아님" 판정
- scrypt 해시 + 상수시간 비교(`compare_digest`) → 이미 정확. legacy SHA-256 은 로그인 시 업그레이드 경로 존재.
- 토큰 포맷 `sub_id:ts:sig` — `sub_id` 가 UUID(콜론 없음)라 `split(":")` 오분리 없음.
- `require_admin`(`enhanced_rag.py`) 도 `compare_digest` + `change-me` 가드 → 일관.

### 검증
- `py_compile` OK. (사전 존재 unused `datetime.datetime`/`datetime.timezone` import 는 본 수정과 무관)

---

## ✅ 파트 9 실행 결과 (배포 / 인프라 / 설정)

대상: `Dockerfile`, `docker-compose.prod.yml`, `deploy.sh`, `backend/app/db.py`, `backend/app/config.py`, `.env.example`, `requirements*.txt`, (신규) `Dockerfile.ui`, `requirements-ui.txt`.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `backend/app/db.py` | **수정** | `DB_PATH` env 오버라이드 → 컨테이너 재시작 후 DB 보존(P9-0) |
| `docker-compose.prod.yml` | **수정** | backend `DB_PATH=/app/gospel.db` 주입 + UI 서비스 빌드 이미지 전환(P9-0/P9-4) |
| `deploy.sh` | **수정** | 헬스체크 `PORT` 반영 + 요약 UI 포트 정정(P9-1/P9-2) |
| `Dockerfile` | **수정** | `COPY data ./data` 제거 + data 디렉토리 정렬(P9-3) |
| `Dockerfile.ui` (신규) | **추가** | UI 전용 최소 이미지(앱 소스만 복사) |
| `requirements-ui.txt` (신규) | **추가** | UI 핀 고정 의존성 |
| `backend/app/config.py` | 양호 | pydantic-settings 단일 소스, `.env` env_file 로컬만 |
| `.env.example` | 양호 | 로컬 embedded Qdrant 기본값 적절 |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P9-0 | **데이터 유실(치명)**: `db.py` 가 SQLite 를 `/app/.gospel.db`(컨테이너 내부)에 기록, compose 는 `./gospel.db:/app/gospel.db` 마운트 → 실제 DB 와 마운트 경로 불일치 → 컨테이너 재생성 시 구독자/대화기록 전부 유실 | 버그(데이터유실) | **P0** | `db.py` 가 `DB_PATH` env 존중(`ROOT/.gospel.db` 기본, Docker `/app/gospel.db`), compose backend 에 `DB_PATH=/app/gospel.db` 주입 → 마운트 경로 일치 |
| P9-1 | `deploy.sh` 헬스체크 `localhost:8000` 하드코딩 → `PORT` env 와 불일치 시 잘못된 포트 검사 | 버그(배포) | **P1** | `BACKEND_PORT="${PORT:-8000}"` 사용 |
| P9-2 | `deploy.sh` 요약 "Admin UI: http://localhost:8502" 로 표기(`8502` 미노출) → 운영자 혼선 | 문서(오류) | **P3** | `8501` 로 정정 + Admin `?admin` 진입 안내 |
| P9-3 | `Dockerfile` `COPY data ./data` 로 문서 이미지 베이크 → compose 볼륨(`./data`)에 가려지고 이미지 비대/문서 배포 | 성능/품질 | **P2** | `COPY data` 제거, data 디렉토리 `/app/data` 로 정렬 |
| P9-4 | UI 컨테이너 `./:/app` repo 전체 마운트(`.env`/DB/로그 노출) + 기동 시 `pip install`(비핀, 느림, 비재현) | 보안/신뢰성 | **P2** | `Dockerfile.ui` 로 `app.py`+`admin`+`user` 만 복사한 최소 이미지 빌드, `.env`/DB/로그 노출 제거, 의존성 핀 고정 |

### 검토 중 확인된 "아님" 판정
- compose 가 `QDRANT_URL=http://qdrant:6333`(서버 모드) 사용 → embedded 락 경합 없음(로컬 `.env` `local:` 은 dev 전용).
- `APP_PASSWORD`/`API_BASE` 만 UI 에 주입, 백엔드 시크릿은 UI 에 전달 안 함(마운트 제거로 강화).
- healthcheck `/health` 경로는 실제 존재(113 routes 내).

### 검증
- `py_compile` db.py OK. `pyflakes` 수정 파일 신규 warning 0(사전 존재 unused import 무관). `bash -n deploy.sh` OK. `yaml.safe_load` compose OK.

---

## ✅ 파트 10 실행 결과 (로깅 / 모니터링 / 테스트)

대상: `middleware/error_monitor.py`, `logging_setup.py`, `services/tracing.py`, `tests/*`, (신규) `.github/workflows/ci.yml`, `pytest.ini`, `tests/test_config.py`.

### 검토 대상 및 상태
| 파일 | 상태 | 비고 |
|------|------|------|
| `logging_setup.py` | **수정** | 시크릿 마스킹 필터 + 웹훅/데스크톱 알림 분기(P10-7/P10-5) |
| `middleware/error_monitor.py` | **수정** | DB 기록 전 `scrub_secrets` 적용 |
| `services/tracing.py` | 양호 | `observe` noop 폴백, `as_type` 보관 — 개선 제안만 |
| `tests/test_enhanced_rag.py` | 양호 | 청킹/BM25/RRF/지표/프롬프트/E2E 스모크 |
| `tests/test_addiction_care.py` | 양호 | 위기/중독유형/수치/가족/안전메시지/단계/구절 검증 |
| `.github/workflows/ci.yml` (신규) | **추가** | pyflakes 정적분석 + 경량 테스트 |
| `pytest.ini` (신규) | **추가** | pythonpath/testpaths 설정 |
| `tests/test_config.py` (신규) | **추가** | 설정/DB URL/시크릿 마스킹 스모크(4건 통과) |

### 식별·수정 내역
| ID | 문제 | 유형 | 우선순위 | 수정 |
|----|------|------|----------|------|
| P10-7 | 로그/에러/트레이스백에 API 키·토큰·DB 비밀번호가 그대로 기록될 수 있음(장애 시 스택트레이스에 시크릿 노출) | 보안(정보노출) | **P2** | `scrub_secrets()` + `RedactingFilter` 를 모든 핸들러에 부착, error_monitor DB 기록 전 마스킹 |
| P10-5 | `notify_critical` 이 `plyer`(Windows 데스크톱 전용)만 시도 → 컨테이너/서버에서 import 실패로 CRITICAL 알림 **항상 유실** | 신뢰성(모니터링 공백) | **P2** | `ALERT_WEBHOOK_URL`(백그라운드 POST) + Windows 에서만 plyer + 항상 errors.log 기록 3중 분기 |
| P10-8 | 테스트가 2개 파일뿐(auth/API/config/DB/error_monitor 무검증) + CI 부재 → 회귀 방지망 없음 | 테스트/품질 | **P2** | `ci.yml`(pyflakes + 경량 pytest), `pytest.ini`, `test_config.py` 추가 |
| P10-3 | error_monitor 가 에러마다 `asyncio.to_thread` + SQLite 단일 writer 기록 → 고에러량 시 스레드/락 경합 | 성능 | **P3** | (권고) 배치 기록 큐 — 본 세션 미적용(관찰) |
| P10-9 | `test_enhanced_rag.py` 가 전역 `settings.qdrant_url="memory:"` 복원 없이 변이 → pytest 공유 프로세스 테스트 오염 | 테스트 품질 | **P3** | (권고) fixture 에서 원복 — 본 세션 미적용 |

### 검토 중 확인된 "아님" 판정
- `AppErrorLog` 모델(`models/orm.py:379`) 존재 → error_monitor 기록 정상.
- `addiction_care.AddictionType.none`/`ADDICTION_COMFORT_VERSES["general"]` 존재 → 테스트 참조 유효.
- `tracing.observe` 는 `client=None` 이면 그대로 통과(no-op) → Langfuse 비활성 시 안전.

### 검증
- 신규 `test_config.py` 4건 전부 통과(`pytest tests/test_config.py`). `py_compile` 수정 파일 OK. `pyflakes` 수정 파일 신규 warning 0.
