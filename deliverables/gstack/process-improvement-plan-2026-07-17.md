#  — 정제 프로세스 개선 기획안
## (감사 → 기획대조 → 개선로드맵 파이프라인 재실행 결과)

**작성일**: 2026-07-17
**목적**: `deliverables/gstack/`의 3개 산출물(system-audit, plan-vs-implementation, remediation-plan)을 만드는 "정제 프로세스"를 처음부터 재실행하면서 각 단계 소요시간을 계측하고, 느린 구간·문제 구간을 식별해 **프로세스 자체의** 개선 방안을 수립한다.
**범위**: 프로세스 효율화/신뢰성 — 제품 결함 자체가 아님(그것은 3개 산출물에 반영).

---

## 1. 재실행 단계 구성 (정제 프로세스 파이프라인)

| 단계 | 이름 | 내용 | 측정 방식 |
|------|------|------|-----------|
| S1 | 컨텍스트 준비 | 스킬 로드, 고정 사실 수집 | 수동 |
| S2 | 코드베이스 인벤토리 | 파일 수·모듈·route·테스트 집계 | `date +%s%3N` |
| S3 | 제품/기능 리뷰 | Phase 0-4 항목별 구현 여부 대조 | `date +%s%3N` |
| S4 | 보안 리뷰 | 인증/노출/인젝션/모바일 | `date +%s%3N` |
| S5 | QA/릴리스 리뷰 | py_compile·pyflakes·pytest | `date +%s%3N` |
| S6 | 디자인 리뷰 | 브랜딩·토큰·테마 | `date +%s%3N` |
| S7 | 코드품질/아키텍처 | 데드코드·이중엔진·embedded 락 | `date +%s%3N` |
| S8 | system-audit 재생성 | 통합 감사서 작성 | Write |
| S9 | plan-vs-implementation 재생성 | 항목별 완성도 | Write |
| S10 | remediation-plan 재생성 | Phase 0-4 상세 로드맵 | Write |

---

## 2. 단계별 소요시간 측정 결과 (이번 재실행)

| 단계 | 소요(ms) | 비고 |
|------|----------|------|
| S1 컨텍스트 | ~5,000 | 스킬 1회 read (별도 계측 생략) |
| **S2 인벤토리** | **11,809** | 앱 임포트(라우터 18개 로딩)+pytest 수집이 지배적 |
| S3 제품/기능 | 1,664 + 정밀재확인 ~500 | 내용 grep → 파일명/임포트 재확인 |
| S4 보안 | 625 + 정밀재확인 ~300 | |
| **S5 QA/릴리스** | **40,486** | **pytest 36,631ms 가 전체의 71% — 최대 병목** |
| S6+S7 디자인/품질 | 1,096 | |
| **계측 합계(툴 실행)** | **~57,000** | S5(71%) + S2(21%) 가 92% 점유 |

**핵심 병목**: `S5 pytest 전체 수행(36.6s)` ≫ `S2 앱 임포트/수집(11.8s)` ≫ 나머지(각 <2s).

---

## 3. 식별된 문제 구간 (느린 구간 + 오류 구간)

### 🔴 P-A. S5 pytest 전체 수행이 과도하게 느림 (36.6s)
- **위치**: S5 단계, `pytest tests/` (69건)
- **원인**:
  1. 단위/통합 구분 없이 전체를 직렬 1회 실행.
  2. 설정·임베딩 등 무거운 fixture가 매 테스트에서 재초기화.
  3. (가능성) 일부 테스트가 실LLM/네트워크 경로에 걸릴 결합도.
- **수정방법**:
  - `pytest-xdist`로 병렬화(`-n auto`).
  - 마커 분리: `@pytest.mark.fast`(순수 단위, mock) / `@pytest.mark.slow`(통합). 기본 `pytest`는 fast만, CI에서 slow 병렬.
  - LLM/임베딩/DB는 전부 mock fixture로 교체(네트워크 0).
  - `pytest --cache` + `--lf`(실패만 재실행).
- **예상효과**: 단위 서브셋 <8s, 병렬 전체 <15s. 재실행 1회당 ~25s 절감.

### 🟠 P-B. S2 앱 임포트 + pytest 수집 병목 (11.8s)
- **위치**: S2 단계, `from backend.app.main import app` + `pytest --collect-only`
- **원인**: 앱 임포트 시 18개 라우터 전부 즉시 로드 + 로깅 초기화. 인벤토리 단계에서 굳이 전 라우터를 import할 필요 없음.
- **수정방법**:
  - 인벤토리용 경량 스크립트(`scripts/inventory.py`)로 route 수를 별도 import 없이 `FastAPI` 라우트 정의만 정적으로 세거나, 라우터 로딩을 지연(lazy)화.
  - pytest 수집은 S5로 역할 이관(중복 제거).
- **예상효과**: S2 <3s (≈9s 절감), 중복 제거.

### 🔴 P-C. S3 검증 거짓음성(false negative) — 파일 내용 grep 오한
- **위치**: S3 단계, `grep -rq "user_app" _archive/` 등 4건 MISS
- **원인**: "구현 여부"를 **파일 내용**에 포함된 문자열로 판정. 그런데 `user_app`은 파일**이름**이고, `prompt_guard`는 **다른 파일의 import**에만 등장 → 내용 grep은 0건이라 "미구현"으로 오판.
- **수정방법**:
  - 검증 기준을 "파일 존재(`ls`) + import/route 존재"로 변경.
  - 또는 `grep` 대상을 파일명(`ls`)과 전체 repo import 모두 포함시킴.
  - 각 체크에 "확인 방식(존재/임포트/라우트)" 주석 필수화.
- **예상효과**: 감사 정확도 100%(거짓음성 0), 잘못된 "미구현" 경보 제거.

### 🟠 P-D. S4 조잡한 grep 카운트 — 보안 판정 오독
- **위치**: S4 단계, `localStorage` 카운트=20 → "메모리 only 아님"으로 오해 소지
- **원인**: 보안 핵심은 **인증 토큰**(gospel_token)인데, 전체 `localStorage` 발생 횟수를 세어 테마/언어 등 무관한 20건과 혼동. 실제 토큰은 0건(메모리 only)이나 subId 4건 잔존.
- **수정방법**:
  - 보안 체크는 **비밀 키 명칭**(`gospel_token`, `gospel_sub_id`)을 직접 타겟팅.
  - "localStorage 미사용"이 아니라 "인증 토큰의 localStorage 미사용"으로 명세화.
- **예상효과**: 보안 verdict 명확화(subId 잔존을 저위험 잔여항목으로 정확히 분류).

### 🟠 P-E. S5 pyflakes 불완전 스캔(head -50) → 린트 부채 은폐
- **위치**: S5 단계, `pyflakes ... | head -50` (139개 중 50개만)
- **원인**: 속도를 위해 상위 50개만 검사 → admin/auth/chat/documents 등 후반 파일의 **19건 미사용 import 부채**가 보이지 않음.
- **수정방법**:
  - `ruff` 단일 패스(`ruff check`, C로 구현되어 전체 139파일을 수초 내)로 대체.
  - 또는 CI에서 전체 pyflakes/ruff 를 게이트로 고정(로컬 단계는 요약만).
  - 사전존재 부채는 `autoflake -r --in-place` 또는 `ruff --fix` 일괄 정리(별도 마일스톤).
- **예상효과**: 린트 부채 가시화 + 전체 스캔 <3s, 신규 경고 0 목표 달성 가능.

### 🟡 P-F. "정제 프로세스" 용어 모호성 (3파일 vs 14파일)
- **위치**: 프로세스 진입 단계 (대상 파일 특정)
- **원인**: "정제"가 (a) `refine_sermons.py` 설교 원문 정제(대상 14개 txt)와 (b) 감사/개선 산출물 정리의 두 의미로 충돌. 사용자 발화 "보유한 3개 파일"과 실제 정제 대상(14개)이 불일치해 재실행 범위 혼선.
- **수정방법**:
  - 프로세스 명칭을 명확히: "감사 정제 파이프라인(audit-refine)" vs "설교 정제(refine_sermons)" 구분 문서화.
  - 3개 산출물 세트를 `deliverables/gstack/README` 또는 `MANIFEST`로 명시(감사 정제의 출력물 = 이 3개).
- **예상효과**: 재실행 범위 모호성 제거, 신규 작업자 온보딩 오류 방지.

---

## 4. 단계별 개선 액션 (실행 계획)

| 우선순위 | 액션 | 대상 | 산출물 |
|----------|------|------|--------|
| P0 | pytest-xdist + fast/slow 마커 + mock fixture | S5 | `pytest.ini`/`conftest.py` 갱신 |
| P0 | 검증 기준을 존재/임포트/라우트로 전환 | S3/S4 체크리스트 | `deliverables/gstack/VERIFY.md` |
| P1 | 인벤토리 경량 스크립트 + 라우터 지연로딩 | S2 | `scripts/inventory.py` |
| P1 | ruff 전체 스캔 + 부채 일괄 정리 | S5 | `ruff.toml`, `autoflake` 실행 |
| P2 | 프로세스 명칭/산출물 세트 문서화 | 진입 | `deliverables/gstack/MANIFEST.md` |

---

## 5. 예상 효과 요약

- **재실행 총 소요**: ~57s → **~25s** (pytest 병렬 + S2 경량화 + 중복 제거).
- **감사 정확도**: 거짓음성 4건 → 0건, 보안 오독 제거.
- **린트 가시성**: 19건 은폐 부채 → 전체 스캔으로 가시화.
- **재현성**: 명확한 산출물 세트 + 검증 기준 문서화로 재실행 범위 혼선 해소.

> 부록 — 이번 재실행에서 제품 측으로 새로 식별된 잔여 항목(별도 추적):
> 1. 모바일 `gospel_sub_id` localStorage 잔존(4건, 저위험 — 토큰은 메모리 only). P4-7 후속.
> 2. 사전존재 미사용 import 19건(admin/auth/chat/documents 등). P1-4/레거시 정리 범위.
> 3. P0-1 실제 모델 교체 미이행(유효 non-reasoning 키 부재). 키 확보 후 적용.


---

## 후속 조치 (2026-07-18 — 냉정 재검증 기반 실제 fix)

이전 재실행이 "🟢 Go, 차단 0"로 too rosy 했던 점을 감안, grep 이 아닌 **live TestClient/테스트로 기능 재검증** 후 진짜 결함만 수정.

### 실제 수정된 항목
- **P-E (lint 부채) → 해결**: `ruff` 설치 후 `ruff check --fix`로 미사용 import/중복정의 **78건**(F401/F811) + `except Exception as e` 미사용 **8건**(F841) 제거. `db.py`/`migrations/env.py` 의 `.orm` import 는 ORM 등록 side-effect 라 제거 금지(의도적 잔여).
- **P-G (신규 발견 — 인증 게이트 미검증)**: 기존 enhanced_rag 테스트는 파이프라인 내부만 다루고 **HTTP 인증 계층(require_admin→401/503)을 전혀 검증 안 함**. → `tests/test_admin_auth.py` 신규(6케이스: /ready 구조, require_admin 401/503/None, /rag 무키 거부)로 CI 잠금. live 프로브로 401(무키)/401(오키)/200(정키)/503(change-me) 모두 확인.
- **P-H (신규 발견 — 잠재 버그)**: `insight_engine.regenerate_insights_for_stale(older_than_days)` 가 `cutoff` 를 계산만 하고 쿼리에 적용 안 해 `older_than_days` 가 silently 무시됨. → `insight_generated_at <= cutoff` (+ is_(None) OR) 필터 추가. `__import__("datetime")` 악취 정식 import로 교체.
- **데드 변수 제거**: `documents.py` `_version_id` 2건, `trending_service.py` `fb_total` 1건.

### 재검증 결과 (기능적으로 확인됨 — 결함 아님)
- P0-3/P0-4/P4#2/P1-2/answer_cache/retriever boost: live 또는 테스트로 실제 동작 확인.
- 모바일 `gospel_sub_id` localStorage 잔존: 비밀(토큰) 아님, 익명 대화 연속성용 문서화된 의도 → **수용**.

### 검증
- `py_compile` backend 전체 OK · `pyflakes` 잔여 = 의도적 orm 2건 + cosmetic 3건(무해).
- `pytest tests/` → **75 passed** (기존 69 + 신규 auth 6).
