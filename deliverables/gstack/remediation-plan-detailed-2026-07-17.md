#  — 개선 로드맵 상세 (재실행 / 2026-07-17)

**상태**: Phase 0-4 전 항목 이번 세션에서 구현 완료. 본 문서는 재실행 기준 **잔여/후속 액션**으로 갱신.

---

## Phase 0~4 — 구현 완료 (재실행 확인)
전 항목 ✅. 상세 구현 내역은 `plan-vs-implementation-2026-07-17.md` 및 `system-audit-korean-gospel-ai-2026-07-17.md` 참조.
검증: `py_compile` OK · pyflakes 신규 경고 0 · import 132 routes · pytest 69 passed.

---

## 잔여 / 후속 액션 (M5 이후)

### A. 제품/모델 (P0-1 후속)
- **A1 실제 모델 교체**: 유효한 non-reasoning tencent 모델명 확보 시 `config.py` `tencent_model` 교체. (현재 reasoning 모델 코드 측 방어만 적용)
- **A2 타임아웃 튜닝**: 빠른 모델 도입 후 `llm_provider_timeout_sec` 90→30~45 하향.

### B. 모바일 보안 (P4-7 후속)
- **B1 subId 메모리 전환**: `gospel_sub_id` localStorage 4건 → 메모리 or `sessionStorage`(새로고침 시 재로그인 허용). 저위험이나 strict 보안을 위해 권고.

### C. 코드품질 (P1-4/레거시)
- **C1 린트 부채 정리**: 사전존재 미사용 import 19건(admin/auth/chat/documents/drafts/glossary/media/enhanced_rag) `ruff --fix` 일괄. → 신규 경고 0 목표 달성.

### D. 레포 정리 (P4-9 후속)
- **D1 대형 문서 분리**: `HANDOFF_*`/히스토리 `.md`(>50KB)를 `docs/archive/` 로 이동 또는 위키화.
- **D2 `_archive/` 검토**: `user_app.py` 영구 보관 확인 또는 삭제.

### E. 프로세스 개선 (별도 기획안)
- **E1~E6**: `process-improvement-plan-2026-07-17.md` 참조 — pytest 병목 병렬화, 검증 거짓음성 제거, 린트 은폐 해소, 프로세스 명칭 문서화.

---

## 권고 실행 순서
1. C1 (린트 정리) — 즉시, 위험 낮음.
2. A1/A2 (모델 교체) — 키 확보 시.
3. B1 (subId) — 보안 강화 마일스톤.
4. E1~E6 (프로세스) — 다음 감사 주기 전.
5. D1/D2 (레포) — 별도 정리 패스.
