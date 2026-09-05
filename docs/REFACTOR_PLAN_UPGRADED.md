# korean-gospel-ai 리팩토링 기획안 (업그레이드/수정 버전)

> 작성 기준: 본 문서는 이번 세션에서 실제 코드베이스(`backend/app`, `mobile`, `admin`, `Dockerfile*`, `docs/CODE_REVIEW_FRAMEWORK.md`)를 직접 읽고 검증한 결과에 기반한다.
> 공유 링크(`https://codebuddy.work/agents/tasks/share/9Bd0r6vwmQ`)는 HTTP 200으로 **정상 접근 가능**하나, React SPA로서 내용이 클라이언트 사이드에서 렌더링되며 WorkBuddy 앱 세션 컨텍스트(인증/Provider)가 필요해 외부 도구로는 렌더링된 평가 텍스트를 추출하지 못했다. 따라서 아래 기획안은 링크의 제목("분석 시스템 부족점 및 재구성 방안")과 본 프로젝트에 대한 검증된 분석 결과를 통합하여 작성한 **업그레이드 버전**이다.

---

## 0. 링크 접근성 확인 결과

| 항목 | 결과 |
|---|---|
| HTTP 상태 | 200 OK (정상) |
| 페이지 형태 | WorkBuddy 공유 SPA (`share.html` → React 라우터 `/tasks/share/:code`) |
| 콘텐츠 렌더링 | 클라이언트 사이드 (`getBackendProvider().getTaskShareDetail(code)`) |
| 외부 도구 가독성 | **불가** — 인증/세션 컨텍스트 필요, 정적 크롤링 불가 |
| 사용자(app 내) 접근 | 정상 (공유 대상이므로 앱에서 열림) |

→ 사용자가 링크 본문을 붙여넣어 주시면, 본 기획안을 그 평가의 문단별로 정확히 정렬시켜 수정하겠다.

---

## 1. 배경 및 목적

korean-gospel-ai는 FastAPI 백엔드 + 모바일 PWA + Streamlit 관리자 + Qdrant(임베디드/클라우드)로 구성된 복음 Q&A RAG 시스템이다. 그간 10개 파트 코드 리뷰(Part 5–10), 성능 최적화, 배포 데이터 유실 수정, 신고/오류신고 시스템 설계를 진행하며 **상당수 버그는 이미 수정**되었다. 본 기획안은 (1) 아직 플랜/미처리 상태인 항목을 정리하고, (2) 점 진화한 구조적 부채를 아키텍처 차원에서 리팩토링하며, (3) 설계만 완료된 신고/오류신고 시스템을 **구현 가능한 상세 스펙**으로 승격시키는 것을 목적으로 한다.

---

## 2. 시스템 부족점 통합 카탈로그 (검증 기준)

상태: `✅수정` / `📋설계완료-미구현` / `⏸권고-미적용` / `🟡부분`

| 레이어 | ID | 부족점 | 심각도 | 상태 |
|---|---|---|---|---|
| 배포/인프라 | P9-0 | SQLite 경로 불일치(`/app/.gospel.db` vs 마운트 `./gospel.db`) → 재시작 시 데이터 유실 | P0 | ✅수정(`db.py` `DB_PATH` env + compose 주입) |
| LLM | P5-1 | DeepSeek-V4 답변이 `reasoning_content`에 옴 → `content` 비어 응답 공백 | P1 | ✅수정(`text_from_message/delta` 헬퍼) |
| 모바일 | P6-12 | 채팅 `history`에 현재 질문이 이미 포함 → 백엔드 중복 삽입(질문 2회) | P1 | ✅수정(`mobile/screens/index.js`) |
| 관리자 | P7-1 | API 클라이언트가 `ConnectError`만 처리 → 타임아웃/HTTP/JSON 크래시 | P2 | ✅수정(`(httpx.HTTPError, ValueError)`) |
| 관리자 | P7-2 | 삭제/보관 액션 확인 체크박스 없음 | P2 | ✅수정(5개 페이지) |
| 인증 | P8-3 | Google OAuth `aud`만 검증 → `iss` 위조 차단 누락 | P1 | ✅수정(`iss` 체크 추가) |
| 성능 | OPT-A | `/chat/stream` FAQ 캐시를 quota 이후 조회 → 중복 질문마다 DB+토큰 낭비 | P1 | ✅수정(순서 정렬 + 토큰 0 소모) |
| 성능 | OPT-B | `RedactingFilter`가 3개 핸들러에 각각 부착 → 로그 라인당 정규식 3회 | P2 | ✅수정(logger级 1개 + 키워드 게이트) |
| 성능 | OPT-C | `ContextCompressor._extract_keywords`가 호출마다 stopwords 재생성+정규식 인라인 컴파일 | P3 | ✅수정(모듈상수 hoist) |
| 성능 | OPT-D | `build_prompts` 루프 내 `import re`+인라인 컴파일 | P3 | ✅수정(모듈상수 hoist) |
| 테스트 | bug | `test_rrf_fusion`이 리팩터된 `_rrf_fusion_streams` 시그니처와 불일치(스테일) | P2 | ✅수정(신규 시그니처로 갱신) |
| 테스트 | P10-9 | `test_enhanced_rag`가 전역 `settings.qdrant_url` 변이 후 복원 안 함 | P3 | ✅수정(try/finally) |
| 아키텍처 | A1 | RAG 진입점 중복: `search_v4.py`/`retriever.py`/`rag_engine.py`/`enhanced_rag/*` 4개 병존, 역할 경계 모호 | P1 | 🟡부분(일부만 사용) |
| 아키텍처 | A2 | `settings` 싱글톤 + `.env` 직접 env read 혼재, 타입 검증 없음 | P2 | ⏸미적용 |
| 아키텍처 | A3 | DB 접근이 `db.py` 전역 engine 직접 사용, Repository 추상화 없음 | P2 | ⏸미적용 |
| 관측성 | A4 | 로그가 평문 텍스트, 구조화(JSОN) 안 됨; 메트릭/트레이스 누락 | P2 | 📋설계완료-미구현 |
| 기능 | F1 | **신고/오류신고 시스템** — 설계만 완료, 구현 미시작 | P1 | 📋설계완료-미구현 |
| 정합성 | A5 | 사전 존재 미사용 import 다수(`db.py`, `error_monitor.py`, `chat_pipeline.py`, `auth.py`) | P3 | ⏸미적용(리뷰 범위 외) |
| 견고성 | P10-3 | 고에러량 시 `error_monitor` DB 쓰기 미배치화 | P3 | ⏸권고(이중 dedup으로 커버, 인메모리 버퍼는 크래시 시 유실 역설) |

---

## 3. 리팩토링 로드맵 (우선순위별, 4단계)

### Phase 0 — 안정성 마무리 (즉시, ~1주)
- [x] P9-0 데이터 유실 수정 (완료)
- [x] P5-1 / P6-12 / P8-3 / OPT-A~D / 스테일 테스트 수정 (완료)
- [ ] **A5 미사용 import 정리** (`pyflakes` 기준 일괄 제거, 동작 동일 → 제로 리스크). 영향: 가독성/정적분석 통과.
- [ ] **런타임 스모크 테스트 자동화**: 컨테이너 기동 후 `/health` + `/docs` + 1회 채팅 왕복을 `deploy.sh`가 검증(현재 health만 체크).

### Phase 1 — 아키텍처 정합성 (중기, ~3주) ⭐ 본 기획안 핵심
**A1 — RAG 서비스 통합**
- 목표: 4개 진입점을 **하나의 `RAGService` 파사드**로 수렴. 내부는 `HybridRetriever`(dense KURE + BM25 폴백 + RRF) 단일 구현만 유지.
- 방식: `search_v4.py`/`retriever.py`/`rag_engine.py`를 `enhanced_rag/` 하위로 이식, 레거시 3개는 deprecation warning 후 1개 릴리즈 뒤 삭제. **기존 공개 API 경로(`/chat`, `/chat/stream`) 동작 보존**이 최우선 제약.
- 위험: 검색 품질 회귀 → 점진적 스위치(`RAG_BACKEND=legacy|unified` env)로 카나리.

**A2 — 설정 타입화**
- `config.py`의 `settings`를 pydantic `BaseSettings`로 전환(이미 `pydantic-settings` 의존성 존재 가능성 높음 — 미확인 시 추가). env 검증(`QDRANT_URL`, `LLM_PROVIDER` 열거형)으로 기동 시 조기 실패.
- 영향: 12개 모듈이 `settings.xxx` 접근 → 인터페이스 유지하면 제로 리스크.

**A3 — 데이터 접근 추상화**
- `Session` 직접 사용 → `Repository` 클래스(`SubscriberRepo`, `InteractionRepo`, `ErrorLogRepo`, `TicketRepo`[F1 신규])로 캡슐화.
- FK 정합성(신고↔`AppErrorLog`)과 WAL 쓰기 경합(`BEGIN IMMEDIATE`) 패턴을 Repository에 집중.

### Phase 2 — 성능/캐시 고도화 (중기, ~2주)
- **임베딩 캐시 격상**: 현재 `CachedEmbedder`가 전역 dict(프로세스 메모리, 휘발). → LRU + 선택적 Redis(옵트인, `CACHE_REDIS_URL` 비어있으면 인메모리). 쿼리 임베딩은 이미 전역 공유되므로 **사용자 간 중복 제거는 이미 됨** — 여기서는 장기 생존 + 다중 워커 공유가 목적.
- **검색 결과 캐시 TTL 명확화**: `cache_utils`/`faq_cache`에 TTL+무효화 훅(`invalidate_on_ingest`) 추가. 인제스트 시 관련 FAQ 캐시만 선별 무효화.
- **비동기 배치**: 채팅 응답 스트리밍과 무관한 부가 기록(상호작용 저장, FAQ 캐싱)은 이미 `_spawn_bg_task` 비동기 → 이 패턴을 표준 `TaskQueue`로 추출.

### Phase 3 — 관측성 (중기, ~2주)
**A4 — 구조화 로그 + 메트릭**
- `logging_setup.py`에 `JSONFormatter` 옵션(`LOG_FORMAT=json`) 추가. 이미 `scrub_secrets` 적용됨.
- Prometheus 메트릭 경량 추가: 채팅 지연(P95/P99), 검색 hit-rate, FAQ 캐시 적중률, 에러율. `/metrics` 엔드포인트(추가 의존성 최소).
- `AppErrorLog`를 Grafana/CloudWatch로 내보내는 exporter(선택).

### Phase 4 — 기능 구현: 신고/오류신고 시스템 (하기 섹션 4 상세) ⭐

---

## 4. 상세 설계 — 신고/오류신고 시스템 (업그레이드 버전)

기존 설계를 구현 가능 수준으로 승격. **핵심 판단 유지**: "고동시성"은 오판 — 실제 위험은 배드 버전 배포 시 PWA 크래시 폭주이며, 이는 **클라이언트+서버 이중 dedup**으로 방어(큐/Redis 불필요).

### 4.1 데이터 모델 (DDL — `support_ticket` 단일 테이블)

```sql
CREATE TABLE support_ticket (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_no     VARCHAR(32) NOT NULL UNIQUE,   -- 'RPT-YYMM-XXXXX'
    kind            VARCHAR(8)  NOT NULL,           -- 'report' | 'error'
    status          VARCHAR(12) NOT NULL DEFAULT 'pending', -- pending|processing|resolved|rejected
    priority        VARCHAR(8)  NOT NULL DEFAULT 'normal', -- low|normal|high|urgent
    subscriber_id   VARCHAR(36),                     -- NULL 허용(익명 신고)
    reporter_ip      VARCHAR(50),
    -- 신고 전용
    target_type     VARCHAR(16),                     -- content|comment|user|other
    target_ref       VARCHAR(120),                    -- 대상 ID/URL
    category        VARCHAR(24),                     -- spam|abuse|harassment|violation|other
    -- 오류신고 전용
    error_stack      TEXT,
    device_info      TEXT,                            -- UA/OS/앱버전 JSON
    operation_path   VARCHAR(255),
    is_auto          BOOLEAN DEFAULT 0,              -- 프론트 자동 캡처 여부
    -- 공통
    description      TEXT,
    context_json     TEXT,                            -- 확장 필드(스크린샷 URL 등)
    signature_hash   VARCHAR(64),                     -- dedup용 해시
    flagged          BOOLEAN DEFAULT 0,               -- check_input 히트
    assigned_to      VARCHAR(64),
    resolution_note  TEXT,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    error_log_id     INTEGER,                         -- AppErrorLog FK (P2)
    FOREIGN KEY (error_log_id) REFERENCES app_error_log(id)
);
CREATE INDEX ix_ticket_status ON support_ticket(status);
CREATE INDEX ix_ticket_kind ON support_ticket(kind);
CREATE INDEX ix_ticket_sig ON support_ticket(signature_hash, created_at);
```
- Alembic 마이그레이션新增(`alembic/versions/xxxx_add_support_ticket.py`). SQLite WAL 모드 가정.
- `AppErrorLog`는 원형 유지(원시 시스템 로그). 고 severity는 P2에서 선택적 티켓 자동 생성(`error_log_id` FK).

### 4.2 백엔드 API 계약

| 메서드 | 경로 | 설명 | auth |
|---|---|---|---|
| POST | `/report` | 신고 제출(스크린샷 다중 업로드) | 익명 허용 |
| POST | `/error-report` | 오류신고 제출(자동/수동) | 익명 허용 |
| GET | `/report/{tracking_no}` | 추적번호로 진행상태 조회 | 공개(본인 범위) |
| GET | `/admin/tickets` | 목록+필터(상태/유형/우선순위/기간) | admin_api_key |
| POST | `/admin/tickets/bulk` | 상태/우선순위 일괄 갱신 | admin_api_key |
| POST | `/admin/tickets/{id}` | 상세 갱신(상태전이/메모/우선순위) | admin_api_key |

**제출 플로우(공통)**
1. `rate_limit` 미들어웨어(`/report`, `/error-report`에 확장) — IP RPM/RPH + 15분 차단.
2. `signature_hash = sha256(subscriber_id|ip + normalize(description) + target_ref|error_stack[:500])` → 60초 윈도우 내 동일 해시 존재 시 409 `duplicate`(서버 dedup).
3. `check_input(description)` → 히트 시 `flagged=1`(삭제 안 함, 관리자 하이라이트).
4. 스크린샷: `image/png|jpeg|webp` + 5MB + UUID 파일명 → `data/reports/screenshots/`. `scrub_secrets` 적용 후 저장.
5. `_spawn_bg_task`로 비동기 DB write(응답 블로킹 방지, `BEGIN IMMEDIATE`).
6. `tracking_no = f"RPT-{YYMM}-{rand5}"` (충돌 시 재시도).

### 4.3 프론트엔드 (모바일 PWA + 관리자)

**모바일 `mobile/`**
- `window.onerror` + `unhandledrejection` 리스너(`utils/state.js` 초기화) → 오류 스택+`device_info`(UA/OS/`AppState` 버전)+`operation_path`(현재 라우트) 수집.
- **클라이언트 dedup**: `localStorage`에 `lastErrorSig = sha256(stack[:500]+UA)` + 타임스탬프, 동일 시그니처 5분 내 중복 전송 차단(크래시 폭주 방어).
- 경량 공유 모달 `screens/report_modal.js`: 신고/오류 탭, 유형 선택, 설명+스크린샷 첨부, 제출. 메인 플로우 방해 안 함(플로팅 버튼).

**관리자 `admin/pages/18_🚩_신고함.py`**
- 2탭(신고/오류) + 필터(상태/유형/우선순위/기간) + plotly 통계(유형·상태·월별 추이).
- 상세: 상태 전이 버튼(pending→processing→resolved/rejected), 우선순위 드롭다운, 처리 메모, 스크린샷 프리뷰.
- 일괄: `st.session_state` 멀티셀렉트 → `/admin/tickets/bulk`(P7-2 패턴의 확인 체크박스 적용).
- 기존 `api_client` 재사용 + `st.cache_data` + `safe_api_call`.

### 4.4 중복제거 / 보안 / 콘텐츠 필터 (알고리즘)

```
클라이언트: on error -> sig = hash(stack[:500] + UA)
            if localStorage[sig] within 5min: drop
            else: POST /error-report; localStorage[sig]=now

서버: sig = hash((sub_id||ip) + norm(desc) + (target_ref||stack[:500]))
      if Ticket.exists(sig, since=now-60s): 409 duplicate
      else: insert (async)
```
- **보안**: 추적번호 조회는 본인이 생성한 번호만 볼 수 있음(추적번호 자체가 무작위) → 권한 우회 불가. 익명 신고는 `subscriber_id` NULL, 차단 불가하나 rate_limit로 남용 방지.
- **필터**: `check_input` 히트 = `flagged` 마킹, 삭제 안 함(실제 신고 오탐 방지).
- **스크린샷**: mime/용량 검증 + UUID 파일명(사용자 파일명 불신) + 별도 디렉터리(`media`와 분리).

### 4.5 명시적으로 제외(과도한 복잡도)
- sourcemap 스택 디코딩(원시 스택만 저장) / Redis 큐(이중 dedup으로 충분) / 이미지 OCR(인건审核) / 메일 알림(추적번호 조회로 대체) / RBAC(단일 admin 키).

---

## 5. 리스크 및 검증 계획

| 리스크 | 완화 |
|---|---|
| A1 RAG 통합 시 검색 품질 회귀 | `RAG_BACKEND` 카나리 스위치 + 회귀 테스트(`test_enhanced_rag` 확장) |
| A3 Repository 추상화가 쿼리 경로 변경 유발 | 단계적 이전, 기존 엔드포인트 e2e 유지 |
| F1 스크린샷 저장 경로 권한 | 컨테이너 볼륨 마운트 `+ DB_PATH`와 동일 정책 적용 |
| 로그 JSON 포맷 변경이 기존 파서 영향 | `LOG_FORMAT` env 기본 `text` 유지, opt-in |

**검증 런북(이미 가동 중)**: `py_compile` → `pyflakes`(신규 경고 0) → `from backend.app.main import app`(113 routes) → `pytest tests/` → 컨테이너 `/health`.

---

## 6. 마일스톤 요약

| 단계 | 범위 | 산출물 | 예상 기간 |
|---|---|---|---|
| Phase 0 | 잔여 안정성 + A5 | 미사용 import 제거, 스모크 테스트 | ~1주 |
| Phase 1 | A1/A2/A3 아키텍처 | `RAGService` 파사드, pydantic 설정, Repository | ~3주 |
| Phase 2 | 캐시/비동기 | LRU/옵트인 Redis, 캐시 무효화, TaskQueue | ~2주 |
| Phase 3 | 관측성 | JSON 로그, 메트릭 `/metrics` | ~2주 |
| Phase 4 | F1 기능 | 신고/오류신고 시스템 전체 구현 | ~2주 |

> 총괄: 안정성·핵심 버그는 **이미 해결**됨. 남은 가치는 아키텍처 부채 정리(A1–A3)와 **설계 완료된 신고/오류신고 시스템의 실제 구현(Phase 4)**, 그리고 관측성 강화(A4)에 집중하는 것.
