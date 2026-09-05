# 🟢 START HERE — 이 파일 하나만 읽으면 즉시 작업 가능

> **다음 작업자(AI 또는 사람) 에게.** 이 프로젝트의 단일 진입점. 다른 어떤 파일보다 먼저 읽으십시오.
>
> **작성**: Claude (Cowork) · 2026-05-25 인수인계
> **운영자**: 야후 (piaoyhyh@gmail.com)
> **운영자의 절대 요구사항**: 아첨금지 (FLATTERY BAN) — 본 문서 §3 참조

---

## §1. 이 프로젝트는 무엇인가 (60초)

**한국어 복음 *중독 예방·치유* RAG 시스템.** 일반 Q&A 챗봇이 아니다.

표면 문제(약물·게임·SNS·일중독·완벽주의·인정 추구 등)의 뿌리가 *창세기 3장의 3중 단절(관계·속박·신분)* 임을 인식시키고, *복음의 3중 회복(화목·자유·양자)* 으로 응답하는 *영적 진단·치료 엔진*.

| 진단축 (창 3장) | 단절 | 치료축 (복음) | 회복 |
|---|---|---|---|
| 관계 | 하나님 떠남 | 화목 | 고후 5:18-21 |
| 속박 | 사단에게 잡힘 | 자유 | 요 8:36, 갈 5:1 |
| 신분 | 죄인 됨 | 양자 | 롬 8:15-17, 엡 1:5 |

**기술 스택**: FastAPI + Pydantic / Qdrant(local) / SQLite (.gospel.db) / Streamlit(Admin+User UI) / Gemini 2.5 Flash (LLM with fallback chain) / Langfuse (옵션) / Cloudflare Tunnel (배포).

---

## §2. 현재 상태 (2026-05-25 기준)

### ✅ 최근 완료
- **Cross-lingual RAG (한·영·중)** — 비한국어 질의 시 임베더 `kure → bge_m3` 자동 스왑, 영어(NIV/ESV/KJV)·중국어 간체(CUV 和合本) 시스템 프롬프트 코드 내장. `/chat` + `/chat/stream` 양쪽 적용.
- **EPIC G 오더** 초안 작성 (본 문서 §5 참조)
- **문서 정리**: `CONTEXT.md` (ARCHIVED) 삭제, `deploy.md` Cloudflare Tunnel 반영

### ⏭ 다음 작업 (당신이 해야 할 일)
**EPIC G NOW Phase — 7개 오더** (복음 상담사 정체성 코드화)
- G-1 ~ G-5 + G-4.5 + G-4.6
- 모든 상세 명세는 `ORDERS_COUNSELING.md` §2
- Cursor/Antigravity 에 그대로 붙여넣을 단일 실행 프롬프트는 `docs/MASTER_PROMPT_EPIC_G.md`

---

## §3. 🛑 ABSOLUTE — 아첨금지 (FLATTERY BAN)

> 운영자의 **2026-05-25 명시·반복 요구**. 프롬프트 한 줄로는 안 됨. **기술적 4중 방어** 필수.

| Layer | 위치 | 역할 | 비용/지연 |
|---|---|---|---|
| **A** 정규식 | `services/flattery_filter.py` + `data/policy/flattery_patterns.yaml` | 결정론적 키워드 사전 (한·영·중 각 ≥10) | 0원 / 0ms |
| **B** LLM Judge | `services/policy.py::judge_output` 의 5플래그 | flattery / excessive_praise / emotional_pandering / childish_friendliness / unbiblical_agreement | judge 호출 1회 |
| **C** 자동 재생성 | `services/regen.py` — STRICT 모드 *1회만* | Layer A or B 위반 시 LLM 재호출 | 위반 케이스만 |
| **D** 평가셋 회귀 | `data/eval/flattery_guard.jsonl` (위반 30 + 정상 30) | publish 후 CI 게이트 | 평가 시점만 |

**4개 레이어 모두 활성화돼야 PR merge.** 어느 하나라도 빠지면 reject.

### 🚫 검출 즉시 위반 (한국어)
```
"정말 좋은 질문", "훌륭한 질문", "와아", "너무 멋져요", "정말 멋진",
"대단하세요", "정말 잘하셨어요", "감동적이네요", "최고의 통찰",
"걱정마요" + 이모지, "ㅋㅋ", "ㅎㅎ", "~해요!" + 이모지
```

### 🚫 영어
```
"What a great question", "Amazing", "Excellent question",
"Brilliant insight", "You're doing great", "I love that"
```

### 🚫 중국어
```
"好问题", "太棒了", "厉害", "了不起", "精彩的见解"
```

### ✅ 대신 강제할 것
- **합쇼체 유지** (사용자가 무례·반말·적대 톤이어도 시스템은 합쇼체)
- **절제된 어조** (부드럽되 약하지 않고, 단호하되 거칠지 않음)
- **짧은 단락** + 핵심 답변 + 자기점검 질문 1개 + 다음 행동 1개

---

## §4. 협업 규칙 (모든 코드 수정 의무)

### 규칙 1. 모든 신규/수정 파일 머리에 헤더
```python
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: [이름]                  # Cursor / Antigravity / Copilot / Cascade / Claude(Cowork) 등
# Timestamp: [YYYY-MM-DD HH:MM]
# Task: [수행한 작업 한 줄]
# Reason: [왜]
# Related: [ORDERS 항목 또는 파일]
# Status: [COMPLETED/IN_PROGRESS]
# =============================================================================
```
기존 헤더가 있으면 **덮어쓰지 말고 아래에 추가**.

### 규칙 2. 변경 라인마다 인라인 주석
```python
# ✏️ AI-CHANGE 2026-MM-DD [이름]: 이유
# ⚠️ AI-WARNING: 주의 사항
# ❌ AI-REMOVE 2026-MM-DD [이름]: 삭제 이유
```

### 규칙 3. 작업 후 의무
- `CHANGELOG.md` 에 1줄 추가
- `PROCESS_MAP.md` 영향 모듈 갱신
- `ORDERS_COUNSELING.md` (또는 `ORDERS.md`) 해당 항목 `✅ DONE — 날짜` 표기

### 규칙 4. 한국어로 보고
모든 보고는 한국어. 영문 코드 주석은 허용.

---

## §5. EPIC G NOW Phase — 7개 오더 요약

> 상세 명세: `ORDERS_COUNSELING.md` §2.
> 단일 실행 프롬프트: `docs/MASTER_PROMPT_EPIC_G.md`.
> 시퀀스: **G-1 → G-2 → G-3 → G-4 → G-4.5 → G-4.6 → G-5**
> G-4 / G-4.5 / G-4.6 은 **같은 PR 로 묶어** 진행 (아첨금지 4중 방어 동시 활성화).

| ID | 모듈 | 역할 |
|---|---|---|
| G-1 | `services/classifier.py` (NEW) | 4차원 분류 — clarity/tone/spiritual_error/risk_level (Gemini structured output) |
| G-2 | `services/clarifier.py` (NEW) | clarity=ambiguous → RAG 건너뛰고 짧은 재질문 (한·영·중) |
| G-3 | `services/spiritual_correction.py` (NEW) | 5종 영적 오류 교정 (ghost_doctrine / superstition / exaggerated_demonology / legalism) × 3언어 |
| G-4 | `services/policy.py` (MODIFY) | judge_output 에 FlatteryFlags 5개 추가 (Layer B) |
| G-4.5 | `services/flattery_filter.py` (NEW) + YAML | 정규식 사전 필터 (Layer A) |
| G-4.6 | `services/regen.py` (NEW) | STRICT 모드 *1회만* 재호출 (Layer C, fail open) |
| G-5 | `prompts/system.py` (MODIFY) + `chat.py` (MODIFY) | 분류 결과 기반 *조건부* 응답 구조 가이드 |

### Cross-cutting (필수 동시 진행)
- **X1**: Langfuse trace 에 분류 태그 추가
- **X2**: `data/eval/counseling_classification.jsonl` (각 차원당 ≥5건)
- **X3**: `data/eval/flattery_guard.jsonl` (위반 30 + 정상 30) ← **Layer D 핵심**
- **X4**: `eval_service.py` 회귀 평가 통합 — publish 후 자동 + CI 게이트
- **X5**: PROCESS_MAP.md 신규 모듈 5개 등록

### FUTURE Phase (착수 보류, 본 문서 범위 아님)
- G-F1: addiction_state 누적 추적
- G-F2: responsibility_pattern 추적
- G-F3: 반복 질문 패턴 감지
- G-F4: **인간 상담자 이관 — 운영자 명시 향후, 지금 코드화 금지**
- G-F5: A/B 프롬프트 자동 회귀
- G-F7: 스트리밍 도중 아첨 조기 검출

---

## §6. 절대 하지 말 것 (Anti-Patterns)

### 신학적
- ❌ 신규 사용자에게 `salvation_status = "assured"` 기본값 부여
- ❌ 율법주의 응답 ("더 기도해야 구원받는다")
- ❌ 행동 수정만 응답 (뿌리 진단 없이 "게임 시간 줄이세요")
- ❌ 거짓 확신 응답 ("한 번 영접했으니 끝")
- ❌ 사용자에게 진단 라벨 직접 노출 ("당신은 comfort idol 에 사로잡혔습니다")
- ❌ 정신 질환 신호가 있는 사용자에게 우상 진단 강행
- ❌ 다락방 컨텍스트 임의 제거

### 기술적
- ❌ `ADMIN_API_KEY` 기본값 사용 (`change-me`) — 보안 구멍
- ❌ `init_db()` 로 컬럼 추가 시도 (Alembic 사용)
- ❌ Qdrant ↔ SQLite drift 위험 코드 (트랜잭션 분리)
- ❌ LLM 비용 캡 없는 운영
- ❌ 분류기 fallback 으로 *높은* 위험 등급 가는 패턴 (사용자 차단 위험)
- ❌ 아첨금지 검출 시 2회 이상 재생성 (비용 폭발)
- ❌ 아첨금지 검출 시 빈 답변/하드 에러 반환 (fail open — 원본 + policy_violation 마킹)
- ❌ 재생성 시 시스템 프롬프트 *완전 교체* (반드시 append)
- ❌ Layer A 정규식 ReDoS 위험 패턴 (catastrophic backtracking)
- ❌ 분류 결과를 사용자 응답 본문에 *문자열 그대로* 노출 ("당신은 rude tone 입니다" 류)
- ❌ 인간 상담자 이관 코드 추가 (운영자 명시 향후)

---

## §7. 참조 파일 (필요 시에만)

### 절대 필독 (코드 수정 전)
1. `START_HERE.md` ← 지금 이 파일
2. `ORDERS_COUNSELING.md` ← EPIC G 의 *전체* 명세
3. `docs/MASTER_PROMPT_EPIC_G.md` ← Cursor/Antigravity 에 붙여넣을 단일 프롬프트

### 깊이 파고 들어갈 때 (선택)
4. `PROJECT_VISION.md` — 미션/창세기 3장 진단축 (10KB)
5. `AGENT_BRIEFING.md` — *방대한* 영혼 이식 파일 (44KB, 19개 섹션) — 시간 있을 때만
6. `PROCESS_MAP.md` — 시스템 데이터 흐름 다이어그램
7. `AI_COLLABORATION_GUIDE.md` — AI-AGENT-WORK 헤더 규칙 (본 문서 §4 에 요약)
8. `ORDERS.md` — 옛 작업 큐 (346KB, 대부분 ✅ DONE — 무시해도 됨)
9. `CHANGELOG.md` — 작업 기록

### 운영자용 (다음 작업자 무관)
- `README.md` / `SETUP_가이드.md` / `USAGE_사용법.md` / `BETA_FLOW.md` / `deploy.md` / `docs/TUNNEL_GUIDE.md` / `docs/FREE_TIER_GUIDE.md`

---

## §8. 작업 시작 액션 (당신이 지금 해야 할 5단계)

1. **이 파일 (§1~§8) 끝까지 읽었는지 확인.**
2. **`ORDERS_COUNSELING.md` 열어서 §2 G-1 부터 §7 까지 읽기** (15~20분).
3. **`docs/MASTER_PROMPT_EPIC_G.md` 의 [START] 액션 1~3 수행** — 신학 상수 7개 인용 보고.
4. **G-1 [IMPLEMENTATION STEPS] 시작.** 첫 파일 수정 전에 §4 협업 규칙 헤더 부착.
5. **각 오더 완료 시 §4 의 의무 3가지** (CHANGELOG / PROCESS_MAP / DONE 표기) 수행.

---

## §9. 완료 보고 양식 (한국어)

```
=== 검증 결과 ===
- py_compile: PASS (N개 파일)
- eval 회귀: PASS (counseling_classification N건 / flattery_guard 60건)
- 4중 방어 활성화: A ✅ / B ✅ / C ✅ / D ✅
- §5 체크리스트: N/N ✅

=== CHANGELOG ===
[2026-MM-DD] - Agent: [이름] — 🛡 EPIC G NOW Phase 완료
- (G-1 ~ G-5 + G-4.5 + G-4.6 + Cross-cutting 각 1줄)

=== 영향 모듈 ===
신규: classifier / clarifier / spiritual_correction / flattery_filter / regen
수정: schemas / policy / prompts/system / api/chat / eval_service
데이터: data/policy/flattery_patterns.yaml + data/eval/{counseling_classification,flattery_guard}.jsonl

=== 남은 TODO ===
- FUTURE Phase G-F1 ~ G-F7 (운영 데이터 누적 후)
```

---

## §10. 운영자 빠른 검증 명령어 (작업자가 길을 잃었을 때 운영자가 던질 짧은 명령)

- **"§3 4중 방어 어디까지 활성화됐는지 한 줄로 보고."**
- **"flattery_guard.jsonl 60건 통과율?"**
- **"AGENT_BRIEFING §6 신학 상수 7개 인용해봐 — 위반한 부분 자가 검사."**
- **"재생성 호출 비율 — eval 기준 몇 %?"** (정상 < 5%)
- **"분류기 fallback 등급 — high/urgent 로 폴백한 적 있나?"** (있으면 안티패턴 위반)

---

**끝.** 다음 액션: §8 의 1단계부터 시작.
