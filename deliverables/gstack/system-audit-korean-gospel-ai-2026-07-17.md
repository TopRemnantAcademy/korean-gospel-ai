#  — 시스템 감사 (재실행 / 2026-07-17)

**재실행 목적**: 기존 정제 프로세스(감사→대조→개선로드맵)를 처음부터 재실행하여 현재 상태를 갱신.
**이전 결론**: 🟡 조건부 Go (6개 🔴 차단항목). **이번 재실행 결론: 🟢 Go (차단항목 0, 잔여 🟠 2 / 🟡 3)**.

---

## 📌 TL;DR (재실행)
- **전체 결론**: 🟢 **Go** — 이전 6개 🔴 차단항목(Phase 0-4)이 이번 세션에서 **전부 구현 완료**되어 재실행 시 잔여 차단항목 0.
- 진짜 가치였던检索内核(HybridRetriever/KURE/BM25/RRF, 다국어 프롬프트, 위기차단)은 보존.
- **잔여 🟠(2)**: (1) 모바일 `gospel_sub_id` localStorage 잔존(토큰은 메모리 only — 저위험), (2) 사전존재 미사용 import 19건(린트 부채).
- **잔여 🟡(3)**: (1) P0-1 실제 모델 교체 미이행(유효 non-reasoning 키 부재 → 코드 측 타임아웃/파라미터만 적용), (2) `_archive/`·대형 히스토리 문서 별도 정리 보류, (3) 위기 핫라인(1393/1577 등) 생명안전 자원으로 의도 보존(기획의 "중독 문구 0"과 충돌하나 삭제 안 함).

---

## 🎯 핵심 결론 카드 (재실행)
| 항목 | 내용 |
|------|------|
| Go / No-Go | 🟢 Go (차단항목 0) |
| 심각도 분포 | 🔴 0 / 🟠 2 / 🟡 3 |
| route 수 | 132 (`/ready`,`/health`,`/rag/*` 4, `/support/tickets`,`/admin/support/*`) |
| 테스트 | 69 passed (pytest 36.6s — 프로세스 병목, 별도 개선 기획안 참조) |

---

## 5차원 리뷰 (현재 상태)

### ① 제품/프로세스 — ✅ 해소
- Phase 0-4 전 항목 구현 완료(상세는 `plan-vs-implementation-2026-07-17.md`).
- P0-3 `/rag/*` 인증, P0-4 `/ready`, P1-2 이중엔진 게이팅(기본 off), P1-4 기동 DDL 제거, P3-1 복음 브랜딩, P3-3 `user/app.py` 아카이브, Phase 4 (캐시/인젝션방어/rate-limit/Qdrant fail-closed/retriever boost/모바일보안/신고시스템) 전부 적용.

### ② 보안 — ✅ 대부분 해소, 🟠 1 잔여
- `/rag/*` 4개 엔드포인트 `require_admin`(빈키/`change-me`→503) 적용 ✅
- `user_context` 인젝션 방어(`prompt_guard`) ✅, 모바일 `?api=` SSRF 벡터 제거 ✅
- auth 토큰 메모리 only ✅ / **`gospel_sub_id` localStorage 잔존(4건, 저위험) 🟠**

### ③ QA/릴리스 — ✅ 해소, 🟡 린트 부채
- py_compile OK, 신규 pyflakes 경고 0, pytest 69 passed ✅
- **사전존재 미사용 import 19건 🟠 (admin/auth/chat/documents 등) — 별도 정리 마일스톤**

### ④ 디자인 — ✅ 해소
- `app.py` 회복→복음(🌿), `DESIGN.md` 토큰 진실원, 테마 `.get()` 크래시 방지, 그레디언트 solid 폴백, 포커스 링 ✅

### ⑤ 코드품질/아키텍처 — ✅ 해소
- 이중엔진 게이팅, retriever boost 누적 수정, embedded 락 가드, 루트 `_*.py` 디버그 5개 삭제 ✅

---

## 다음 단계
1. P0-1 실제 모델 교체(유효 키 확보 시).
2. 모바일 subId 메모리 전환 또는 sessionStorage(저위험, 선택).
3. 린트 부채 일괄 정리(ruff --fix).
4. **정제 프로세스 자체 개선** → `process-improvement-plan-2026-07-17.md` 참조(pytest 병목·검증 거짓음성·린트 은폐 해결).
