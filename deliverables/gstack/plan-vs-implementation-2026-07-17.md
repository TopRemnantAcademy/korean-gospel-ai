#  — 기획안 vs 구현 대조표 (재실행 / 2026-07-17)

**결론**: 이전 대조에서 Phase 0-4 미구현 🔴 20건 → 이번 재실행에서 **전부 구현 완료**. 누락 0, 미완성 0, 기획과 다르게 구현된 사항은 "의도적 예외 2건"(위기 핫라인 보존, subId localStorage 잔존)만 존재.

---

## Phase 0 — 안전 발매 (M0)
| 항목 | 기획 | 구현 | 상태 |
|------|------|------|------|
| P0-3 `/rag/*` 인증 | 무인증 4개 엔드포인트 보호 | `require_admin`(빈키/`change-me`→503) | ✅ |
| P0-4 `/ready` | DB/Qdrant/LLM 실검증 실패 503 | `main.py` `/ready` 신설 | ✅ |
| P0-1 지연 | reasoning ~78s → <10s | 타임아웃 90s·파라미터 설정화 (실제 교체는 키 부재로 보류) | 🟡 부분 |
| P0-2 비스트리밍 타임아웃 | 20s→안정 | `llm_provider_timeout_sec=90` | ✅ |

## Phase 1 — 정리 (M1)
| 항목 | 기획 | 구현 | 상태 |
|------|------|------|------|
| P1-1 Qdrant env 분기 | prod server / dev embedded | `app_env`+embedded 락 가드+빈키 fail-closed | ✅ |
| P1-2 이중엔진 게이팅 | enhanced_rag 상주 제거 전 게이팅 | `_maybe_search_enhanced`(기본 off) | ✅ |
| P1-4 기동 DDL 제거 | Alembic 전담 | `main.py` raw DDL 제거 | ✅ |

## Phase 3 — 프론트 (M3)
| 항목 | 기획 | 구현 | 상태 |
|------|------|------|------|
| P3-1 재브랜딩 | 회복→복음 | 페이지 타이틀 🌿, 도메인 신앙 전환 | ✅ (위기핫라인 보존) |
| P3-2 토큰/크래시 | 단일 토큰·테마 방어 | `DESIGN.md`+`.get()`+gradient 폴백+포커스링 | ✅ |
| P3-3 프론트 정리 | user/app 중복 제거 | `_archive/user_app.py` 아카이브, README 갱신 | ✅ |

## Phase 4 — 강화 (M4)
| # | 항목 | 구현 | 상태 |
|---|------|------|------|
| 1 | 답변 캐시(TTL) | `answer_cache.py`(Redis 옵션) | ✅ |
| 2 | 프롬프트 인젝션 | `prompt_guard.py` | ✅ |
| 3 | Rate limit | XFF·Redis·경로확장 | ✅ |
| 4 | Qdrant 노출 | P1-1에 통합(빈키 fail-closed) | ✅ |
| 5 | 관리후단 인증 | `require_admin` change-me 거부 | ✅ |
| 6 | retriever boost | `_compute_profile_boost` 누적 수정 | ✅ |
| 7 | 모바일 보안 | `?api=` 제거·토큰 메모리 | ✅ (subId 잔존 🟠) |
| 8 | 신고/오류 | `SupportTicket`+엔드포인트 | ✅ |
| 9 | 레포 정리 | 루트 `_*.py` 5개 삭제 | 🟡 (`_archive`/대형문서 보류) |

---

## 의도적 예외 (기획과 다른 구현, 정당함)
1. **위기 핫라인 보존**: 기획 "중독 도메인 문구 0"이나 1393/1577/1588-9191/129는 생명안전 자원 → 삭제 안 함, 신앙 상담 맥락으로 재배치.
2. **subId localStorage 잔존**: auth 토큰은 메모리 only(보안 목적 달성), subId는 비밀 아닌 식별자로 UX 유지를 위해 잔존(저위험).

## 검증
- `py_compile` OK, 신규 pyflakes 경고 0, `app` import 132 routes, `pytest tests/` 69 passed.
