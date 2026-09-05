# 용어집 기능 대체 기획서 — "자동 추출 용어집" → "번역 용어집"

> 작성일: 2026-07-27
> 상태: 기획(PR0 분석 완료, 구현 대기)

---

## 0. 현황 진단 (가장 중요한 발견)

코드베이스에는 **이름만 같은 '용어집'이 두 개** 따로 존재합니다. 사용자가 본 것은 (A), 원하는 것은 (B)입니다.

### (A) 자동 추출형 용어집 — 제거 대상 ❌
- `backend/app/services/glossary_service.py` : 자료 발행 시 명사 빈도 추출 → `GlossaryTerm` DB에 저장
- `backend/app/models/orm.py` : `GlossaryTerm` 테이블 (frequency/doc_count/status/theology_flag 등 13컬럼)
- `backend/app/api/glossary.py` : 승인/거부/병합 CRUD API (`main.py:292` 마운트됨)
- `admin/pages/14_📚_용어집.py` : 검토 대기/승인 완료 관리 UI
- `backend/app/services/publish_service.py:258, 465` : `extract_terms_from_text()` 호출
- `backend/app/api/admin.py:90` : 헬스체크가 `GlossaryTerm.count()` 사용

**문제**: 사용자 지적대로 "반복되는 아무런 의미없는 단어"만 모읍니다(빈도 기반 명사 추출). 무엇보다 **번역 품질과 완전히 분리**되어 있고, UI에 적힌 "D3 가드레일 자동 반영"의 `get_theology_whitelist()`는 **실제로 어디에도 소비되지 않는 dead code**입니다.

### (B) 번역 용어집 — 확장 대상 ✅ (사용자가 원하는 것)
- `backend/app/services/enhanced_rag/data/glossary_zh.json` : KO→ZH 매핑 53개
- `backend/app/services/enhanced_rag/translation.py` : `translate()`가 이 JSON을 LLM 번역 프롬프트에 강제 주입
- `backend/app/services/enhanced_rag/config.py` : `BilingualConfig(primary_lang="zh")`

**현재 한계**: ① 중국어만 있음(영어 필드 없음) ② 53개뿐(신학 대화 용어의 ~35% 커버) ③ 관리 UI 없이 JSON 수동 편집 ④ 채팅 파이프라인(`chat_pipeline.py`)에는 미주입(RAG 문서 번역만 주입).

> **결론적 인사이트**: 제거할 (A)를 지우고, (B)를 "KO→ZH+EN 번역 용어집"으로 승격시키면 사용자의 니즈가 정확히 충족됩니다. (A)를 고치는 것이 아니라 (B)가 (A)의 자리를 대체하게 만듭니다.

---

## 1. 대체 설계: "번역 용어집" (Translation Glossary)

### 1.1 단일 진실 공급원 (Single Source of Truth)
`glossary_zh.json` → `glossary.json` 으로 확장. **JSON 우선** 방식(기존 패턴 유지, DB 마이그레이션 불필요):

```json
{
  "version": "v2",
  "source_lang": "ko",
  "target_langs": ["zh", "en"],
  "terms": [
    {"ko": "은혜", "zh": "恩典", "en": "grace",      "category": "doctrine", "note": "은혜"},
    {"ko": "보혈", "zh": "宝血", "en": "precious blood", "category": "doctrine", "note": "보혈"},
    {"ko": "대속", "zh": "代赎", "en": "substitutionary atonement", "category": "doctrine", "note": "대속"}
  ]
}
```

- `ko`(핵심 키) / `zh`(중국어) / `en`(영어) / `category` / `note`(운영자 메모)
- 런타임 캐시(`GlossaryCache`, TTL 5분)로 요청마다 파일/DB 조회 방지

### 1.2 용어 확장 (53 → 150+)
`docs/design-term-translation-system.md` §1.3에 누락 용어 목록이 이미 정리됨:
보혈, 성육신, 원죄, 대속, 중보기도, 구속, 성만찬, 직분, 안수, 축복, 소명, 사명, 회복, 위로, 평안, 순종, 겸손, 인내, 거룩, 의인, 택함, 언약, 율법, 계명, 시험, 연단, 정결, 화평, 긍휼, 자비 …
우선순위: Tier1 구원론 30개 → Tier2 인명/지명/서명 40개 → Tier3 예배/교회생활 40개 → Tier4 상담 40개.

### 1.3 주입 경로 (번역 품질이 실제로 올라가는 지점)
| 경로 | 현재 | 변경 |
|------|------|------|
| RAG 문서 번역 | `translation.py` ZH만 | EN 추가 (`build_glossary_block`에 en 분기) |
| **채팅 파이프라인** | 미주입 | `chat_pipeline.py`에서 `target_lang`이 `zh`/`en`일 때 system prompt에 glossary_block 주입 (신규) |
| 검색 인덱싱 | — | ZH 검색어→KO 문서 매칭 (P2, 선택) |

- 토큰 비용: 등장 용어만 프롬프트에 포함하므로 요청당 ~100~300토큰 추가(미미).
- `chat_pipeline.py:586`에 이미 `if target_lang == "en"` 분기가 있으므로 EN 답변 경로는 존재 — 용어집만 붙이면 됨.

### 1.4 관리 UI (Admin)
`admin/pages/14_📚_용어집.py`를 **번역 용어집 관리 페이지로 전면 교체**:
- 용어 목록/검색 (ko/zh/en/category)
- 신규 추가 / 수정 (ko, zh, en, category, note)
- "번역 검증" 토글 (운영자가 직접 확인한 용어는 주입 우선)
- JSON export/import (백업·이식)
- 미번역 용어(EN 빈칸) 하이라이트

---

## 2. 제거 범위 (자동 추출형 용어집)

| 대상 | 처리 |
|------|------|
| `backend/app/api/glossary.py` (자동추출 CRUD) | 삭제 (또는 번역 용어집 서빙용으로 재활용) |
| `main.py:292` `include_router(glossary.router)` | 제거 |
| `admin/pages/14_📚_용어집.py` | 번역 용어집 페이지로 교체 |
| `backend/app/services/glossary_service.py` | 삭제 (`extract_terms_from_text`, `get_theology_whitelist` 포함 — 둘 다 미소비) |
| `publish_service.py:256-261, 462-468` | `extract_terms_from_text` 호출 제거 |
| `backend/app/models/orm.py` `GlossaryTerm` | 테이블 삭제 + Alembic 다운마이그레이션 |
| `admin.py:87-94` 헬스체크 | `GlossaryTerm.count()` → `glossary.json` term 수로 교체 |

> 제거 영향: 번역 파이프라인은 (B)인 `glossary.json`을 쓰므로 (A) 삭제와 무관. 가드레일도 dead code라 무효화 없음.

---

## 3. 실행 단계 (Phased)

- **Phase 1 — 데이터 모델/확장 (1~2h)**: `glossary.json`(ko/zh/en) 생성 + 53→150+ 확장. `load_glossary`가 en 필드 읽도록 수정.
- **Phase 2 — 주입 확장 (2~3h)**: `translation.py` EN 분기 + `chat_pipeline.py` zh/en glossary_block 주입.
- **Phase 3 — 자동추출 제거 (1~2h)**: §2 항목 일괄 제거 + 마이그레이션.
- **Phase 4 — 관리 UI (1~2h)**: 14번 페이지 번역 용어집으로 교체.
- **Phase 5 — QA (1h)**: `verify_translation_terms()`(설계서 §5.3) + zh/en 통합 테스트.

**총 예상 공수: 약 6~10시간.**

---

## 4. 위험 / 주의

- **GlossaryTerm 테이블 삭제**는 Alembic 마이그레이션 필요(참조는 admin 헬스체크뿐 — 단순 교체).
- **용어 검증은 운영자 수동**이 전제(자동 추출 아님) → 정확성이 오히려 보장됨.
- **EN 주입 시 토큰 증가**는 미만하나, `target_lang=ko`(기본)일 땐 주입 안 함.
- 기존 `docs/design-term-translation-system.md`는 DB 중심 설계였으나, 본 기획은 **JSON 우선**으로 단순화(마이그레이션 부담 최소). DB가 필요해지면 Phase 1 데이터를 `GlossaryTerm`로 이관 가능.

---

## 5. 요약

사용자가 "필요없다"고 한 것은 (A) 자동 추출 용어집이고, "더 필요하다"고 한 것은 (B) 번역 용어집입니다.
**(A)를 삭제하고 (B)를 KO→ZH+EN 관리형 번역 용어집으로 승격**시키는 것이 정답입니다. 이렇게 하면 무의미한 단어 수집은 사라지고, 번역 품질을 좌우하는 신학 용어의 중국어·영어 매핑이 모든 번역 경로에 강제 주입됩니다.
