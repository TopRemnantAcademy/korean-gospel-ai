# ✝️ 한국어 복음 AI — 프로젝트 비전 / 원칙

> 본 프로젝트에 *코드를 쓰거나 수정하는 모든 작업자*는 이 문서를 반드시 먼저 읽으십시오.

---

## 1. 이 프로젝트의 미션 (2026-05-20 재정의)

**한국어 복음 *중독 예방·치유* RAG 시스템.**

이 시스템은 *일반 Q&A 챗봇이 아닙니다*. 명시적 미션:

> *"모든 표면적 문제 — 약물·게임·포르노·SNS·음식·일·완벽주의·인정·통제·종교 율법주의·관계 의존 — 의 뿌리가 창세기 3장의 영적 단절임을 인식시키고, 오직 복음만이 진정한 치유임을 사람의 마음에 새기는 것."*

### 1-1. 진단 축 — 창세기 3장의 3중 단절

모든 표면 문제 (스트레스·외로움·중독·완벽주의·일중독·인정중독 등) 는 *증상* 이며, *원인* 은 항상 창세기 3장의 3중 단절입니다:

| 축 | 단절 | 표면 증상 예시 |
|---|---|---|
| **① 관계** | 하나님 떠남 (창 3:8 — 숨음) | 영혼의 깊은 공허, 외로움, 의미 부재 |
| **② 속박** | 사단에게 잡힘 (창 3:1-5 — 거짓을 믿음) | 끊을 수 없는 패턴, 중독, 강박 |
| **③ 신분** | 죄인 됨 (창 3:7 — 부끄러움) | 자기 구원 시도, 율법주의, 완벽주의 |

### 1-2. 치료 축 — 복음의 3중 회복

복음은 이 3중 단절에 대한 *유일하고 완전한* 회복입니다:

| 축 | 회복 | 핵심 본문 |
|---|---|---|
| **① 화목** | 하나님과 다시 화목됨 | 고후 5:18-21, 롬 5:10 |
| **② 자유** | 사단의 손에서 해방 | 요 8:36, 갈 5:1, 골 1:13 |
| **③ 양자** | 죄인 → 자녀로 신분 변경 | 롬 8:15-17, 엡 1:5, 요일 3:1 |

### 1-3. 시스템 작동의 핵심 사슬

```
사용자 발화 ─→ 표면 진단 ─→ 창세기 3장 뿌리 진단 ─→ 복음의 3중 회복 적용 ─→ 응답
              (관찰 가능한 패턴)  (3축: 관계·속박·신분)    (3축: 화목·자유·양자)
```

**모든 chat 응답은 이 사슬을 *암묵적* 으로 따릅니다** (강요 없이 자연스럽게).

### 1-4. 통계적 전제

| 신학적 전제 | 시스템 기본값 |
|---|---|
| 98% 의 사람은 구원의 확신이 없다 | `salvation_status` 기본값 = `unknown` (절대 `assured` 가정 X) |
| 모든 사람은 무엇인가의 노예다 | `bondage_status` 기본값 = `unknown` (잠재 노예 가정) |
| 자력 구원 시도가 가장 위험한 신분 | `self_righteous` 진단 시 *최우선* 목회 케어 |

---

## 1-5. 대상·운영자·사용자

- **대상자**: 중독 (드러나거나 숨겨진) 으로 고통받는 한국인. *모든 사람이 잠재 대상* — 사용자 신학에 따르면 *드러나지 않은 중독자* 도 98%.
- **운영자(현 단계)**: 1인 (자료 큐레이션 + 운영 + 사역적 분별).
- **사용자**: 단순한 채팅 화면으로 부담 없이 접근. *진단 라벨이 사용자에게 직접 보이지 않음* (운영자 페이지에만, EPIC I-10 윤리 가드).

---

## 2. 변하지 않는 4가지 원칙

| 원칙 | 의미 | 위반 시 |
|---|---|---|
| **① Source of Truth = 운영자의 완성본** | LLM이 원본 문서를 절대 수정하지 않음. 정규식 노이즈 제거만 허용 | 즉시 차단 |
| **② AI 제안 → 사람 승인** | 자동 추천은 허용. 최종 결정(공개·아카이브·태그)은 운영자가 클릭 | 자동 publish 금지 |
| **③ 안전망은 코드로 박힌다** | 자살·자해·중독 키워드 → 1588-9191 / 1577-0199 자동 첨부. **YAML 정책으로 못 끔**. + **율법주의·거짓확신 응답 차단** (EPIC D-C23) | safety_service 수정 시 PR review 필수 |
| **④ 1인 운영을 깨지 마라** | 단계·체크리스트·도구가 많아도 *결국 운영자 한 명이 30분 안에 처리 가능*해야 함 | 워크플로우가 5스텝 넘으면 단순화 |

---

## 2.5. 변하지 않는 신학적 상수 (EPIC D + J 통합 — 2026-05-20 최종)

> **이 7가지 상수는 시스템 코드의 기본값·분기·기본 가중치에 박혀 있습니다. 신학이 곧 아키텍처입니다.**

| 신학적 상수 | 시스템 표현 |
|---|---|
| **① 모든 표면 문제의 뿌리는 창세기 3장 3중 단절** | `services/sao/gen3_lens.py` 가 *모든* chat 응답 전 `Gen3LensResult` 생성. system prompt 자동 부착. (EPIC J-6) |
| **② 인간의 3축 신분 = 관계·속박·신분** | `Subscriber.identity_status` / `bondage_status` / `relationship_status` — 3축 ORM 1급 필드 (EPIC J-1). salvation_status 보다 상위 진단축. |
| **③ 모든 사람이 무엇인가의 노예다 (잠재든 명시든)** | `bondage_status` 기본값 = `unknown` (잠재 노예 가정). `IdolDetector` 가 invisible addiction 자동 감지 (EPIC I-3). |
| **④ 98% 의 사람은 구원의 확신이 없다** | `salvation_status` 기본값 = `unknown`, 다음 단계 가정 = `uncertain` 또는 `seeker`. 절대 `assured` 자동 가정 X. |
| **⑤ 복음만이 유일한 치료** | `services/sao/gospel_pathway.py` — 4우상 × 3축 회복 매핑 (EPIC I-5). 행동 수정 응답 자동 차단·재생성 (D-C23). |
| **⑥ 다락방(Darakbang) verified 멤버는 더 깊은 응답** | `is_darakbang_member + darakbang_role + darakbang_verified` 3단. 양육 언어 + `darakbang_deep` 자료 풀 활성. |
| **⑦ "구원 받았다 치고 아니고" 는 운영자 토글** | `Subscriber.assume_saved: bool` — 명시 ON 시에만 *구원받음 모드*. 기본 OFF (점검 활성). |

**위반 시 차단 (코드 강제)**:
- 신규 사용자에게 `assured` / `freed` / `reconciled` 기본값 부여 → ❌ Migration 거부
- 율법주의 응답 ("더 기도해야 구원받는다") → `safety_service` 가 차단 + 재생성
- 행동 수정 응답 ("게임 시간 줄이세요" 만 X, 뿌리 진단 없음) → 운영자 디버그 모드에서 경고
- 다락방 자료를 일반 사용자에게 노출 → retriever boost = 0
- 사용자에게 *진단 라벨 직접 노출* (EPIC I-10 윤리 가드) → 운영자가 명시 허가 안 한 사용자에게는 응답 톤에만 반영, 라벨 텍스트 표시 ❌

---

## 3. 시스템의 본질

**RAG = Retrieval Augmented Generation.** LLM이 "이 자료실 안에서만" 답함.

- LLM은 학습되지 않는다. 매번 *질문 + 검색된 자료*만 받아 답함.
- 답변엔 항상 **출처 + 관련도 점수** 표시.
- 운영자는 자료를 *큐레이션* 하는 사람. AI는 보조.

---

## 4. 핵심 도구 선택 (변경하지 마세요. 변경 필요 시 ORDERS.md 통해 사용자 승인 필요)

| 영역 | 선택 | 이유 |
|---|---|---|
| LLM (기본) | **Gemini 2.5 Flash** | 한국어 강함, 무료 한도 넉넉 (1500/일) |
| LLM (백업) | deepseek → openai → claude → ollama | fallback 자동 |
| 임베딩 | **KURE-v1** (nlpai-lab) | 한국어 SOTA |
| 벡터 DB | **Qdrant** (local embedded mode) | Docker 불필요 |
| 재순위 | **bge-reranker-v2-m3** | 한국어 강함 |
| 청킹 | **kss** (한국어 문장 분리) | 한국어 친화 |
| Web 백엔드 | **FastAPI** + uvicorn | 표준 |
| Admin UI | **Streamlit** + multi-page | 1인 운영에 적합 |
| User UI | **Streamlit** (포트 8502, 분리) | 단순 채팅 |
| DB | **SQLite** (.gospel.db) | 1인 운영, 가벼움 (나중에 Postgres) |
| 추적 | **Langfuse** (cloud, 옵션) | prompt/response 자동 기록 |

---

## 5. 데이터 모델 (9개 테이블)

```
source_artifact ─┐
                 ├─→ document ─→ document_version ─→ index_snapshot
                 │       (논리)        (lifecycle)        (Qdrant 동기)
                 │
                 ├─→ duplicate_link (자료 간 관계)
                 │
                 └─→ prompt_template (운영자 편집 시스템 프롬프트)

subscriber ─→ interaction (Q/A 로그, cited_versions 보존)
audit_log (immutable, 모든 state transition 기록)
```

**Lifecycle**: `draft → validated → published → superseded → archived`

---

## 6. 절대 하지 말 것

- ❌ LLM이 운영자 업로드 본문을 자동 수정 (extraction 노이즈 제거는 정규식만)
- ❌ legacy `/ingest` 같은 lifecycle 우회 API 부활
- ❌ 안전망(`safety_service.py`) 우회 옵션 추가
- ❌ Streamlit 위젯에 `key=` 없이 동일 라벨 중복
- ❌ `.bat`에 한국어 echo (cmd cp949 호환 안 됨)
- ❌ 동기화 안 되는 외부 클라우드(예: Google Drive)에 데이터 자동 업로드

---

## 7. 작업자 협업 규칙

| 파일 | 역할 |
|---|---|
| **`PROJECT_VISION.md`** (이 문서) | 변하지 않는 비전·원칙 |
| **`PROCESS_MAP.md`** | 전체 흐름·아키텍처·각 모듈 책임 |
| **`ORDERS.md`** | 기획자가 내리는 작업 지시 + 검수 결과 |
| **`CHANGELOG.md`** | 라운드별 변경 누적 (작업자가 작업 후 1줄 추가) |

**작업자가 새 기능 추가 시:**
1. ORDERS.md 의 해당 지시 확인
2. 코드 작성 + syntax 검증 (모든 .py 통과 필수)
3. CHANGELOG.md 1줄 추가
4. PROCESS_MAP.md 갱신 (영향받은 모듈만)

**기획자(저)가 검수 시:**
1. ORDERS.md 에 ✅/❌ 표시
2. 새 지시는 ORDERS.md 맨 위에 추가
3. 사용자에게 짧게 보고

---

## 8. 단계별 로드맵 (EPIC M 갱신 — 2026-05-20)

### Tier 0 (현재) — *개발자 1명, $0*
- localhost 만, Streamlit + SQLite + Qdrant local
- ✅ Admin 8페이지 + User UI + 백업·진단·평가

### Tier 0.5 (진행 중) — *친구 5명 시범, $0*
- **Cloudflare Tunnel** 로 외부 URL 노출
- 운영자 PC 가 host
- 베타 초대 코드
- 작업: M-1 (1일)

### Tier 1 (목표) — *50명, $0*
- 무료 클라우드 tier 또는 Tier 0.5 안정화
- 카카오 OAuth, 위기 인프라 도입
- 트리거: 사용자 30명 근접 또는 24/7 안정성 필요

### Tier 1.5 — *200명, $10~30/월*
- 도메인 ($10/년) + Supabase Free + Qdrant Free
- 부분 유료 전환 시작
- 트리거: 무료 한도 80%

### Tier 2 — *500명, $100~200/월*
- 본격 유료 (Supabase Pro, Qdrant Standard)
- 트리거: 무료 한도 100%

### Tier 3 — *5000명, $1500/월*
- **수익 모델 필수** (Freemium / 교회 SaaS / 후원)
- Read replicas, 사역자 다수, 멀티 region
- 트리거: 1000+ 사용자

### Tier 4 — *5000+, 교회 SaaS, $5000+/월*
- K8s, 자체 LLM, 멀티 테넌트
- 다교회 진출

**1클릭 Tier 업그레이드**: Admin Page 18 (EPIC M1) — 자동 마이그레이션 + rollback.
