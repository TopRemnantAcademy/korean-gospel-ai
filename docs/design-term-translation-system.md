# 신학 용어 정밀 번역 시스템 — 설계서

> **핵심 철학**: 전체 콘텐츠를 이중 언어로 저장하지 않는다. 대신 **신학적으로 오역되면 안 되는 용어 150여 개의 KO→ZH 매핑을 단일 진실 공급원(Single Source of Truth)으로 관리**하고, 이 용어집을 모든 번역 경로에 강제 주입한다. 정확성이 모든 것보다 우선한다.

> **이전 평가 참조**: `docs/evaluation-dual-lang-storage.md` — 전체 콘텐츠 이원화 저장은 불필요하다고 판단. 본 문서는 그 대안으로 **용어 수준 정밀 번역**을 제안한다.

---

## 1. 문제 정의

### 현재 상태의 취약점

```
사용자: "보혈의 능력이 무엇인가요?" (target_lang=zh)
         ↓
LLM 실시간 번역: "宝血的能力是什么？"  ← 운 좋게 맞음
                      또는
                 "血的能力是什么？"    ← ❌ 보혈(宝血)을 血로 오역
```

| 항목 | 현재 | 문제 |
|------|------|------|
| glossary_zh.json | 53개 용어 | 신학 대화에서 등장하는 용어의 약 35%만 커버 |
| GlossaryTerm DB | 85개 화이트리스트 | KO→ZH 번역 정보 없음 (한국어 정의만 있음) |
| 번역 주입 경로 | Enhanced RAG 문서 파이프라인만 | 채팅 파이프라인에는 용어집 주입 안 함 |
| 용어 관리 | JSON 파일 수동 편집 | Admin UI 없음, 변경 이력 없음 |

### 실제 누락된 핵심 용어들

현재 glossary_zh.json에 없지만 실제 대화에서 빈번히 등장하는 용어:

```
보혈 → 宝血           성육신 → 道成肉身       원죄 → 原罪
대속 → 代赎           중보기도 → 中保祷告     구속 → 救赎
성만찬 → 圣餐         직분 → 职分             안수 → 按手
축복 → 祝福           소명 → 召命             사명 → 使命
회복 → 恢复           위로 → 安慰             평안 → 平安
순종 → 顺从           겸손 → 谦卑             인내 → 忍耐
거룩 → 圣洁           의인 → 义人             택함 → 拣选
언약 → 约             율법 → 律法             계명 → 诫命
시험 → 试探           연단 → 熬炼             정결 → 洁净
화평 → 和平           긍휼 → 怜悯             자비 → 慈悲
```

---

## 2. 설계: 단일 진실 공급원 + 다중 주입 경로

### 2.1 핵심 원칙

```
┌──────────────────────────────────────────────────┐
│           용어집 (Single Source of Truth)          │
│  KO term → ZH translation (운영자 검증, 버전 관리) │
│  DB: GlossaryTerm.zh_translation                   │
│  JSON: glossary_zh.json (export/import 호환)       │
└──────────────┬───────────────────────────────────┘
               │
     ┌─────────┼─────────┬──────────────┐
     ▼         ▼         ▼              ▼
  채팅 번역   RAG 번역   검색 인덱싱    Admin UI
  (system     (기존      (중국어        (용어
   prompt     경로)      검색어 →       추가/수정/
   주입)                 KO 문서)       검증)
```

### 2.2 데이터 모델 변경

#### GlossaryTerm ORM 확장 (1개 컬럼 추가)

```python
# backend/app/models/orm.py — GlossaryTerm 클래스에 추가
zh_translation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
# 예: term="보혈", zh_translation="宝血"
# NULL → 아직 번역 할당 안 됨 (번역 대상 목록에서 관리 가능)
zh_verified: Mapped[bool] = mapped_column(Boolean, default=False)
# True → 운영자가 직접 확인한 번역. 주입 시 우선 사용.
zh_verified_by: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
zh_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

**영향**: 기존 12개 컬럼 → 15개 컬럼. Alembic 마이그레이션 1회. 기존 데이터는 NULL 허용.

### 2.3 용어집 JSON 확장

53개 → 150+개로 확장. 구조 유지, `terms` 배열에 누락 용어 추가.

```json
// glossary_zh.json v2 구조 동일, terms만 확장
{
  "version": "v2",
  "source_lang": "ko",
  "target_lang": "zh",
  "terms": [
    // ... 기존 53개 유지 ...
    {"ko": "보혈", "zh": "宝血", "category": "doctrine", "note": "precious blood"},
    {"ko": "성육신", "zh": "道成肉身", "category": "doctrine", "note": "incarnation"},
    {"ko": "대속", "zh": "代赎", "category": "doctrine", "note": "substitutionary atonement"},
    {"ko": "원죄", "zh": "原罪", "category": "doctrine", "note": "original sin"},
    // ... 100개 이상 추가 ...
  ]
}
```

### 2.4 동기화 서비스

```python
# backend/app/services/glossary_sync.py (신규)

# DB → JSON export
def export_glossary_to_json(db: Session, output_path: Path) -> dict:
    """GlossaryTerm.zh_translation이 있는 모든 용어를 JSON으로 출력"""

# JSON → DB import
def import_glossary_from_json(db: Session, json_path: Path) -> int:
    """glossary_zh.json 내용을 DB GlossaryTerm.zh_translation에 반영.
    이미 있는 용어는 업데이트, 없는 용어는 신규 등록."""

# 인메모리 캐시 (서비스 시작 시 로드, TTL 5분)
class GlossaryCache:
    """KO→ZH 매핑의 인메모리 캐시. 번역 요청마다 DB 조회 방지."""
    _cache: dict[str, str] = {}  # {ko_term: zh_translation}
    _last_load: float = 0
    TTL: float = 300  # 5분
```

---

## 3. 주입 경로 설계

### 3.1 경로 A: 채팅 파이프라인 (핵심)

`target_lang="zh"`일 때 system prompt에 용어집을 주입.

```
현재:
  system_prompt = "당신은 한국 기독교 AI 상담사입니다..."

변경 후 (target_lang=zh):
  system_prompt = "당신은 한국 기독교 AI 상담사입니다..."
  + "\n\n[신학 용어 번역 규칙 - 반드시 준수]"
  + "\n다음 용어는 반드시 아래 번역으로 사용하세요:"
  + "\n- 보혈 → 宝血"
  + "\n- 은혜 → 恩典"
  + "\n- 구원 → 救恩"
  + "\n... (답변 텍스트에 실제 등장한 용어만 포함)"
```

**구현 지점**: `chat_pipeline.py`의 `build_prompts()` 함수

```python
# chat_pipeline.py 수정 (의사코드)
if target_lang == "zh":
    glossary_block = glossary_cache.build_context_prompt(response_text_keywords)
    system_prompt = f"{system_prompt}\n\n{glossary_block}"
```

**비용**: LLM 프롬프트 토큰 약 100~300토큰 추가 (등장 용어만 포함하므로). DeepSeek 기준 요청당 약 $0.0001 추가.

### 3.2 경로 B: Enhanced RAG 번역 (기존)

이미 `translation.py`의 `LLMTranslator.translate()`에서 용어집 주입 중.  
→ glossary_zh.json 확장만으로 자동 적용됨. 코드 변경 없음.

### 3.3 경로 C: 검색 인덱싱 (신규)

중국어 사용자가 "宝血"로 검색했을 때 "보혈" 포함 문서를 찾을 수 있도록:

```
KO 문서 → glossary 치환 → ZH 텍스트 → embedding → Qdrant (zh 벡터)
```

기존 Enhanced RAG의 `bilingual_smoke.py` 패턴을 `interaction` 테이블의 답변에도 선택적 적용.

**우선순위**: P2. 검색 인덱싱보다 용어 일관성이 먼저.

### 3.4 경로 D: Admin UI (용어 관리)

`admin/pages/`에 용어집 관리 페이지 추가 (또는 기존 Glossary API 확장):

| 기능 | 기존 | 추가 |
|------|------|------|
| 용어 목록/검색 | GET /glossary | + ZH 번역 컬럼 표시 |
| 용어 승인/거부 | POST /glossary/{id}/approve | + `zh_translation` 필드 |
| ZH 번역 일괄 가져오기 | 없음 | POST /glossary/import-zh |
| 미번역 용어 목록 | 없음 | GET /glossary/untranslated |
| 번역 검증 상태 | 없음 | PATCH /glossary/{id}/verify-zh |

---

## 4. 구현 계획

### Phase 1: 용어집 확장 (1~2시간)

| 작업 | 파일 | 공수 |
|------|------|------|
| glossary_zh.json 53→150개 확장 | `enhanced_rag/data/glossary_zh.json` | 1h |
| 누락 신학 용어 조사 및 검증 | (리서치) | 30m |
| DB GlossaryTerm에 `zh_translation` 컬럼 추가 | `models/orm.py` | 15m |
| Alembic 마이그레이션 | `alembic/versions/` | 10m |

### Phase 2: 동기화 + 캐시 (1~2시간)

| 작업 | 파일 | 공수 |
|------|------|------|
| `glossary_sync.py` (export/import/cache) | 신규 | 1h |
| 서비스 시작 시 캐시 웜업 | `main.py` lifespan | 15m |
| `glossary_zh.json` → DB 초기 import 스크립트 | `scripts/` | 30m |

### Phase 3: 채팅 파이프라인 주입 (1~2시간)

| 작업 | 파일 | 공수 |
|------|------|------|
| `build_prompts()`에 glossary_block 주입 | `chat_pipeline.py` | 45m |
| 등장 용어만 추출하는 `build_context_prompt()` | `glossary_sync.py` | 30m |
| 스트리밍 채팅 검증 | `chat.py` (stream endpoint) | 30m |

### Phase 4: Admin UI (1~2시간)

| 작업 | 파일 | 공수 |
|------|------|------|
| 용어집 관리 페이지 | `admin/pages/19_📖_용어집.py` | 1h |
| 번역 상태 표시 + 검증 기능 | 위 페이지 | 30m |
| API 확장 (untranslated, verify-zh) | `api/glossary.py` | 30m |

### 총 예상 공수: 4~8시간

---

## 5. 품질 보증

### 5.1 번역 검증 체크리스트 (용어별)

| 검증 항목 | 기준 |
|-----------|------|
| 신학적 정확성 | 한국 개신교 표준 용어와 일치 |
| 중국어 교계 표준 | 중국 삼자교회(三自教会) 및 가정교회에서 통용되는 표현 |
| 한자 선택 | 간체자(简体字) 사용, 대만어(번체) 아님 |
| 문맥 적합성 | 단독 사용 시와 문장 내 사용 시 동일한 의미 |

### 5.2 검증 우선순위

1. **Tier 1 (필수)**: 구원론 핵심 용어 30개 — 보혈, 대속, 칭의, 성화, 구원, 은혜, 믿음, 회개, 중생, 속죄, 부활 등
2. **Tier 2 (중요)**: 성경 인명/지명/서명 40개
3. **Tier 3 (권장)**: 예배/교회 생활 용어 40개
4. **Tier 4 (선택)**: 상담/심리 용어 40개

### 5.3 오류 감지

```python
# 번역 결과에 용어집 매핑이 지켜졌는지 확인
def verify_translation_terms(ko_text: str, zh_result: str, glossary: dict) -> list[str]:
    """KO 원문에 등장하는 용어가 ZH 번역문에 올바르게 반영되었는지 검사."""
    violations = []
    for ko_term, expected_zh in glossary.items():
        if ko_term in ko_text and expected_zh not in zh_result:
            violations.append(f"{ko_term} → {expected_zh} 누락")
    return violations
```

---

## 6. 기존 이원화 저장 제안과의 비교

| 항목 | 전체 이원화 저장 ❌ | 용어 정밀 번역 ✅ |
|------|---------------------|-------------------|
| DB 컬럼 추가 | 14개 | 3개 (zh_translation, zh_verified, zh_verified_by) |
| 번역 대상 | 모든 채팅 응답, 모든 인사이트 | 150개 용어 (유한집합, 사람 검증 가능) |
| LLM API 비용 | 요청당 항상 추가 | target_lang=zh일 때만 (전체의 약 5~10%) |
| 정확성 보장 | 불가능 (전수 검증 불가) | 가능 (용어 하나씩 수동 검증) |
| 유지보수 | 편집 시 ZH 동기화 버그 가능성 | 용어집만 관리하면 됨 |
| Admin UI | 복잡한 편집기 필요 | 간단한 테이블 CRUD |
| 번역 품질 리스크 | 높음 (오역 발견 시 모든 저장 데이터 재처리) | 낮음 (용어집 수정 1건 → 즉시 전체 적용) |

---

## 7. 결론

**용어 수준 정밀 번역 시스템을 도입한다.**

- 전체 콘텐츠 이중 저장은 하지 않는다 (이전 평가 유지).
- 대신 150여 개 핵심 신학 용어의 KO→ZH 매핑을 단일 진실 공급원으로 관리한다.
- 이 용어집을 채팅 번역, RAG 번역, 검색 인덱싱의 모든 경로에 강제 주입한다.
- 용어 하나를 수정하면 모든 번역 경로에 즉시 반영된다.
- 관리자는 Admin UI에서 용어별 번역을 검증·수정할 수 있다.
- **정확성**이 최우선이다. LLM이 창의적으로 번역하게 두지 않고, 검증된 용어집으로 제어한다.
