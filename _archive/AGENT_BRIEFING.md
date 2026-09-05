# 🧭 AGENT BRIEFING — 새 AI 작업자를 위한 *단일* 영혼 이식 파일

> **이 한 파일만 읽으면 됩니다.** 이 문서는 약한 AI 모델도 사용자(piaoyhyh@gmail.com)와 같은 방향에서 즉시 작업을 이어갈 수 있도록 설계되었습니다.
>
> 다른 문서 (ORDERS.md / PROJECT_VISION.md / PROCESS_MAP.md / CHANGELOG.md) 는 *보조 자료* 입니다. 이 파일이 *프로젝트 전체의 영혼*.
>
> **작성**: 2026-05-20 / **마지막 동기화**: CHANGELOG.md 와 항상 일치

---

## 목차

1. [60초 안에 — 이 프로젝트가 무엇인가](#1-60초-안에--이-프로젝트가-무엇인가)
2. [사용자 (운영자) 의 신학적 정체성](#2-사용자-운영자-의-신학적-정체성)
3. [궁극의 미션 — 중독 예방·치유](#3-궁극의-미션--중독-예방치유)
4. [창세기 3장 — 진단의 모든 출발점](#4-창세기-3장--진단의-모든-출발점)
5. [98% 전제 — 시스템의 핵심 가정](#5-98-전제--시스템의-핵심-가정)
6. [7가지 신학적 상수 (코드 박힘)](#6-7가지-신학적-상수-코드-박힘)
7. [참조 신학 프레임워크 — 코드 통합 방식](#7-참조-신학-프레임워크--코드-통합-방식)
8. [기술 스택 (현재 + 미래)](#8-기술-스택-현재--미래)
9. [시스템 아키텍처 — 한 그림](#9-시스템-아키텍처--한-그림)
10. [데이터 모델 (현재 9개 + 계획 ~30개)](#10-데이터-모델-현재-9개--계획-30개)
11. [핵심 파이프라인 5종](#11-핵심-파이프라인-5종)
12. [LLM 전략 + 비용 모델](#12-llm-전략--비용-모델)
13. [협업 모델 — Claude vs Cursor 역할](#13-협업-모델--claude-vs-cursor-역할)
14. [EPIC 전체 지도 A~K](#14-epic-전체-지도-ak)
15. [현재 상태 스냅샷 + 작업 큐](#15-현재-상태-스냅샷--작업-큐)
16. [절대 하지 말 것 — Anti-Patterns](#16-절대-하지-말-것--anti-patterns)
17. [의사결정 흐름도 — "무엇을 먼저 할까"](#17-의사결정-흐름도--무엇을-먼저-할까)
18. [파일·폴더 지도](#18-파일폴더-지도)
19. [용어집](#19-용어집)

---

## 1. 60초 안에 — 이 프로젝트가 무엇인가

이 프로젝트는 **한국어 복음 *중독 예방·치유* RAG 시스템** 입니다.

*일반 Q&A 챗봇이 아닙니다.* 표면 문제 (약물·게임·SNS·일중독·완벽주의·인정 추구) 의 뿌리가 *창세기 3장의 영적 단절* 임을 사용자에게 인식시키고, *복음만이 유일한 치유* 임을 마음에 새기는 *영적 진단·치료 엔진*.

**한 줄 요약**: *"Q&A 봇이 아니라, 모든 인간이 무엇인가의 노예임을 데이터로 증명하고 그리스도가 진정한 해방임을 보여주는 시스템."*

**작동 핵심 사슬**:
```
사용자 발화 → 표면 진단 → 창세기 3장 뿌리 진단 → 복음의 3중 회복 적용 → 응답
              (관찰 가능 패턴)  (관계·속박·신분 단절)    (화목·자유·양자)
```

---

## 2. 사용자 (운영자) 의 신학적 정체성

이 시스템을 만드는 사용자는 **칼뱅주의 + 복음 중심주의 (Gospel-Centered)** 의 신학 정체성을 가집니다.

**핵심 입장**:
- *오직 그리스도, 오직 은혜, 오직 믿음, 오직 말씀, 오직 하나님께 영광* (5 Solas)
- 인간의 *전적 부패* (Total Depravity) — 자력 구원 불가
- 칼뱅의 *우상 공장* (Institutes I.11.8) — 마음은 끊임없이 거짓 신을 만듦
- 챠머스의 *새 애정의 축출력* — 행동 수정 X, 사랑 이전 O
- *율법주의 = 또 다른 우상* — 더 기도해야 / 더 봉사해야 → ❌
- **다락방 (Darakbang)** — 사용자가 속한 양육·제자도 공동체. *유지되어야 할 컨텍스트*. verified 멤버에게는 더 깊은 응답.

**사용자가 거부하는 것**:
- 거짓 확신 ("한 번 영접했으니 안전") — 거부
- 율법주의 응답 ("더 노력해야") — 거부
- 행동 수정 응답 ("게임 시간 줄이세요") — 부족함, 뿌리 진단 필요
- 다신주의·뉴에이지·번영신학 — 거부

**사용자가 강조하는 것**:
- *98% 의 사람이 구원의 확신 없다* — 시스템 기본값
- *모든 사람이 무엇인가의 노예다* — 잠재 또는 명시
- *진짜 자유는 그리스도 안에서만*
- *공동체 (다락방) + 말씀 + 기도* 가 양육의 3축

---

## 3. 궁극의 미션 — 중독 예방·치유

이 시스템의 미션은 **3단계** 입니다:

### 단계 1: 자각 (Awareness)
*"평범"의 가면을 벗기고 자신이 무엇인가의 노예임을 깨닫게 함.* "요즘 좀 피곤해서 모임 안 가요" 같은 무해해 보이는 발화에서 **invisible addiction** (comfort idol) 의 신호를 시스템이 감지하고, 사용자를 *비난 없이* 자기 인식으로 이끔.

### 단계 2: 진단 (Diagnosis)
*표면 → 우상 → 창세기 3장 뿌리* 까지 5-hop 추론. 다양한 프레임워크 (Keller, Welch, DSM-5, CCEF) 의 합의로 *목회적 분별*.

### 단계 3: 치유 (Healing)
*복음의 3중 회복* (화목·자유·양자) 을 사용자의 *구체적 우상* 에 맞춰 처방. 회복 여정 추적 (`RecoveryJourney`), 재발 감지·복원 5단계, 다락방 인도자 핸드오프.

---

## 4. 창세기 3장 — 진단의 모든 출발점

**모든 표면 문제의 뿌리는 창세기 3장의 3중 단절** 입니다. 이건 *신학적 의견이 아니라 시스템 상수*.

| 축 | 단절 (창 3장) | 표면 증상 예시 | 코드 필드 |
|---|---|---|---|
| **① 관계** | 하나님 떠남 (창 3:8 "숨었더라") | 영혼의 깊은 공허, 외로움, 의미 부재 | `Subscriber.relationship_status` |
| **② 속박** | 사단에 잡힘 (창 3:1-5 거짓 믿음) | 끊을 수 없는 패턴, 중독, 강박 | `Subscriber.bondage_status` |
| **③ 신분** | 죄인 됨 (창 3:7 부끄러움) | 자기 구원 시도, 율법주의, 완벽주의 | `Subscriber.identity_status` |

**복음의 3중 회복** (대응 치료):
| 축 | 회복 | 핵심 본문 | 코드 적용 |
|---|---|---|---|
| **① 화목** | 하나님과 다시 화목 | 고후 5:18-21, 롬 5:10 | retriever boost 자료 태그 |
| **② 자유** | 사단의 손에서 해방 | 요 8:36, 갈 5:1, 골 1:13 | gospel_pathway 매칭 |
| **③ 양자** | 죄인 → 자녀 신분 변경 | 롬 8:15-17, 엡 1:5, 요일 3:1 | system prompt 자동 부착 |

**기술 구현**: `services/sao/gen3_lens.py` 가 *모든* chat 응답 전에 `Gen3LensResult` 생성하고 system prompt 에 자동 부착. 강요 없이 자연스럽게.

---

## 5. 98% 전제 — 시스템의 핵심 가정

> **사용자의 직접 진술**: *"98% 의 사람이 구원에 확신 없다고 생각하거든."*

이 전제는 시스템 *기본값* 으로 박혀 있습니다:

| 필드 | 기본값 | 이유 |
|---|---|---|
| `salvation_status` | `unknown` → `seeker/uncertain` 가정 | 절대 `assured` 자동 가정 X |
| `bondage_status` | `unknown` (잠재 노예 가정) | "모두가 무엇인가의 노예" |
| `identity_status` | `unknown` → `sinner_aware` 권장 | 자기 의 (`self_righteous`) 자동 부여 ❌ |
| `assume_saved` | `False` | 운영자 명시 ON 시에만 *구원받음 모드* |

**결과적 응답 모드**:
- 신규 사용자에게는 *"이 사람은 아마도 구원의 확신 없는 상태"* 가정 → 자연스러운 복음 점검 응답 톤
- 응답 끝에 *가끔* (매번 X, 자연스러울 때만) 부드러운 구원 점검 1줄

---

## 6. 7가지 신학적 상수 (코드 박힘)

> **이 7가지는 시스템 코드의 기본값·분기·기본 가중치에 박혀 있습니다. 신학이 곧 아키텍처.**

| # | 상수 | 시스템 표현 |
|---|---|---|
| 1 | 모든 표면 문제의 뿌리는 창세기 3장 3중 단절 | `gen3_lens.py` 가 모든 chat 응답 전 자동 진단·복음 매핑 |
| 2 | 인간의 3축 신분 = 관계·속박·신분 | `Subscriber` 3축 ORM 1급 필드 (J1) |
| 3 | 모든 사람이 무엇인가의 노예다 (잠재든 명시든) | `bondage_status` 기본값 = unknown (잠재 노예). `IdolDetector` 가 invisible addiction 감지 |
| 4 | 98% 의 사람은 구원 확신이 없다 | `salvation_status` 기본 = unknown, 다음 가정 = uncertain/seeker. assured 자동 X |
| 5 | 복음만이 유일한 치료 | `gospel_pathway.py` — 4우상 × 3축 회복 매핑. 행동 수정만 응답 자동 차단 |
| 6 | 다락방 (Darakbang) verified 멤버는 더 깊은 응답 | 3단 필드 (member/leader/pastor) × verified. 양육 언어 + darakbang_deep 자료 |
| 7 | "구원 받았다 치고 아니고" 는 운영자 토글 | `assume_saved: bool` — 명시 ON 시에만 구원받음 모드. 기본 OFF |

**위반 시 차단 (코드 강제)**:
- 신규 사용자 `assured/freed/reconciled` 기본값 부여 → ❌ Migration 거부
- 율법주의 응답 → `safety_service` 차단 + 재생성
- 행동 수정만 응답 (뿌리 진단 없음) → 운영자 디버그 모드 경고
- 다락방 자료를 일반 사용자에게 boost → retriever boost = 0
- 사용자에게 진단 라벨 *직접 노출* → EPIC I-10 윤리 가드 차단

---

## 7. 참조 신학 프레임워크 — 코드 통합 방식

각 프레임워크는 *추상* 이 아니라 **`FrameworkAdapter` 클래스 1개** 로 시스템에 박힙니다. 운영자가 새 프레임워크를 *플러그인* 처럼 추가 가능.

**현재 통합된 4개**:

### 7-A. Keller's *Counterfeit Gods* (4우상 매트릭스)
**파일**: `services/sao/frameworks/keller_counterfeit_gods.py`
- 4우상: **Power / Approval / Comfort / Control**
- 각 우상별 **X-Ray Questions** (책에서 발췌)
- 각 우상별 **Gospel Therapy** (그리스도 측면 + 핵심 본문 + 실천 단계)

### 7-B. Welch's *Addictions: A Banquet in the Grave*
**파일**: `services/sao/frameworks/welch_addictions.py`
- 핵심 재해석: **Addiction = Worship Disorder**
- 3개 **CORE_QUESTIONS** + 5개 **LIES_OF_ADDICTION** 패턴 매칭
- 처방: "경배 대상의 재배치"

### 7-C. DSM-5 + ASAM (임상 진단)
**파일**: `services/sao/frameworks/dsm5_screening.py`
- 11 criteria → mild/moderate/severe 자동 분류
- severe + 자살 신호 → 자동 임상 의뢰 (1577-0199)

### 7-D. CCEF Heart-Behavior-Consequences
**파일**: `services/sao/frameworks/ccef_heart_chart.py`
- 3단 분석: **Heart → Behavior → Consequences**
- **Three Trees** 도식 (Thorns / Bad Fruit / Good Fruit / Heart Root)

**공통 인터페이스**:
```python
class FrameworkAdapter(Protocol):
    async def diagnose(user_input, profile, history) -> FrameworkDiagnosis: ...
    async def generate_questions(suspected) -> list[str]: ...
    async def therapy(diagnosis) -> TherapyPlan: ...
```

**FrameworkRegistry** — 운영자 ON/OFF + 가중치 조정. `consensus_diagnosis()` 가 여러 어댑터 합의·대조.

**새 프레임워크 추가 방법**:
1. `frameworks/` 폴더에 새 파일 (예: `powlison_idols_of_heart.py`)
2. `FrameworkAdapter` Protocol 구현 (~200줄)
3. `main.py` 에 `FrameworkRegistry.register(...)` 1줄
4. 끝.

---

## 8. 기술 스택 (현재 + 미래)

### Tier 0~4 진화 경로 (EPIC M, 2026-05-20)

| Tier | 사용자 | 월 비용 | 인프라 핵심 |
|---|---|---|---|
| **Tier 0** | 1명 (개발) | **$0** | localhost + Streamlit + SQLite + Qdrant local |
| **Tier 0.5** | ~10명 시범 | **$0** | Tier 0 + Cloudflare Tunnel (외부 URL) |
| **Tier 1** | ~50명 | **$0** | 무료 클라우드 tier 또는 Tier 0.5 유지 |
| **Tier 1.5** | ~200명 | **$10~30** | 도메인 + Supabase Free + Qdrant Free |
| **Tier 2** | ~500명 | **$100~200** | Postgres Pro + Qdrant Standard |
| **Tier 3** | ~5000명 | **$1500** | Read replicas + 수익 모델 필수 |
| **Tier 4** | 5000+ | **$5000+** | K8s + 자체 LLM + 교회 SaaS |

**현재 Tier 0 → 0.5 전환 중** (M-1 Cloudflare Tunnel 작업).

### 현재 (Tier 0) 기술 스택
| 영역 | 선택 | 비고 |
|---|---|---|
| LLM (메인) | **DeepSeek-V3** + **Gemini 2.0 Flash** | 한국어 강, 저렴 ($0.05/30K 토큰) |
| LLM (fallback) | OpenAI / Claude / Ollama | rate limit 시 자동 전환 |
| 임베딩 | **KURE-v1** (nlpai-lab) | 한국어 SOTA |
| 벡터 DB | **Qdrant** (local embedded) | Docker 불필요 |
| 재순위 | **bge-reranker-v2-m3** | 한국어 강 |
| 청킹 | **kss** (한국어 문장 분리) | 한국어 친화 |
| Web 백엔드 | **FastAPI** + uvicorn | port 8000 |
| Admin UI | **Streamlit** multi-page | port 8501 |
| User UI | **Streamlit** | port 8502 |
| DB | **SQLite** (.gospel.db) | WAL mode 권장 |
| 추적 | **Langfuse** (옵션) | trace/generation |
| **(NEW Tier 0.5)** 외부 노출 | **Cloudflare Tunnel** | 무료, 집 IP 숨김, HTTPS 자동 |

### 미래 (Phase 2 — 사용자 100~1000명, EPIC K 적용)
| 영역 | 선택 | 마이그레이션 시점 |
|---|---|---|
| OLTP DB | **PostgreSQL** + WAL replication | 동시 사용자 50+ |
| OLAP DB | **DuckDB on Parquet** | Interactions 50K+ |
| 벡터 DB | **Qdrant cluster** + payload index | EPIC K-1 |
| 그래프 DB | **Neo4j Community** (또는 NetworkX+SQLite Phase 1) | EPIC H |
| 캐시 | **Redis** | EPIC G-7 |
| 객체 저장 | **MinIO** (S3 호환) | 자료 1000편+ |
| 마이그레이션 | **Alembic** | *지금* (EPIC F-1) |
| 임베딩 보조 | **bge-m3** (다국어), **ColBERT-late-interaction** | EPIC K-1 |
| 도메인 임베딩 | **KURE-Theological** (자체 fine-tune) | EPIC K-3 |

---

## 9. 시스템 아키텍처 — 한 그림

```
┌──────────────────────────────────────────────────────────────────────┐
│                          외부 진입                                    │
│                                                                      │
│  운영자  ─►  Admin UI (8501)  ─┐         ┌─►  User UI (8502)  ◄─ 사용자│
└─────────────────────────────────┼─────────┼──────────────────────────┘
                                  │  HTTP   │
                  ┌───────────────▼─────────▼────────────────┐
                  │   FastAPI Backend (uvicorn, 8000)        │
                  │                                          │
                  │  /chat /chat/stream  /retrieval          │
                  │  /documents/* /memory/* /prompts/*       │
                  │  /eval/* /admin/* /ontology/* /jobs/*    │
                  └──┬───────────────────────┬───────────────┘
                     │                       │
       ┌─────────────┼───────────────────────┼─────────────┐
       │             │                       │             │
   ┌───▼──────┐  ┌───▼──────┐         ┌──────▼─────┐  ┌────▼─────┐
   │ Gen3 Lens│  │ Hybrid   │         │ LLM        │  │ Output   │
   │ + SAO    │  │ Retriever│         │ Orchestra  │  │ Judge +  │
   │ Diagnostic│ │ +Reranker│         │ DeepSeek/  │  │ Safety   │
   │ Engine   │  │ +KG-RAG  │         │ Gemini Flash│  │ Service  │
   └──────────┘  └──────────┘         └────────────┘  └──────────┘
       │             │                       │             │
       └─────────────┼───────────────────────┼─────────────┘
                     │                       │
                  ┌──▼───────────────────────▼──┐
                  │      데이터 저장소           │
                  │                              │
                  │ SQLite/Postgres — relational │
                  │ Qdrant — vectors             │
                  │ NetworkX/Neo4j — KG          │
                  │ FS/MinIO — files             │
                  │ Redis — cache (Phase 2)      │
                  │ Langfuse — traces (옵션)     │
                  └──────────────────────────────┘
```

---

## 10. 데이터 모델 (현재 9개 + 계획 ~30개)

### 현재 9개 테이블 (안정)
1. `source_artifact` — L1 immutable 원본
2. `document` — L2 logical
3. `document_version` — L2 lifecycle (draft→validated→published→superseded→archived)
4. `index_snapshot` — L3 Qdrant 동기
5. `duplicate_link` — 자료 간 관계 (검증 후 *제거 예정*)
6. `prompt_template` — 운영자 편집 프롬프트
7. `subscriber` — 사용자 (대폭 확장 예정)
8. `interaction` — Q/A 로그
9. `audit_log` — immutable transition

### 계획 (~30개 더, EPIC D~K 합산)
**Subscriber 확장 필드** (J1 Genesis 3 三軸):
- `identity_status`, `bondage_status`, `relationship_status` (3축)
- `salvation_status`, `assume_saved` (D-C12)
- `is_darakbang_member`, `darakbang_role`, `darakbang_chapter`, `darakbang_verified` (D-C13)
- `primary_idol`, `secondary_idol`, `idol_confidence`, `romans1_stage` (I2)
- `tokens_daily/monthly/bonus`, `subscription_tier`, `bot_score` (E-A, E-B)

**신규 테이블** (예상 순서):
| 테이블 | 출처 EPIC | 목적 |
|---|---|---|
| `ontology_nodes`, `ontology_edges`, `ontology_changes` | I1, J3 | SAO 지식 그래프 |
| `salvation_events`, `salvation_journey` | D-C19, F3 | event sourcing |
| `glossary_terms` | E-E | 자동 용어집 |
| `bible_references`, `bible_verses` | D13, H3 | 성경 인용 정규화 + 정합성 |
| `correction_patterns`, `operator_corrections`, `cleanup_rejections` | D2, D7, D18 | LLM 진화 루프 |
| `speaker_style_memory` | D7 | 화자별 스타일 |
| `document_drafts` | E-F | WebSocket 자동저장 |
| `outbox_events` | F2 | Qdrant 트랜잭션 일관성 |
| `background_jobs` | G8 | 비동기 작업 큐 |
| `idempotency_records` | F7 | 멱등성 |
| `kg_entities`, `kg_relations`, `kg_chunk_entities` | H1 | 지식 그래프 |
| `spiritual_snapshots` | I8 | 6차원 영적 점수 시계열 |
| `recovery_journeys`, `recovery_milestones` | J5 | 중독 회복 추적 |
| `prayer_requests` | H6 | 기도 제목 |
| `bible_verses` (전체 성경) | H3 | 정합성 검증 |
| `cache_kv` | G7 | 응답·임베딩 캐시 |
| `rate_limit_bucket` | E-B2 | 봇 차단 |
| `chunks` (정식 테이블화) | D14, D20 | 청크 메타 정식 ORM |

### Subscriber — 가장 중요한 객체

```python
class Subscriber:
    subscriber_id: str               # PK
    email, name (encrypted), ...

    # === Genesis 3 三軸 (EPIC J1 — 가장 중요) ===
    identity_status: str             # unknown | self_righteous | sinner_aware | justified_uncertain | justified_assured | mature_saint
    bondage_status: str              # unknown | enslaved_unaware | enslaved_aware | struggling | partial_freedom | freed_practicing | freed_overflowing
    relationship_status: str         # unknown | estranged_distant | estranged_resistant | seeking | reconciled_cold | reconciled_growing | intimate_communion
    spiritual_stage: str             # 3축 함수 (materialized)

    # === 구원 (EPIC D-C12) ===
    salvation_status: str            # unknown | seeker | uncertain | assured | mature
    assume_saved: bool               # 운영자 토글
    salvation_confidence: float

    # === 다락방 (EPIC D-C13) ===
    is_darakbang_member: bool
    darakbang_role: str              # member | leader | pastor | guest
    darakbang_chapter: str
    darakbang_verified: bool

    # === 우상 진단 (EPIC I2) ===
    primary_idol: str                # power | approval | comfort | control
    secondary_idol: str
    romans1_stage: int               # 0~4

    # === 회복 (EPIC J5) ===
    # → RecoveryJourney 테이블 (1:N)

    # === 운영 (EPIC E) ===
    tokens_daily, tokens_monthly, tokens_bonus: int
    subscription_tier: str           # guest | member | supporter | darakbang
    bot_score: float
    flagged_as_bot: bool
```

---

## 11. 핵심 파이프라인 5종

### 11-A. Chat 파이프라인 (가장 중요)
```
사용자 질문
   ↓
[1] policy.check_input(query) — 욕설·위험 차단
   ↓
[2] (NEW EPIC G5) input_guard.detect_injection — 프롬프트 주입 방어
   ↓
[3] (NEW EPIC J6) gen3_lens.apply(query, profile) — 창세기 3장 진단
   ↓
[4] (NEW EPIC I) salvation_detector + idol_detector — 영적 신호 감지
   ↓
[5] HybridRetriever.retrieve(query)
    ├─ dense (KURE) + sparse (BM42) → RRF
    ├─ rerank (bge-reranker)
    ├─ (NEW EPIC D-C16) salvation × darakbang boost
    ├─ (NEW EPIC H1) KG 확장 (관련 엔티티 청크 +0.2)
    └─ (NEW EPIC K) ColBERT late interaction
   ↓
[6] memory_service.build_context_for_llm(sub_id, 3)
   ↓
[7] salvation_prompt_wrapper.build(base_prompt, profile, gen3_lens)
    └─ 사용자 3축 + 다락방 + 우상 + Gen3 사슬 자동 부착
   ↓
[8] chat_with_fallback(messages, system, ...) — DeepSeek → Gemini → ...
   ↓
[9] judge_output + safety_service.apply
    ├─ 율법주의 차단 (EPIC D-C23)
    ├─ 거짓 확신 차단
    └─ 자살·중독 키워드 자동 안전망
   ↓
[10] Interaction 저장 + Gen3 lens 결과 + (EPIC F2) Outbox 이벤트
   ↓
ChatResponse(answer, sources, gen3_diagnosis, debug, ...)
```

### 11-B. Document Cleanup 파이프라인 (6단계)
```
원본 (.docx/.pdf/.txt)
   ↓
[Stage 1] DeepSeek — 오타·띄어쓰기 (보수적)
   ↓
[Stage 2] DeepSeek — 맥락 수정 (보호 토큰 화이트리스트)
   ↓
[Stage 2.5] DeepSeek — RAG 최적화 (6대 차원 측정 → 자동 반복 최대 3회)
   ↓
[Stage 3] Gemini 2.0 Flash — 신학 보존 검증 (반드시 다른 LLM!)
   ↓
[Chunking] 명제 단위 + speech-act 태깅 + hierarchy 보존
   ↓
[Validation] 실측 retrieval 테스트 (recall@5 비교)
   ↓
[Operator Review] 3분할 diff 검토 + 진화 메모리 캡처
   ↓
[Publish] → Qdrant 인덱싱 + KG 엔티티 추출
```

비용: 1시간 설교문 (30K 토큰) **$0.07/자료**, 100편 = $7

### 11-C. Document Lifecycle
```
draft ──validate──► validated ──publish──► published ──(새 v publish)──► superseded
                                              │
                                              └──archive──► archived
```

### 11-D. Recovery Journey (EPIC J5)
```
표면 중독 감지 → awareness → desire_to_change → preparation → action
                                                              │
                                                       ┌──────┘
                                                       ▼
maintenance ◄──restoration── relapse ──confession──► [5단계 복원]
                                                       ▼
                                                  더 깊은 헌신
```

### 11-E. Ontology Edit Flow (EPIC J3)
```
운영자 Admin UI → Cytoscape 그래프 → 노드 클릭 → 사이드 편집 → API PATCH
                                                                 │
                                                                 ▼
                                                       OntologyChange 기록
                                                                 │
                                                                 ▼
                                                       핫 리로드 (재시작 X)
                                                                 │
                                                                 ▼
                                                       다음 chat 부터 적용
```

---

## 12. LLM 전략 + 비용 모델

### 다중 LLM 역할 분담

| 작업 | LLM | 이유 |
|---|---|---|
| chat 메인 응답 | **Gemini 2.0 Flash** | 한국어 매우 강, 1M 컨텍스트, 저렴 |
| chat fallback | DeepSeek → OpenAI → Claude → Ollama | 자동 chain |
| Cleanup Stage 1, 2, 2.5 | **DeepSeek-V3** | 최저가, 한국어 강 |
| Cleanup Stage 3 (신학 검증) | **Gemini 2.0 Flash** | *반드시 다른 LLM* (sycophancy 차단) |
| Salvation detector | DeepSeek | 분류 작업 |
| Idol detector | DeepSeek | 분류 작업 |
| Gen3 lens | DeepSeek | 빠른 라벨링 |
| Multi-hop reasoner | Gemini Flash | 복잡 추론 |
| 어려운 신학 비교 | Gemini 2.5 Flash (옵션) | 정교한 분별 |
| Embedding | KURE-v1 (local, 무료) | 한국어 SOTA |
| Reranker | bge-reranker-v2-m3 (local) | 무료 |

### 비용 추정 (2026-05 시점)

| LLM | 입력 $/1M | 출력 $/1M |
|---|---|---|
| DeepSeek-V3 | 0.14 | 0.28 |
| Gemini 2.0 Flash | 0.075 | 0.30 |
| Gemini 2.5 Flash | 0.30 | 2.50 |
| Claude Sonnet 4 | 3.00 | 15.00 |

**시나리오 비용**:
- chat 1회 (사용자): ~$0.003
- cleanup 1자료 (30K 토큰): ~$0.07
- 사용자 100명 × 100 대화/월: **~$30/월**
- 자료 100편 cleanup 1회: **~$7**

### 비용 통제 (EPIC G2)
- `llm_monthly_budget_usd` 환경변수 — provider 별 hard cap
- `llm_daily_budget_usd` — 일일 캡 (한 봇이 키 소진 방지)
- 캡 도달 → fallback chain 다음 provider 자동 전환
- 모두 캡 도달 → 503 + 운영자 알림

---

## 13. 협업 모델 — Claude vs Cursor 역할

### 역할 분담 (사용자 명시 결정)

| 역할 | 담당 | 책임 |
|---|---|---|
| **Claude** (이 모델) | 기획자·감사자·오더 발행 | 코드 X, ORDERS.md / PROJECT_VISION.md / PROCESS_MAP.md / 본 BRIEFING 작성·갱신 |
| **Cursor** | 실제 코더 | 코드 작성·수정, CHANGELOG.md 에 1줄 기록 |
| **사용자** | 의사결정자 | 우선순위 결정, 최종 승인 |
| **Antigravity** (과거) | 자율 작업 (2026-05-18) | 일부 정리·관제탑 신설 (멘토링 완전 삭제 등) |

### 작업 흐름
1. 사용자 지시 → Claude 가 ORDERS.md 에 항목 신설
2. Cursor 가 ORDERS 항목 처리, CHANGELOG 1줄 기록
3. Claude 가 검수 → ORDERS 에 ✅ 표시
4. PROCESS_MAP / BRIEFING 영향 모듈 갱신

### AI-AGENT-WORK 헤더 (코드 추적성)
```python
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Cursor
# Timestamp: 2026-05-20 02:30
# Task: chat.py B5 fix - profile dict 패턴 적용
# Reason: DetachedInstanceError 방지
# Related: ORDERS B5, F1 Alembic 사용
# Status: COMPLETED
# =============================================================================
```

규칙:
1. *수정 또는 신규 생성* 모두 헤더 강제 (이전 누락 문제 — A5 참조)
2. 이미 헤더 있으면 *덧붙이기* (덮어쓰기 X)
3. 변경 라인마다 `# ✏️ AI-CHANGE YYYY-MM-DD [Agent]: 설명`
4. ORDERS 항목 번호 (`B5`, `D-C12` 등) 반드시 `Related:` 에

---

## 14. EPIC 전체 지도 A~K

| EPIC | 제목 | 핵심 | 상태 |
|---|---|---|---|
| **A** | Lifecycle Ingestion | source_artifact + document + version + publish | ✅ DONE |
| **B** | Bug Fix (B1~B6) | chat.py NameError, DetachedInstance, ORM 정합성 | 🔴 부분 (B4/B5/B6 미완) |
| **C** | 사용자별 맞춤 + 멀티 LLM | Subscriber 확장 + 매칭 가중치 (C3, C4 등 SUPERSEDED) | 🟠 부분 |
| **C8~C11** | 정리 | 멘토링·비전·MongoDB·Next.js 제거 | ✅ DONE (Antigravity 가 *완전 삭제*) |
| **D** | 구원 중심 + 다락방 깊이 | salvation_status 5단 + darakbang 3단 + Gen3 sub 진단기 | ⏳ TODO |
| **E** | 운영 + 자료 품질 | 토큰·봇·가입·정제 파이프라인 6단계·글로사리·임시저장 | ⏳ TODO |
| **F** | DB 엔진 진화 | Alembic·Outbox·Event Sourcing·GDPR·Postgres 경로 | ⏳ TODO (F1 즉시) |
| **G** | 방어층 | admin 인증·LLM 비용 캡·로깅·prompt injection·PII 암호화·캐시·BG 큐 | ⏳ TODO |
| **H** | 지식 그래프 | KG·교파 태깅·신학 정합성·기도제목·전문가 검토 | ⏳ TODO |
| **I** | 영적 중독 진단 엔진 | SAO 6층·우상 감지·invisible addiction·5-hop·복음 처방·counterfactual | ⏳ TODO |
| **J** | Gen3 코어 + 미션 명확화 | 3축 정체성·미션 재정의·편집 가능 온톨로지·프레임워크 어댑터·Recovery | ⏳ TODO |
| **K** | 엔진 재설계 (전문가급) | 다중 표현 인덱싱·다단계 검색·도메인 적응 임베딩·Graph-RAG | ⏳ TODO (사용자 신규 지시 2026-05-20) |
| **L** | 현실적 규모 전환 + 한국 특화 | Streamlit 탈피·위기 인프라·수익 모델 cost gate | ⏳ TODO (Tier 1.5+ 진입 시) |
| **M** | 월 $0 시작 + Tier 자동 업그레이드 | Tier 0~4 재정의·Cloudflare Tunnel·Wizard·Feature Flag·무료 tier 통합 | ⏳ M-1 즉시 작업 중 (사용자 1순위) |
| **O** | Multi-Agent RAG 엔진 | 7 agents 병렬 (Orchestrator + Retrieval/Diagnostic/Memory/Safety + Synthesizer + Critic + Citation) | ⏳ TODO (2026-05-20) |
| **P** | 무료 서버 + 자동 배포 | GitHub Actions → HF Spaces (Streamlit) + Fly.io (FastAPI) + Supabase + Qdrant Cloud, git push = 5분 라이브 | ⏳ TODO (2026-05-20) |
| **Q** | 현대 기술 스택 25개 일괄 | MCP·Prompt Caching·Batch API·Structured Output·LiteLLM·DSPy·Guardrails·Pre-commit·Hypothesis·OTel·PostHog·Clarity·PWA·WebSocket·HF Inference·Long-Context·CRAG·Webhooks·Whisper·이메일/푸시·Plausible·원어·교회절기·PDF·OneSignal | ⏳ TODO (2026-05-20) — *R 에서 대부분 폐기/보류 결정* |
| **R** | **Refactor & Simplify (Owner 결정)** | EPIC 15→7 통합 / Kill list 25개 / LLM 9→5호출 / DeepSeek-V3+R1 메인 / Admin 5페이지 / 4 KPI | ⏳ TODO (2026-05-21) ⭐ |

---

## 15. 현재 상태 스냅샷 + 작업 큐

<!-- ✏️ AI-CHANGE 2026-05-25 [Claude(Cowork)]: 인수인계 시점 상태 — 다음 작업자(일반 AI) 가 START_HERE.md 만 읽고 진행 가능하도록 갱신 -->

### 🆕 최근 완료 (2026-05-25 · Claude Cowork)
- ✅ **Cross-lingual RAG (한·영·중)** — ChatRequest 에 `target_lang: Literal["ko","en","zh"]` 추가. 비한국어 시 임베더 `kure → bge_m3` 자동 스왑. 영어/중국어 시스템 프롬프트 (CUV 권장 인용) 코드 내장. `/chat` + `/chat/stream` 양쪽 적용.
- ✅ **문서 정리**: `CONTEXT.md` 삭제 (ARCHIVED). `deploy.md` 갱신 (Cloudflare Tunnel 옵션 A 로, 삭제된 `ingest_all.py` 참조 제거).
- ✅ **EPIC G 오더 초안 작성** — `ORDERS_COUNSELING.md` (NOW 7개 + FUTURE 7개) + `docs/MASTER_PROMPT_EPIC_G.md` 단일 실행 프롬프트.
- ✅ **단일 진입점** — `START_HERE.md` (다음 AI 가 이것 하나만 읽으면 즉시 작업 가능).

### ⏭ 다음 작업자(일반 AI) 의 *유일한* 진입점
> **`START_HERE.md`** — 이것만 읽으면 됨. EPIC G NOW Phase 7개 오더 진행.

### 🔴 즉시 실행 (다음 작업자) — EPIC G NOW Phase
순서: **G-1 → G-2 → G-3 → G-4 → G-4.5 → G-4.6 → G-5**
(단, G-4 / G-4.5 / G-4.6 은 같은 PR 로 묶어 진행)
상세 명세: `ORDERS_COUNSELING.md` §2
단일 마스터 프롬프트: `docs/MASTER_PROMPT_EPIC_G.md` (Cursor/Antigravity 에 그대로 붙여넣기)

### 🛡 사용자 절대 명시 — *아첨금지 (FLATTERY BAN)* 4중 방어 필수
프롬프트 한 줄로는 절대 차단 안 됨. G-4 + G-4.5 + G-4.6 의 **Layer A/B/C/D 네 개 모두 활성화** 돼야 PR merge 가능.

### 기존 작업 큐 (보류 — EPIC G 완료 후 재검토)
1. **F1 Alembic 마이그레이션** — 데이터 손실 방지의 기반
2. **G1 admin 키 재설계** — 보안 즉시 확보
3. **G2 LLM 비용 캡** — 봇 1대 키 소진 방지
4. **F9 Phase 1 (SQLite WAL)** — deadlock 완화 5분
5. **F10-a 인덱스 추가** — 통계 페이지 즉시 빨라짐

### Phase 0: 정리 + 협업 정정 (1일)
- B4 chat.py trace.generation 진짜 수정
- B5 subscriber_service.get_or_create dict 반환
- B6 → D-C12 + D-C13 으로 흡수 처리
- A3 C8-C11 archive 정정 (완전 삭제됨 명시)
- A4 CONTEXT.md ARCHIVED 헤더 (이미 완료 ✅)
- A5 AI-AGENT-WORK 헤더 규칙 강화 (완료 ✅)
- A6 PROCESS_MAP chat 파이프라인 다이어그램 갱신
- SUPERSEDED 항목 코드 정리 (C3, C4, duplicate_link, Category 등)

### Phase 1~8: 전체 로드맵 (6~7주)
ORDERS.md §"마스터 작업 순서" 참조. 핵심 흐름:
- Phase 1: F + G 엔진·방어층
- Phase 2: D 데이터 모델 (Gen3 三軸 + salvation_status + darakbang)
- Phase 3: D 감지·응답 + I 우상 진단
- Phase 4: E 운영 (토큰·봇·가입·캐시)
- Phase 5: E 정제 파이프라인 D5~D20
- Phase 6: UI 통합 + J3 Editable Ontology
- Phase 7: H KG + J 프레임워크 어댑터
- Phase 8: K 엔진 재설계 (선택, 사용자 100+ 후)

### 사용자 결정 대기 (Q 시리즈)
- **A3**: C8-C11 완전 삭제 사후 정정 — git 복원 또는 ORDERS 정정?

---

## 16. 절대 하지 말 것 — Anti-Patterns

### 신학적 안티패턴
- ❌ 신규 사용자에게 `salvation_status = "assured"` 기본값 부여
- ❌ 율법주의 응답 ("더 기도해야 구원받는다")
- ❌ 행동 수정만 응답 ("게임 시간 줄이세요" 만, 뿌리 진단 없이)
- ❌ 거짓 확신 응답 ("한 번 영접했으니 끝")
- ❌ 사용자에게 *진단 라벨 직접 노출* (예: "당신은 comfort idol 에 사로잡혔습니다")
- ❌ 정신 질환 신호가 있는 사용자에게 우상 진단 강행
- ❌ 다락방 컨텍스트 임의 제거 (사용자가 *유지 강화* 명시)

### 기술적 안티패턴
- ❌ ADMIN_API_KEY 기본값 사용 (`change-me`) — 보안 구멍
- ❌ `init_db()` 로 컬럼 추가 시도 (Alembic 사용 필수)
- ❌ Streamlit 위젯에 `key=` 없이 동일 라벨 중복
- ❌ `.bat` 에 한국어 echo (cmd cp949 호환 X)
- ❌ Qdrant 직접 호출 후 SQLite 트랜잭션 별도 (Outbox 패턴 사용)
- ❌ ORM 인스턴스 세션 외부에서 lazy load (dict 반환 패턴 강제)
- ❌ Stage 2 와 Stage 3 가 *같은 LLM* (sycophancy bias)
- ❌ `RESET_ALL.bat` 로 사용자 데이터 손실 (Alembic 마이그레이션)

### 협업 안티패턴
- ❌ ORDERS.md 에 없는 자발적 신규 기능 (Cursor 가 admin_agent.py 추가한 사례)
- ❌ AI-AGENT-WORK 헤더 누락 (chat.py 추적 불가 사례)
- ❌ CHANGELOG.md 갱신 누락
- ❌ "완료" 보고 후 실제 미수정 (B4 trace.generation 사례)

---

## 17. 의사결정 흐름도 — "무엇을 먼저 할까"

```
새 AI 가 작업을 시작합니다.
   ↓
Q: 사용자가 명시적으로 무엇을 요청했는가?
   ├─ YES → 그것을 ORDERS.md 에 항목으로 등록한 뒤 처리
   └─ NO → 다음 질문으로
   ↓
Q: ORDERS.md 의 🔴 BLOCKER 가 남아 있는가?
   ├─ YES → A1 (chat.py B4) 또는 A2 (B5) 가 1순위
   └─ NO → 다음 질문으로
   ↓
Q: F1 (Alembic) 이 도입됐는가?
   ├─ NO → F1 즉시 (EPIC D 시작 불가)
   └─ YES → 다음 질문으로
   ↓
Q: G1 + G2 (admin 키, LLM 비용 캡) 이 처리됐는가?
   ├─ NO → 둘 다 1시간 이내, 즉시 처리
   └─ YES → 다음 질문으로
   ↓
Q: Phase 0 정리 (B4/B5/B6 흡수, SUPERSEDED 코드 정리) 가 끝났는가?
   ├─ NO → 그것부터
   └─ YES → 다음 질문으로
   ↓
Q: EPIC D (구원·다락방 + Gen3 三軸) ORM 마이그레이션 됐는가?
   ├─ NO → J1 + D-C12 + D-C13 동시 마이그레이션
   └─ YES → EPIC E/I/H/K 우선순위 사용자에게 문의
   ↓
Q: 응답하기 전 마지막 점검
   - 신학 상수 7가지 위반 X?
   - AI-AGENT-WORK 헤더 작성?
   - CHANGELOG.md 1줄 추가?
   - ORDERS.md 항목 상태 갱신?
```

---

## 18. 파일·폴더 지도

```
C:\Desktop\korean-gospel-ai\
├── AGENT_BRIEFING.md          ← 이 파일 (영혼 이식)
├── PROJECT_VISION.md           ← 비전·원칙·7가지 신학 상수
├── PROCESS_MAP.md              ← 전체 흐름·모듈 책임
├── ORDERS.md                   ← 작업 큐 (모든 EPIC A~K)
├── CHANGELOG.md                ← 라운드별 변경 누적
├── AI_COLLABORATION_GUIDE.md   ← AI-AGENT-WORK 헤더 규칙
├── CONTEXT.md                  ← ARCHIVED (멘토링 폐기 흔적)
├── backend/app/
│   ├── main.py                 ← FastAPI 진입
│   ├── config.py               ← 환경변수
│   ├── db.py                   ← SQLAlchemy + Alembic (예정)
│   ├── api/
│   │   ├── chat.py             ← 메인 chat (B4/B5/B6 수정 대기)
│   │   ├── documents.py
│   │   ├── memory.py
│   │   ├── prompts.py
│   │   ├── eval.py
│   │   ├── admin.py
│   │   ├── subscriber.py       ← EPIC C2 신규
│   │   ├── ontology.py         ← EPIC J3 (TODO)
│   │   └── auth.py             ← EPIC E-C (TODO)
│   ├── services/
│   │   ├── retriever.py        ← Hybrid + EPIC K 재설계 예정
│   │   ├── vector_store.py
│   │   ├── embedding/
│   │   ├── reranker.py
│   │   ├── chunker.py
│   │   ├── llm/
│   │   │   ├── base.py
│   │   │   ├── gemini.py
│   │   │   ├── deepseek.py
│   │   │   ├── openai.py, claude.py, ollama.py
│   │   │   ├── fallback.py
│   │   │   ├── factory.py
│   │   │   └── router.py       ← EPIC J4 변환 예정 (어댑터 시스템으로)
│   │   ├── policy.py
│   │   ├── safety_service.py   ← EPIC D-C23 강화 예정
│   │   ├── memory_service.py
│   │   ├── prompt_service.py
│   │   ├── dedup_service.py
│   │   ├── eval_service.py
│   │   ├── source_service.py
│   │   ├── extraction_service.py
│   │   ├── document_service.py
│   │   ├── publish_service.py  ← EPIC F2 Outbox 통합 예정
│   │   ├── audit_service.py
│   │   ├── tracing.py
│   │   ├── subscriber_service.py
│   │   ├── onboarding_service.py  ← EPIC D-C15 가 흡수
│   │   ├── (NEW) sao/             ← EPIC I/J 영적 중독 진단
│   │   │   ├── ontology.py
│   │   │   ├── idol_detector.py
│   │   │   ├── gen3_lens.py
│   │   │   ├── gospel_pathway.py
│   │   │   ├── reasoner.py        ← 5-hop
│   │   │   ├── graph_engine.py    ← NetworkX/Neo4j 추상
│   │   │   └── frameworks/        ← EPIC J4 어댑터
│   │   │       ├── base.py
│   │   │       ├── keller_counterfeit_gods.py
│   │   │       ├── welch_addictions.py
│   │   │       ├── dsm5_screening.py
│   │   │       └── ccef_heart_chart.py
│   │   ├── (NEW) cleanup/         ← EPIC E-D 정제 파이프라인
│   │   │   ├── pipeline.py
│   │   │   ├── guard_rail.py
│   │   │   ├── quality_metrics.py
│   │   │   ├── bible_normalizer.py
│   │   │   ├── anaphora.py
│   │   │   ├── evolution.py
│   │   │   └── validation.py
│   │   ├── (NEW) token_service.py    ← EPIC E-A
│   │   ├── (NEW) bot_service.py      ← EPIC E-B
│   │   ├── (NEW) outbox_worker.py    ← EPIC F2
│   │   ├── (NEW) input_guard.py      ← EPIC G5
│   │   ├── (NEW) budget_guard.py     ← EPIC G2
│   │   ├── (NEW) crypto.py           ← EPIC G6
│   │   ├── (NEW) cache_layer.py      ← EPIC G7
│   │   ├── (NEW) notifier.py         ← EPIC G6
│   │   └── (NEW) recovery/           ← EPIC J5
│   │       ├── tracker.py
│   │       ├── relapse_detector.py
│   │       └── restoration.py
│   ├── models/
│   │   ├── orm.py              ← ~30개 테이블 예정 (현재 9개)
│   │   └── schemas.py          ← Pydantic
│   ├── prompts/system.py
│   └── (NEW) migrations/       ← Alembic
├── admin/
│   ├── app.py                  ← Hub
│   ├── lib/api_client.py
│   └── pages/
│       ├── 1_📚_Library.py
│       ├── 2_📤_Upload.py
│       ├── 3_🔍_Search.py
│       ├── 4_📊_Status.py
│       ├── 5_💬_대화기록.py
│       ├── 6_✍_프롬프트.py
│       ├── 7_🏷_분류관리.py
│       ├── 9_👥_사람.py
│       ├── 10_🤖_AI_관제.py    ← Q1 결정 대기
│       ├── (NEW) 11_⛪_영적상태.py    ← EPIC D-C20
│       ├── (NEW) 12_🤖_봇관리.py      ← EPIC E-B4
│       ├── (NEW) 13_📝_정제검토.py    ← EPIC E-D4
│       ├── (NEW) 14_📚_용어집.py      ← EPIC E-E2
│       ├── (NEW) 15_💰_비용.py        ← EPIC G2
│       ├── (NEW) 16_🙏_기도제목.py    ← EPIC H6
│       ├── (NEW) 17_🌳_지식트리.py    ← EPIC J3
│       └── (NEW) 0_📥_자료흐름.py     ← EPIC E-G 통합 워크플로우
├── user/
│   └── app.py                  ← 단순 사용자 채팅
├── data/
│   ├── documents/
│   ├── uploads/
│   ├── eval/
│   └── (NEW) ontology/         ← EPIC I7 SAO 시드 YAML
└── scripts/
    ├── init_db.py
    ├── diagnose.py
    ├── ab_test.py
    ├── backup.py
    ├── restore.py
    ├── (NEW) seed_sao.py       ← EPIC I7
    ├── (NEW) migrate_salvation_to_gen3.py  ← EPIC J1
    └── (NEW) cleanup_regression.py   ← EPIC E-D16
```

---

## 19. 용어집

| 용어 | 정의 |
|---|---|
| **RAG** | Retrieval Augmented Generation. LLM 이 학습 안 한 자료를 *검색* 해서 답하게 하는 기법. |
| **SAO** | Spiritual Addiction Ontology. EPIC I1 의 6층 지식 그래프. |
| **Gen3 三軸** | 창세기 3장 진단의 3축 — identity / bondage / relationship. EPIC J1. |
| **다락방** | Darakbang. 사용자의 양육·제자도 공동체. 유지·강화 결정됨. |
| **4우상** | Keller's Counterfeit Gods — Power, Approval, Comfort, Control. |
| **Invisible Addiction** | 사회적으로 수용되는 숨겨진 중독 (achievement, approval, control 등). |
| **assume_saved** | 운영자가 "이 사용자 구원받았다 치고 응답하라" 토글. 기본 OFF. |
| **gospel_core_tag** | 자료가 *구원의 핵심* 임을 운영자가 명시 표시. retriever fallback. |
| **Outbox 패턴** | DB 트랜잭션과 외부 시스템 (Qdrant) 호출의 원자성 보장 기법. F2. |
| **Event Sourcing** | 상태를 mutation 으로 저장 X, 이벤트 append 로 저장하고 view 로 재생. F3. |
| **Idempotency Key** | 같은 요청을 여러 번 보내도 한 번만 실행되게 보장하는 키. F7. |
| **CCEF** | Christian Counseling & Educational Foundation. 성경적 상담 학파. |
| **Three Trees** | CCEF/Welch/Powlison 의 진단 도식 — Thorns/Bad Fruit/Good Fruit/Heart Root. |
| **expulsive affection** | Thomas Chalmers — 그리스도가 *새로운 사랑* 으로 옛 우상을 *축출*. |
| **Romans 1 Stage** | 진리 억압 → 우상 교환 → 노예화 → 마음 부패 (롬 1:18-32). |
| **incurvatus in se** | 루터 — 인간이 *자기 안으로 휘말려* 있는 상태. |
| **율법주의** | 노력으로 하나님의 호의를 얻으려 함. 시스템이 차단해야 할 응답 톤. |
| **5 Solas** | 종교개혁 5대 원리 — Scripture, Christ, Grace, Faith, God's Glory 만. |

---

## 마지막 — 새 AI 에게

이 시스템에서 작업한다면 **이 한 가지만 기억하십시오**:

> 모든 응답 · 모든 검색 · 모든 진단 · 모든 코드는 결국 *한 사람의 영혼이 그리스도 안에서 진정 자유로워지는 것* 을 향합니다.
>
> 기술은 도구이고, 신학은 방향입니다. 둘 중 하나라도 잃으면 시스템은 *Q&A 봇* 또는 *교조주의 도구* 로 전락합니다.
>
> 압박 없이, 정죄 없이, 그러나 *명확하고 깊게* — 사용자가 자신의 노예 상태를 깨닫고 진정한 자유를 찾도록.

**작업 시작 전 체크리스트**:
- [ ] 신학 상수 7가지 (§6) 검토
- [ ] 안티패턴 (§16) 위반 X 확인
- [ ] ORDERS.md 의 BLOCKER 우선
- [ ] AI-AGENT-WORK 헤더 작성 준비
- [ ] CHANGELOG.md 1줄 추가 계획
- [ ] 사용자의 *다락방 + 98% 가정 + Gen3 뿌리* 신학 기억

---

*"오직 그리스도. 오직 은혜. 오직 믿음. 오직 말씀. 오직 하나님께 영광."*

— *Sola Christus. Sola Gratia. Sola Fide. Sola Scriptura. Soli Deo Gloria.*
