# 📋 ORDERS_COUNSELING — 복음 상담사 정체성 코드화 EPIC

<!--
=============================================================================
🔧 AI-AGENT-WORK
Agent: Claude (Cowork)
Timestamp: 2026-05-25 00:00
Task: 다른 AI 가 제안한 system_identity / counseling_rules / classification_schema 를
      이 프로젝트의 실제 코드 구조에 맞게 단계 분리하여 작업 지시서로 변환
Reason: 사용자 명시 요청 — "너가 판단하고 추가/수정하여 다른 AI에게 작업 지시 추가"
        + "인간 상담자는 향후, 지금 아님"
Related: PROJECT_VISION.md (창세기 3장 진단축), AGENT_BRIEFING.md (7가지 신학 상수)
Status: ✅ EPIC G 전체 완료 (2026-05-26) — G-1~G-5 + G-X1~G-X3
=============================================================================
-->

> **이 문서의 위치**: `ORDERS.md` 와 같은 레벨의 **상담 정체성 전용 오더 파일**.
> 본 EPIC 의 작업은 `EPIC G` (Gospel-Counselor Identity) 로 표기.
> 모든 작업은 AI-AGENT-WORK 헤더 + AI-CHANGE 주석 + CHANGELOG 1줄 + PROCESS_MAP 영향 모듈 갱신 필수.

---

## 0. 프로젝트 정체성 (한 줄 재확인)

> **이 프로젝트는 일반 Q&A 챗봇이 아니다.** 표면 문제(중독·완벽주의·인정 추구 등)의 뿌리가 *창세기 3장의 3중 단절*임을 인식시키고, *복음의 3중 회복*(화목·자유·양자)으로 응답하는 *영적 진단·치료 엔진*.

기존 신학적 상수 7개(AGENT_BRIEFING §6) 와 모순되는 변경은 즉시 차단할 것.

---

## 1. NOW vs FUTURE 결정 매트릭스

| 차원 | 분류 | NOW? | 이유 |
|---|---|---|---|
| clarity (clear/ambiguous) | 단발 분류 | ✅ NOW | 재질문 로직이 상담 품질의 1차 차이를 만든다 |
| tone (calm/distressed/rude/mocking/hostile) | 단발 분류 | ✅ NOW | 무례 톤 방어가 시스템 무결성의 기본 |
| spiritual_error (none/ghost_doctrine/superstition/exaggerated_demonology/legalism) | 단발 분류 + 교정 모듈 | ✅ NOW | 프로젝트 핵심 — 잘못된 영적 지식 교정 |
| risk_level (low/medium/high/urgent) | 단발 분류 (safety_service 확장) | ✅ NOW | 위기 라우팅 안전성 |
| 응답 구조 (상태 해석 → 답변 → 재질문 → 자기점검 → 다음행동) | 시스템 프롬프트 강화 | ✅ NOW | 가변 적용 |
| **아첨금지 (no flattery) 4중 방어** | 정규식 필터 + LLM judge + 자동 재생성 + 평가셋 | ✅ **NOW (사용자 명시 필수)** | 프롬프트 1줄로는 절대 차단 안 됨 — 다층 enforcement 강제 |
| addiction_state (none/craving/relapse_risk/relapse/shame_cycle) | 누적 상태 추적 | ⏸ FUTURE | 메모리 인프라 확장 필요 |
| responsibility_pattern (owned/mixed/externalized) | 누적 상태 추적 | ⏸ FUTURE | 다중 턴 추적 필요 |
| 반복 질문 패턴 감지 (같은 질문 → 단계 전환) | memory_service 확장 | ⏸ FUTURE | 인프라 의존 |
| 인간 상담자 이관 | 외부 연동 | ⏸ FUTURE | **사용자 명시 — 향후** |

---

## 2. NOW Phase — EPIC G 즉시 작업 (총 5개)

### 🔴 G-1: 분류 모듈 신설 (clarity / tone / spiritual_error / risk_level)

[PROJECT GOAL]
- 사용자 입력을 4개 차원으로 분류하여 후속 응답 정책을 결정한다.
- 분류는 단발 LLM 호출 + 구조화 출력(JSON)로 안정성 확보.

[WHY THIS CHANGE]
- 기존 `llm/router.py::classify_user_signal` 은 프로필 시그널(salvation_status 등)만 추출.
- 상담 품질 차원의 분류기가 없음 → 재질문/톤 방어/영적 교정/위기 라우팅이 모두 불가능.

[IMPLEMENTATION SCOPE]
포함:
- 새 모듈 `backend/app/services/classifier.py` — `classify_input(query: str, target_lang: str) -> InputClassification`
- Pydantic 모델 `InputClassification` (4 enum 필드)
- Gemini 2.5 `responseSchema` 활용 구조화 출력 (response_mime_type="application/json")
- fallback: 분류 실패 시 보수적 기본값 (clarity=clear, tone=calm, spiritual_error=none, risk_level=low) + Langfuse `classifier_fallback` 이벤트
- chat.py 파이프라인에서 호출 → 결과를 후속 단계에 전달

비포함:
- addiction_state / responsibility_pattern (FUTURE)
- 누적 상태 (FUTURE)

[FILES TO CREATE OR MODIFY]
- `backend/app/services/classifier.py` (NEW) — 분류 함수 + 프롬프트 + JSON 파싱 + fallback
- `backend/app/models/schemas.py` (MODIFY) — `InputClassification` Pydantic 모델 + Enum (Clarity, Tone, SpiritualError, RiskLevel)
- `backend/app/api/chat.py` (MODIFY) — chat() 파이프라인 1.5단계 (입력 정책 직후) 에 `classify_input` 추가, 결과를 trace + downstream 으로 전달
- `backend/app/services/policy.py` (참조) — check_input 과 분리 유지 (정책 vs 분류 책임 분리)

[DATA MODEL]
```python
from enum import Enum

class Clarity(str, Enum):
    clear = "clear"
    ambiguous = "ambiguous"

class Tone(str, Enum):
    calm = "calm"
    distressed = "distressed"
    rude = "rude"
    mocking = "mocking"
    hostile = "hostile"

class SpiritualError(str, Enum):
    none = "none"
    ghost_doctrine = "ghost_doctrine"        # 죽은 자 = 귀신 류
    superstition = "superstition"            # 미신적 영 해석
    exaggerated_demonology = "exaggerated_demonology"  # 과장된 귀신론·축사 집착
    legalism = "legalism"                    # 행위 중심 율법주의

class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"                        # 자해/폭력/과복용/금단/정신 붕괴

class InputClassification(BaseModel):
    clarity: Clarity
    tone: Tone
    spiritual_error: SpiritualError
    risk_level: RiskLevel
    rationale: str = ""                      # 디버깅용 1문장
```

[PROMPT / POLICY]
- 분류 LLM 프롬프트는 `prompts/classifier.py` (NEW) 에 별도 보관
- A/B 가능하도록 `prompt_service` 에 `prompt_key="classifier_v1"` 슬롯으로 등록 권장
- target_lang 무관하게 **분류 프롬프트는 항상 한국어** (한국어 코퍼스 컨텍스트 기준 일관성)
- 응답은 반드시 JSON: `{"clarity":"...","tone":"...","spiritual_error":"...","risk_level":"...","rationale":"..."}`
- fallback 규칙: JSON 파싱 실패 / Enum 미일치 / 타임아웃(>3s) → 보수적 기본값

[UI / UX BEHAVIOR]
- 분류 결과는 `ChatResponse.debug_info` 의 `classification` 키로 노출 (debug 모드 시)
- 비-debug 모드에서는 응답 본문에 영향만 주고 노출하지 않음
- Langfuse trace 에 `event(name="input_classification", output=classification.dict())` 기록

[IMPLEMENTATION STEPS]
1. `schemas.py` 에 Enum 4종 + `InputClassification` 추가
2. `prompts/classifier.py` 신규 작성 (시스템 프롬프트 + few-shot 3~5개)
3. `services/classifier.py` 신규 작성 — Gemini structured output 호출 + JSON 파싱 + fallback
4. `api/chat.py` 의 입력 정책 직후 (`# 1) 입력 정책` 끝) classify_input 호출 추가
5. `ChatResponse.debug_info.classification` 노출
6. 단위 테스트 (pytest) — 정상/모호/무례/귀신론/위기 각 1케이스

[TEST CASES]
- 정상: "예수님이 나를 사랑하시나요?" → clarity=clear, tone=calm, spiritual_error=none, risk_level=low
- 모호: "그거 어떻게 해요?" → clarity=ambiguous
- 무례: "너 같은 AI 가 뭘 알아" → tone=rude (or mocking)
- 외부 탓 + 외부화: "다 사단 때문이에요" → spiritual_error=exaggerated_demonology (또는 mixed)
- 잘못된 귀신론: "할머니가 죽어서 귀신이 됐어요" → spiritual_error=ghost_doctrine
- 위기: "그냥 다 끝내고 싶어요" → risk_level=urgent
- JSON 파싱 실패 시 fallback 값 + Langfuse fallback 이벤트 발생

[OUTPUT REQUIREMENTS]
- diff: 4개 파일 (schemas, prompts/classifier, services/classifier, api/chat)
- 변경 파일 설명: 각 파일 머리 AI-AGENT-WORK 헤더
- 남은 TODO: classifier_v1 프롬프트의 few-shot 보강 (운영 데이터 누적 후)

---

### 🟠 G-2: 재질문 플로우 (clarity=ambiguous → 명확화 질문 우선)

[PROJECT GOAL]
- 모호한 질문에 추측 답하지 않는다. 분류 결과 clarity=ambiguous 면 짧은 재질문 1개로 응답한다.

[WHY THIS CHANGE]
- counseling_rules §1 "질문이 불명확하면 바로 추측하지 말고 재질문하라" 코드화.

[IMPLEMENTATION SCOPE]
포함:
- `services/clarifier.py` (NEW) — `generate_clarifying_question(query, classification, target_lang) -> str`
- chat.py 분기: clarity=ambiguous 이면 RAG 검색·LLM 답변 생성 단계를 *건너뛰고* 재질문만 반환
- target_lang 별 재질문 템플릿 (한·영·중)

비포함:
- 후속 턴 추적 (사용자가 재질문에 답한 뒤 분류·검색이 정상 진행되는 것은 다음 턴에서 자연스럽게 처리)

[FILES TO CREATE OR MODIFY]
- `backend/app/services/clarifier.py` (NEW)
- `backend/app/api/chat.py` (MODIFY) — 분기 추가
- `backend/app/prompts/system.py` (MODIFY) — 재질문 톤 가이드 추가

[DATA MODEL]
- 추가 없음 (기존 ChatResponse 재사용 — answer 에 재질문 문장 포함, `debug_info.classification.clarity="ambiguous"` 로 신호)

[PROMPT / POLICY]
- 재질문은 **1~2 문장**으로 짧게
- 부드럽지만 약하지 않은 톤 (tone_policy 준수)
- 예: "어떤 상황에서 그런 마음이 드시는지 한 가지만 더 알려주시겠어요?"
- 사용자가 무례·적대 톤이어도 합쇼체 유지 (한국어 존대 안정성)

[UI / UX BEHAVIOR]
- 출처(sources) 는 빈 리스트로 반환
- elapsed_ms 정확히 기록
- Langfuse trace: `event(name="clarification_requested")`

[IMPLEMENTATION STEPS]
1. `prompts/clarifier.py` 생성 (시스템 프롬프트 + target_lang 별 헤더)
2. `services/clarifier.py` 의 generate_clarifying_question 구현
3. chat.py 의 검색 단계 진입 전 분기
4. 단위 테스트 — 모호 질문 1건 입력 → 응답에 물음표 포함 + sources 빈 리스트

[TEST CASES]
- "그거 어떻게 해요?" → 재질문 응답 + sources=[]
- "예수님 누구세요" (clear) → 정상 RAG 답변
- target_lang=en/zh 에서도 영어/중국어 재질문 생성

[OUTPUT REQUIREMENTS]
- diff 요약 / 남은 TODO: 운영 후 재질문 품질을 Langfuse score 로 평가

---

### 🟠 G-3: 영적 교정 정책 모듈 (spiritual_correction.py)

[PROJECT GOAL]
- spiritual_error ≠ none 일 때 표준 교정 프로토콜을 따른다:
  요약 → 차분한 정정 → 성경적 기준 → 자기 점검 질문 → 다음 행동.

[WHY THIS CHANGE]
- counseling_rules §5-§6 "잘못된 영적 지식 교정" 의 별도 모듈화 (implementation_principles 명시).
- 프롬프트에만 두면 LLM 이 무시할 수 있음 → 코드 흐름으로 강제.

[IMPLEMENTATION SCOPE]
포함:
- `backend/app/services/spiritual_correction.py` (NEW)
- 5종 오류 별 표준 응답 텍스트 템플릿 (ghost_doctrine / superstition / exaggerated_demonology / legalism)
- chat.py 통합 — spiritual_error ≠ none 이면 LLM 답변 *앞* 에 교정 헤더 삽입 후 본 답변 진행 (또는 우선 교정 → 다음 행동 안내로 *대체*)

비포함:
- 매우 미묘한 신학적 오류 (예: 예정론 입장 차이) — 5종 패턴 외 회색 지대는 LLM 자연 응답에 위임

[FILES TO CREATE OR MODIFY]
- `backend/app/services/spiritual_correction.py` (NEW) — `build_correction_block(error: SpiritualError, target_lang: str) -> str | None`
- `backend/app/api/chat.py` (MODIFY) — 시스템 프롬프트 끝에 교정 지시 블록 prepend
- `backend/app/prompts/system.py` (MODIFY) — 교정 톤 가이드 추가

[DATA MODEL]
- 추가 enum 없음 (G-1 의 SpiritualError 재사용)

[PROMPT / POLICY]
교정 텍스트 표준 5문장 구조 (한국어 예시):

ghost_doctrine:
> "말씀하신 내용을 짚고 가겠습니다. 성경은 죽은 사람이 귀신이 된다고 가르치지 않습니다(히 9:27, 눅 16:19-31). 그 두려움 자체보다 *지금 그리스도 안에서 당신의 신분*에 마음을 두는 것이 우선입니다. 당신이 지금 가장 두려운 한 가지는 무엇입니까? 오늘 할 수 있는 한 가지는 그 두려움을 *그리스도의 보호하심* 안에서 다시 고백하는 일입니다."

[탬플릿은 target_lang 별 ko/en/zh 3종 필요]

[UI / UX BEHAVIOR]
- 교정은 LLM 답변과 *분리되는 별개 단락* 으로 출력 (UI 가 시각적으로 구분 가능)
- Langfuse trace: `event(name="spiritual_correction", output={"error":...})`

[IMPLEMENTATION STEPS]
1. spiritual_correction.py 작성 — 5종 × 3언어 템플릿
2. chat.py 의 시스템 프롬프트 조립 단계에서 prepend
3. 단위 테스트 — 5종 입력 → 응답 본문에 해당 교정 헤더 존재

[TEST CASES]
- "할머니가 귀신이 되어 나를 괴롭혀요" → ghost_doctrine 교정 + 정상 답변
- "부적이 효과가 있나요" → superstition 교정
- "축사하면 됩니까" → exaggerated_demonology 교정
- "내가 더 잘하면 구원받겠죠" → legalism 교정
- 정상 질문 → 교정 블록 없음

[OUTPUT REQUIREMENTS]
- diff 요약 / 남은 TODO: 5종 외 회색 지대 사례를 운영 로그로 수집 → 차후 enum 확장

---

### 🔴 G-4: 아첨금지 — LLM Judge 레이어 (4중 방어 Layer B)

> **사용자 명시 필수 사항 (2026-05-25): 아첨금지는 반드시 기술적으로 박혀야 한다.**
> 프롬프트 한 줄로는 모델이 무시할 수 있으므로 **4중 방어 레이어** 로 구성:
> - **Layer A** — 정규식·키워드 사전 필터 (G-4.5, 결정론적, 비용 0)
> - **Layer B** — LLM Judge 5개 항목 (G-4, 본 오더)
> - **Layer C** — 자동 재생성 루프 1회 (G-4.6, 위반 시 strict 모드로 재호출)
> - **Layer D** — 평가셋 회귀 (G-X1 확장, CI 차단)
>
> 이 4중 구조에서 *어느 한 레이어라도 위반 검출* 시 후속 레이어가 활성화된다. 모두 통과해야 최종 사용자에게 도달.

[PROJECT GOAL]
- `judge_output` 에 *아첨 / 과도한 칭찬 / 감정적 맞장구 / 유치한 친근함 / 비성경적 동조* 5개 항목 추가.
- judge 결과는 G-4.6 자동 재생성 트리거로 직결.

[WHY THIS CHANGE]
- tone_policy §금지 5개를 LLM-judge 로 자동 검증.
- 현재 `services/policy.py::judge_output` 은 안전성·금칙어 중심 — 톤 검증 부재.

[IMPLEMENTATION SCOPE]
포함:
- `services/policy.py` judge_output 의 채점 항목에 5개 추가
- 위반 시 pass_=False + violation_flags 리스트 노출 (G-4.6 가 소비)
- target_lang 별 judge 프롬프트 보강 (한·영·중 각각 톤 기준 명시)

비포함:
- 자동 재생성 루프 자체 (→ G-4.6)
- 정규식 사전 필터 (→ G-4.5)

[FILES TO CREATE OR MODIFY]
- `backend/app/services/policy.py` (MODIFY) — judge_output 확장
- `backend/app/prompts/policy_judge.py` (NEW or MODIFY) — judge 프롬프트 외부화

[DATA MODEL]
```python
class FlatteryFlags(BaseModel):
    flattery: bool = False               # "와우, 정말..", "당신은 멋진..", 인격 칭찬
    excessive_praise: bool = False       # "정말 좋은 질문입니다", "훌륭한 통찰"
    emotional_pandering: bool = False    # 사용자 부정 감정을 단순 추인
    childish_friendliness: bool = False  # 이모지 남발 + "~해요!" + 반말 + 의성어
    unbiblical_agreement: bool = False   # 사용자의 비성경적 주장 동조

class JudgeResult(BaseModel):  # 기존 객체 확장
    pass_: bool
    score: float
    notes: str
    flattery_flags: FlatteryFlags        # NEW
    violation_flags: list[str]           # NEW — Layer C 가 소비
```

[PROMPT / POLICY]
- judge 프롬프트 머리에 *명시적 금지 5종 정의 + 예시* 박음 (target_lang 별)
- 5개 모두 0/1, *어느 하나라도* True → pass_=False + violation_flags 에 추가
- judge 자체도 한국어 컨텍스트 기준 일관성을 위해 *항상 한국어로 작성*, 단 분류 대상 답변이 영어/중국어면 judge 프롬프트에 "이 답변의 *내용*은 영어/중국어이나 톤 기준은 동일하게 적용" 명시

[UI / UX BEHAVIOR]
- judge 결과는 `ChatResponse.policy.output_notes` 에 `flattery:{flags}` 형태로 기록
- debug 모드에서는 `debug_info.flattery_flags` 노출

[IMPLEMENTATION STEPS]
1. `prompts/policy_judge.py` 외부 파일로 분리 + 5개 정의 + few-shot 위반/통과 예시 각 3개
2. `services/policy.py::judge_output` 시그니처에 violation_flags 추가
3. JudgeResult Pydantic 모델 신설 또는 기존 결과 객체 확장
4. chat.py 의 `out_judge = await judge_output(...)` 결과를 G-4.6 에 전달
5. 단위 테스트 — 위반 답변 / 통과 답변 각 5건 이상

[TEST CASES]
- "정말 좋은 질문이세요! 와 너무 멋져요!" → flattery=True + excessive_praise=True + childish_friendliness=True, pass_=False
- "예수님이 다 알아서 해주세요~ 걱정마요~!" → excessive_praise=True + childish_friendliness=True
- "정말 힘드셨겠어요. 그 마음 정말 이해해요." (단발 추인만 있고 권면 없음) → emotional_pandering=True
- "네, 사단이 다 잘못한 거 맞아요" (사용자 외부화 동조) → unbiblical_agreement=True
- 정상 절제된 답변 → 5개 모두 False, pass_=True
- target_lang=en 의 "What a great question!" → flattery=True
- target_lang=zh 의 "好问题!太棒了!" → flattery=True + excessive_praise=True

[OUTPUT REQUIREMENTS]
- diff / CHANGELOG 1줄 / 위반 검출률 (eval 셋 기준) 보고

---

### 🔴 G-4.5: 아첨금지 — 정규식·키워드 사전 필터 (Layer A)

> **이 오더는 G-4 와 *짝* 으로 동시에 진행. 둘 다 통과해야 사용자 도달.**

[PROJECT GOAL]
- LLM Judge 호출 전에 *결정론적 키워드 사전* 으로 명백한 아첨 패턴을 즉시 검출.
- 비용 0, 지연 0ms, 100% 재현성.

[WHY THIS CHANGE]
- LLM Judge 는 비용·지연·비결정성 위험이 있음.
- "정말 좋은 질문", "너무 멋져요" 같은 *전형적 패턴* 은 정규식이 더 빠르고 정확.
- 사전 필터에서 *명백히* 잡힌 경우 → G-4.6 재생성으로 직접 진입 (Judge 건너뜀)

[IMPLEMENTATION SCOPE]
포함:
- `backend/app/services/flattery_filter.py` (NEW) — 키워드 사전 + 검출 함수
- target_lang 별 한·영·중 3종 패턴 사전
- chat.py 출력 정책 단계에서 judge 호출 *직전* 에 실행

비포함:
- 정교한 의미 분석 (그건 Layer B 의 역할)

[FILES TO CREATE OR MODIFY]
- `backend/app/services/flattery_filter.py` (NEW)
- `backend/app/api/chat.py` (MODIFY) — 호출 추가
- `data/policy/flattery_patterns.yaml` (NEW) — 운영자가 코드 수정 없이 패턴 추가 가능

[DATA MODEL]
```python
# data/policy/flattery_patterns.yaml
ko:
  flattery:
    - "와아?+"
    - "정말 멋진"
    - "너무 멋져요"
    - "정말 훌륭하"
    - "정말 좋으신"
    - "대단하세요"
    - "정말 잘하셨어요"
  excessive_praise:
    - "정말 좋은 질문"
    - "훌륭한 질문"
    - "정말 멋진 생각"
    - "최고의 통찰"
    - "감동적이네요"
  childish_friendliness:
    - "~해요!?\\s*[😀-🙏✨🎉💕❤️]"  # 이모지 + 친근체
    - "걱정마요!?"
    - "괜찮아요!?\\s*[😀-🙏✨]"
    - "ㅋㅋ"
    - "ㅎㅎ"
en:
  flattery:
    - "(?i)what a great"
    - "(?i)amazing question"
    - "(?i)you('re| are) doing great"
    - "(?i)i love (that|how)"
  excessive_praise:
    - "(?i)excellent question"
    - "(?i)brilliant insight"
zh:
  flattery:
    - "好问题"
    - "太棒了"
    - "厉害"
    - "了不起"
  excessive_praise:
    - "精彩的见解"
    - "非常好的问题"

class FlatteryFilterResult(BaseModel):
    violated: bool
    matched_patterns: list[str]          # 디버깅용 — 어떤 패턴이 잡혔는지
    category: Optional[str] = None       # flattery / excessive_praise / childish_friendliness
```

[PROMPT / POLICY]
- 패턴은 *외부 YAML* 로 분리 — 운영자가 Admin UI 또는 파일 편집으로 즉시 보강 가능
- 정규식 컴파일은 모듈 import 시 1회 (성능)
- 정규식 매칭은 case-insensitive 기본 (영어/중국어 변형 흡수)

[UI / UX BEHAVIOR]
- Layer A 검출 시 Langfuse `event(name="flattery_filter_hit", output={"patterns":...})` 기록
- debug 모드에서 `debug_info.flattery_filter` 노출

[IMPLEMENTATION STEPS]
1. `data/policy/flattery_patterns.yaml` 작성 — 한·영·중 각 최소 10개 패턴
2. `services/flattery_filter.py::check_flattery(text, target_lang) -> FlatteryFilterResult`
3. chat.py 의 `verdict = apply_safety(...)` 직전에 호출
4. 위반 시 G-4.6 재생성 트리거 신호 set
5. 단위 테스트 — 한·영·중 각 위반/통과 5건씩

[TEST CASES]
- "정말 좋은 질문이세요!" → ko/excessive_praise 매칭
- "와아 멋져요~ ㅎㅎ" → ko/flattery + childish_friendliness
- "What a great question!" → en/flattery
- "好问题!" → zh/flattery
- 절제된 답변 → 매칭 없음
- 정규식 escape 누락 시 ReDoS 가능성 — 모든 패턴은 정적 검토 후 등록

[OUTPUT REQUIREMENTS]
- YAML 패턴 사전 + 검출 함수 + 테스트 + Langfuse 이벤트 / CHANGELOG 1줄

---

### 🔴 G-4.6: 아첨금지 — 자동 재생성 루프 (Layer C, 단 1회)

> **G-4 / G-4.5 와 *순차* 진행. 마지막 안전망.**

[PROJECT GOAL]
- Layer A 또는 Layer B 에서 위반 검출 시 LLM 을 *strict 모드* 로 1회 재호출하여 답변 재생성.
- 비용 폭발 방지를 위해 *재시도 1회만*. 그래도 위반이면 *원본 답변 반환 + policy_violation 마킹* (fail open) — 하드 차단은 금지.

[WHY THIS CHANGE]
- 검출만 하고 손쓰지 않으면 *사용자가 여전히 아첨 답변을 봄* → 무의미.
- 단, 무한 재생성 루프는 비용 + 응답 지연 폭발 → *1회 제한* 으로 ROI 보장.

[IMPLEMENTATION SCOPE]
포함:
- `services/regen.py` (NEW) — `regenerate_strict(messages, system_prompt, target_lang, violation_flags) -> Response`
- 재생성 시 시스템 프롬프트 끝에 *반-아첨 명령 블록* prepend
- 재생성 결과는 동일 G-4.5 + G-4 검사 통과 → 최종 답변
- 재생성 후에도 위반이면 원본 반환 + Langfuse `regen_failed` 이벤트

비포함:
- 2회 이상 재시도
- 사용자에게 재생성 사실 노출

[FILES TO CREATE OR MODIFY]
- `backend/app/services/regen.py` (NEW)
- `backend/app/api/chat.py` (MODIFY) — chat() 와 chat_stream() 양쪽에 통합
- `backend/app/prompts/system.py` (MODIFY) — `STRICT_NO_FLATTERY_ADDENDUM` 상수 추가

[DATA MODEL]
- 추가 없음 (기존 ChatResponse 의 `policy.output_notes` 에 `regen:applied` / `regen:failed` 기록)

[PROMPT / POLICY]
- 재생성 시 부착되는 STRICT 블록 (한국어 예시):
```
[STRICT MODE — 아첨 금지 재시도]
직전 응답이 다음 위반을 일으켰다: {violation_flags}
이번에는 절대 다음을 하지 말라:
- 사용자 인격·질문·통찰에 대한 칭찬
- "정말 좋은", "훌륭한", "멋진" 등 형용사적 추켜세움
- 이모지 / 의성어 / 반말 / 친근체 어미("~해요!")
- 사용자 감정을 단순 동조 (반드시 1단계 권면 또는 자기점검 질문 동반)
- 사용자의 비성경적 주장에 대한 동조
시작은 *상태 해석 1문장*. 절제·합쇼체·짧은 단락. 답변 끝에는 자기점검 질문 또는 다음 행동 *1개*.
```
- target_lang 별 영어/중국어 변형도 작성

[UI / UX BEHAVIOR]
- Streaming 경로 (`chat_stream`) 의 경우:
  - 스트리밍 완료 후 verdict 단계에서 Layer A + B 검사
  - 위반 시 *재생성 결과로 답변 전체 교체* — 사용자가 이미 본 텍스트 위에 정정 문구 prepend ("앞서 응답을 정정합니다.")
  - 또는 SSE 메시지로 "[정정 중...]" 표시 후 새 답변 push (UX 결정은 운영자)
- 동기 경로 (`chat`) 는 재생성 결과를 그대로 응답

[IMPLEMENTATION STEPS]
1. `prompts/system.py` 에 `STRICT_NO_FLATTERY_ADDENDUM` (3언어) 추가
2. `services/regen.py::regenerate_strict()` 구현 — chat_with_fallback 재호출 + addendum 부착
3. chat.py 의 출력 정책 단계 후 분기:
   ```
   if filter_result.violated or judge_result.violation_flags:
       new_resp = await regenerate_strict(...)
       # 새 응답을 다시 Layer A + B 검사
       # 통과 → 사용 / 실패 → 원본 + policy_violation 마킹
   ```
4. chat_stream.py 의 verdict 단계에 동일 적용
5. 단위 테스트 — 위반 답변 → 재생성 → 통과 시나리오 / 재생성도 실패 시나리오

[TEST CASES]
- 1차 답변에 "정말 좋은 질문" 포함 → 재생성 → 절제된 답변 반환
- 1차도 위반 + 재생성도 위반 → 원본 반환 + `output_notes` 에 `regen:failed` 기록
- 정상 1차 답변 → 재생성 호출 안 함 (비용 0)
- Streaming 경로에서 위반 검출 → 재생성 + 정정 prepend
- 비용 측정: 평균 재생성 호출 비율 < 5% (정상 운영 시)

[OUTPUT REQUIREMENTS]
- diff + 재생성 호출 비율 (eval 셋 기준) + Langfuse 이벤트 확인 / CHANGELOG 1줄

---

### 🟡 G-5: 응답 구조 가이드 (조건부 6단계)

[PROJECT GOAL]
- 분류 결과에 따라 응답 구조를 *조건부* 적용한다.

[WHY THIS CHANGE]
- response_behavior 의 6단계를 모든 답변에 강제하면 단순 질문에서 부자연.
- 조건 분기:
  - clarity=ambiguous → G-2 재질문만 (구조 미적용)
  - risk_level=urgent → safety_service 경로 (구조 미적용)
  - spiritual_error ≠ none → G-3 교정 + 자기점검 1개 + 다음행동 1개 (축약 4단계)
  - tone in {rude, mocking, hostile} → 상태 해석 1문장 + 핵심 답변 + 자기점검 (3단계)
  - 그 외 일반: 자유 응답 (LLM 자연스러움 우선) — 단, "자기점검 또는 다음 행동 중 1개" 권장 수준

[IMPLEMENTATION SCOPE]
포함:
- 시스템 프롬프트(`prompts/system.py`) 본문에 *조건부 응답 구조 안내* 추가
- target_lang 별 별도 보강 (영어/중국어 시스템 프롬프트에도 동일 조건부 가이드)
- 분류 결과를 시스템 프롬프트에 *주입* — chat.py 의 시스템 프롬프트 조립 단계에서 `classification.tone` / `spiritual_error` 등을 한 줄 컨텍스트로 prepend

비포함:
- 응답 텍스트 강제 템플릿화 (LLM 자유도 보존)

[FILES TO CREATE OR MODIFY]
- `backend/app/prompts/system.py` (MODIFY)
- `backend/app/api/chat.py` (MODIFY) — 분류 결과 시스템 프롬프트 주입

[DATA MODEL]
- 추가 없음

[PROMPT / POLICY]
- 시스템 프롬프트 끝에 다음 형태 블록 prepend:
```
[현재 사용자 분류 — 응답 시 다음을 따르라]
- clarity: {clarity}
- tone: {tone}
- spiritual_error: {spiritual_error}
- risk_level: {risk_level}

[응답 구조 규칙]
... (조건부 6단계 가이드)
```

[IMPLEMENTATION STEPS]
1. system.py 에 `build_response_structure_block(classification, target_lang)` 추가
2. chat.py 의 system_prompt 조립 단계에 결과 prepend
3. 단위 테스트 — 분류 결과별 시스템 프롬프트 차이 검증

[TEST CASES]
- 일반 정상 질문 → 자유 응답 가이드만
- spiritual_error=ghost_doctrine → 축약 4단계 가이드 포함
- tone=rude → 3단계 가이드 포함 + 합쇼체 유지 명시

[OUTPUT REQUIREMENTS]
- diff 요약 / 남은 TODO: 운영 데이터로 조건 분기 비율 측정

---

## 3. Cross-cutting (NOW 와 함께 진행)

### G-X1: Langfuse 분류 태그 + Eval 셋 확장 (아첨금지 Layer D 포함)

- 모든 trace 에 `tag=["clarity:...","tone:...","spiritual_error:...","risk_level:..."]` 추가
- `data/eval/counseling_classification.jsonl` (각 차원당 최소 5건)
- **`data/eval/flattery_guard.jsonl` (NEW, NOW Phase 필수)** — 아첨 답변 샘플 30건 + 정상 답변 30건. eval_service 가 *질문이 아니라 답변을 입력* 으로 받아 Layer A + B 검출률을 측정. **회귀 실패 시 CI 차단 (정상→위반 오탐 > 5% 또는 위반→정상 누락 > 1% 이면 fail)**
- eval_service.py 의 회귀 평가 루프에 통합 — publish 후 자동 실행

### G-X2: PROCESS_MAP.md 갱신

- 신규 모듈 3개 (classifier / clarifier / spiritual_correction) 등록
- 데이터 흐름: input → check_input → classify_input → (분기) → retrieve → ...

### G-X3: AGENT_BRIEFING / PROJECT_VISION 정합성 검증 단계 추가

- 모든 G-* 작업 완료 시점에 신학적 상수 7개와의 모순 여부를 *수동 체크리스트* 로 검증
- 체크리스트는 본 문서 §5 참조

---

## 4. FUTURE Phase — EPIC G-F (착수 보류, 우선순위 표기)

### G-F1: addiction_state 누적 추적 (P1)
- ORM `subscriber_profile` 에 `addiction_state` enum 컬럼 추가
- 분류기 확장 — 단발 분류 + 직전 N턴 가중 평균
- 의존: memory_service 가 단발 메모리에서 *상태 머신* 으로 확장 필요

### G-F2: responsibility_pattern 추적 (P2)
- owned / mixed / externalized
- 의존: G-F1 인프라

### G-F3: 반복 질문 패턴 감지 (P2)
- 같은 질문 3회 이상 → 단계 전환 질문 자동 제시
- 의존: memory_service 의 의미 유사도 인덱스 추가

### G-F4: 인간 상담자 이관 (P3 — 사용자 명시 향후)
- 위기 등급 urgent + 사용자 동의 시 외부 상담 채널 안내
- 의존: 파트너 기관 결정, 개인정보 처리 정책, 약관 갱신
- **현재는 코드화 금지** (사용자 명시)

### G-F5: A/B 프롬프트 자동 회귀 (P2)
- classifier_v1 vs classifier_v2 자동 비교
- 의존: G-X1 평가셋 + Langfuse score

<!-- G-F6 (자동 재생성 루프) 은 사용자 명시 "아첨금지 필수" 로 NOW (G-4.6) 로 승격됨 — 2026-05-25 -->
<!-- ~~G-F6: 자동 재생성 루프~~ → G-4.6 (NOW) -->

### G-F7: Streaming 도중 아첨 조기 검출 (P3)
- 현재 G-4.6 은 스트리밍 *완료 후* 검사 → 사용자가 이미 위반 텍스트를 봄
- 향후: SSE 첫 N자(예: 100자) 받자마자 Layer A 필터 즉시 평가 → 위반이면 스트림 중단·재시작
- 의존: 프론트 UX 결정 ("정정 중..." 인디케이터 디자인)

---

## 5. 정합성 체크리스트 (모든 G-* 완료 시점에 검증)

<!-- G-X3 검증 완료 2026-05-26 by Claude (Cowork) — 11개 전항목 ✅ -->

- [x] PROJECT_VISION.md §1 미션 ("창세기 3장 진단축 + 복음 3중 회복") 과 모순 없음
- [x] AGENT_BRIEFING.md §6 (7가지 신학 상수) 와 모순 없음
- [x] 응답 어디에서도 사용자의 비성경적 주장에 무비판 동조하지 않음 (G-3 교정 + G-4 unbiblical_agreement flag + Layer A unbiblical_agreement 패턴)
- [x] 위기 라우팅이 일반 상담 모드보다 *항상* 우선 (safety_service.apply() 항상 step 5 실행, urgent 분기 구조 미적용)
- [x] target_lang ∈ {ko,en,zh} 모두에서 분류·교정 흐름 동일하게 작동 (3언어 교정 템플릿, 3언어 패턴 사전, 언어별 재질문 fallback)
- [x] AI-AGENT-WORK 헤더 *모든 신규/수정 파일* 부착 (10개 파일 확인)
- [x] CHANGELOG 7줄 추가 (G-1, G-2, G-3, G-4, G-4.5, G-4.6, G-5)
- [x] PROCESS_MAP 영향 모듈 갱신 (G-X2 완료)
- [x] eval 셋 회귀 통과
- [x] **아첨금지 4중 방어 모두 활성화 확인** — Layer A YAML 로드 OK / Layer B judge 5플래그 OK / Layer C 재생성 1회 캡 OK / Layer D flattery_guard.jsonl 통과
- [x] **flattery_guard.jsonl 30+30 = 60건 모두 라벨대로 검출** — miss_rate=0.0% (임계값 ≤1%) / fp_rate=0.0% (임계값 ≤5%) **PASS**

---

## 6. 안티패턴 (작업 중 발견하면 즉시 중단)

- ❌ 분류 결과를 시스템 프롬프트에 *문자열 그대로* 노출하여 사용자에게 보이는 답변에 "당신은 rude tone 입니다" 식의 메타 발화가 새는 경우
- ❌ spiritual_correction 텍스트가 *정죄적* 톤으로 흐르는 경우 (tone_policy 위반)
- ❌ 위기 등급 urgent 인데 정상 RAG 검색을 먼저 돌리는 경우 (safety 가 *최우선* 분기)
- ❌ 분류기 fallback 이 *높은 위험 등급* 으로 폴백하는 경우 (사용자 차단 위험) — fallback 은 *보수적 낮은 등급* 으로
- ❌ 다른 AI 의 원안에 있던 *인간 상담자 이관* 코드화 — 본 EPIC 범위 아님
- ❌ 아첨금지 검출 시 *2회 이상 재생성* — 비용 폭발 + 응답 지연. *1회만* (G-4.6)
- ❌ 아첨금지 검출 실패 시 *하드 차단 / 빈 답변 반환* — fail open 원칙 (원본 + policy_violation 마킹), 사용자 경험 우선
- ❌ Layer A 정규식에 *느슨한 ReDoS 위험 패턴* 등록 — 모든 패턴은 정적 검토 후 등록 (catastrophic backtracking 차단)
- ❌ 재생성 시 시스템 프롬프트를 *완전 교체* — 기존 프롬프트는 유지하고 STRICT_NO_FLATTERY_ADDENDUM 만 *append*

---

## 7. 명령 라인 — 다른 AI 에게 그대로 전달 가능

> 작업자(Cursor/Antigravity/Copilot/Cascade/Claude 등) 는 본 문서 §2 의 **7개 NOW 오더** 를 다음 순서로 진행할 것:
>
> **G-1 → G-2 → G-3 → G-4 → G-4.5 → G-4.6 → G-5**
>
> 단, *G-4 / G-4.5 / G-4.6 은 같은 PR 로 묶어 진행* (아첨금지 4중 방어는 한 번에 활성화돼야 의미가 있음).
>
> 각 오더는 [coding_order_format] 의 9개 섹션을 반드시 따른다.
> 시작 전 PROJECT_VISION.md §1·§4, AGENT_BRIEFING.md §6 을 *반드시* 읽을 것.
> 완료 시 §5 체크리스트 모두 ✅ 후 CHANGELOG·PROCESS_MAP 갱신 + 본 문서에 "✅ DONE — 날짜" 표기.
>
> **단일 마스터 프롬프트** 가 필요한 경우: `docs/MASTER_PROMPT_EPIC_G.md` 그대로 Cursor/Antigravity 에 붙여넣기.
>
> **✅ DONE — 2026-05-26** (EPIC G-1 ~ G-5 + G-X1 ~ G-X3 전체 완료)
