# 🗺 PROCESS MAP — 전체 흐름과 모듈 책임

> **작업자 필독.** 이 문서가 시스템의 *지도*입니다. 새 기능 추가 시 어느 모듈에 들어가는지 여기서 먼저 확인하십시오.

---

## 1. 시스템 다이어그램 (한 그림)

```
┌──────────────────────────────────────────────────────────────────────┐
│                          외부 진입                                    │
│                                                                      │
│  운영자  ─►  Admin UI (8501)  ─┐         ┌─►  User UI (8502)  ◄─ 사용자│
│                                 │         │                          │
└─────────────────────────────────┼─────────┼──────────────────────────┘
                                  │  HTTP   │
                  ┌───────────────▼─────────▼────────────────┐
                  │   FastAPI Backend (uvicorn, 8000)        │
                  │                                          │
                  │  /chat  /chat/stream  /retrieval         │
                  │  /documents/*  /memory/*  /prompts/*     │
                  │  /eval/*  /admin/*                       │
                  └──┬───┬───┬───┬───┬───┬───┬───┬────┬─────┘
                     │   │   │   │   │   │   │   │    │
       ┌─────────────┘   │   │   │   │   │   │   │    └─────────────┐
       │                 │   │   │   │   │   │   │                  │
   ┌───▼───┐  ┌──────────▼┐  │  ┌▼──────┐  │  ┌▼────────┐    ┌────▼────┐
   │ Input │  │ Hybrid    │  │  │ LLM   │  │  │ Output  │    │ Memory  │
   │ Policy│  │ Retriever │  │  │ +     │  │  │ Judge   │    │ Service │
   │ (룰)  │  │  (Qdrant) │  │  │Fallback│ │  │ (LLM)   │    │ (Q/A)   │
   └───────┘  └─────┬─────┘  │  └───┬───┘  │  └─────────┘    └────┬────┘
                    │        │      │      │                      │
              ┌─────▼─────┐  │  ┌───▼────┐ │  ┌──────────┐        │
              │ Embedder  │  │  │Gemini  │ │  │ Safety   │        │
              │ (KURE-v1) │  │  │Deepseek│ │  │ Service  │        │
              │           │  │  │OpenAI  │ │  │ (HARD)   │        │
              │ Reranker  │  │  │Claude  │ │  └──────────┘        │
              │ (bge)     │  │  │Ollama  │ │                      │
              └───────────┘  │  └────────┘ │                      │
                             │             │                      │
                  ┌──────────▼─────────────▼──────────────────────▼──┐
                  │            데이터 저장소                          │
                  │                                                  │
                  │  SQLite (.gospel.db) — 9 tables                  │
                  │  Qdrant (.qdrant_local) — vector chunks          │
                  │  Filesystem (data/uploads) — 원본 파일            │
                  │  Langfuse (cloud, 옵션) — 추적                    │
                  └──────────────────────────────────────────────────┘
```

---

## 2. Chat 파이프라인 (가장 중요한 흐름)

```
사용자 질문
    │
    ▼
[1] check_input(query) ──❌─► HTTP 400 차단
    │                            (욕설/위험/정책)
    ▼ 통과
[1.5] _route_embedder(req.embedder, req.target_lang)  ← Cross-lingual RAG (2026-05-25)
    │  └─ target_lang ∈ {en, zh} 이고 kure → bge_m3 강제 스왑
    ▼
[1.6] classifier.classify_input(query, target_lang)  ← EPIC G-1 (2026-05-26)
    │  └─ clarity / tone / spiritual_error / risk_level 4차원 분류
    │  └─ Gemini JSON mode + fallback LLM + 3초 타임아웃
    │  └─ Langfuse trace tag: ["clarity:...", "tone:...", "spiritual_error:...", "risk_level:..."]
    ▼
[1.7] clarity=ambiguous? ──YES─► clarifier.generate_clarifying_question()  ← EPIC G-2
    │                              └─ RAG·LLM 건너뛰고 재질문 반환 (sources=[])
    ▼ NO (clarity=clear)
[2] increment_question(sub_id) + get_or_create(sub_id)
    │  └─ 질문 카운트 증가 + 프로필 로드 (dict 반환)
    ▼
[3] classify_user_signal(query) + merge_auto_signal(sub_id, signal)
    │  └─ LLM router가 사용자 신호 분류 + 프로필 자동 갱신
    ▼
[4] HybridRetriever.retrieve(query, profile=profile)
    │  ├─ dense (KURE-v1) → Qdrant
    │  ├─ sparse (BM42)   → Qdrant   (server 모드만)
    │  └─ RRF 융합 → bge-reranker → top-N (profile 기반 랭킹 조정)
    ▼
[5] memory_service.build_context_for_llm(sub_id, 3)
    │  └─ DB의 같은 사용자 최근 3개 Q/A를 messages 앞에 prepend
    ▼
[6] system_prompt 조립  ← EPIC G-3/G-5 (2026-05-26)
    │  ├─ target_lang=ko → prompt_service.current_text() (DB 관리 프롬프트)
    │  └─ target_lang∈{en,zh} → get_system_prompt(target_lang)
    │  + profile injection (헤더는 target_lang 별 분기)
    │  + build_response_structure_block(classification) append  ← G-5 조건부 응답 구조
    │  + spiritual_correction.build_correction_block() prepend  ← G-3 (spiritual_error≠none)
    ▼
[7] chat_with_fallback(messages, system, ...)
    │  ├─ Try: 사용자 지정 provider (예: gemini)
    │  ├─ Catch retryable (429/503/timeout/quota...)
    │  └─ 다음 provider: deepseek → openai → claude → ollama
    ▼
[8] 아첨금지 4중 방어  ← EPIC G-4/G-4.5/G-4.6 (2026-05-26)
    │  ├─ Layer A: flattery_filter.check_flattery(text, target_lang) — 정규식 사전 필터
    │  ├─ Layer B: judge_output(question, answer, target_lang) — LLM Judge 5개 FlatteryFlags
    │  ├─ Layer C: regen.regenerate_strict() — 위반 시 STRICT 모드 1회 재호출 (fail-open)
    │  └─ Layer D: data/eval/flattery_guard.jsonl 회귀 (eval_service.run_flattery_guard_regression)
    ▼
[9] safety_service.apply(query, answer)
    │  ├─ 자살/자해 키워드 → 1588-9191 자동 첨부
    │  ├─ 중독/약물 키워드 → 1577-0199 + 의료 권유 자동 첨부
    │  └─ "구원받지 못합니다" 같은 정죄 표현 → BLOCK
    ▼
[10] check_and_get_onboarding_question(sub_id)
    │  └─ 온보딩 미완료 시 질문 자동 추가
    ▼
[11] Interaction 로그 저장 (subscriber_id + cited_versions + trace_id)
    │
    ▼
ChatResponse(answer, sources, policy, debug_info, interaction_id, ...)
```

---

## 3. Document Lifecycle (자료 운영)

```
   업로드 (POST /documents/upload)
        │
        ▼
   ┌──────────┐   patch_meta / patch_body / 체크리스트
   │  draft   │ ◄─────────────┐
   └────┬─────┘                │
        │ validate_version     │
        ▼                       │
   ┌──────────┐                │  (재업로드 = 새 v(n+1))
   │validated │                │
   └────┬─────┘                │
        │ publish              │
        ▼                       │
   ┌──────────┐                │
   │published │ ───────────────┘
   └────┬─────┘
        │ (새 v publish 시)
        ▼
   ┌──────────┐    또는      ┌──────────┐
   │superseded│              │ archived │ ◄── 수동 아카이브
   └──────────┘              └──────────┘

   ※ L1 (source_artifact) 절대 안 바뀜
   ※ Audit log 모든 transition 기록
```

---

## 4. 모듈 책임 매트릭스

| 영역 | 파일 | 책임 | 수정 시 영향 |
|---|---|---|---|
| **API 진입** | `backend/app/main.py` | FastAPI 앱 생성, 라우터 등록 | 모든 endpoint 접근성 |
| **설정** | `config.py` | Pydantic Settings (.env 로드) | 환경변수 추가/변경 |
| **DB 연결** | `db.py` | SQLAlchemy engine + session | DB URL 변경 |
| **데이터 모델** | `models/orm.py` | 9개 ORM 클래스 | 스키마 변경 시 마이그레이션 필요 |
| **API 스키마** | `models/schemas.py` | Pydantic 요청/응답 | 외부 클라이언트 영향 |
| **chat API** | `api/chat.py` | `/chat`, `/chat/stream` | 답변 품질·UX |
| **documents API** | `api/documents.py` | upload/list/version/publish/bulk | 자료 lifecycle |
| **memory API** | `api/memory.py` | Q/A 조회·삭제·피드백 | 대화기록 페이지 |
| **prompts API** | `api/prompts.py` | 시스템 프롬프트 편집 | AI 어조 |
| **admin API** | `api/admin.py` | collections/taxonomy/usage/health | Hub 페이지 |
| **admin agent** | `api/admin_agent.py`| 자연어 명령 해석 및 백엔드 툴 제어 | AI 관제 챗봇 |
| **subscriber API** | `api/subscriber.py` | 프로필 CRUD 및 Admin 관제 | 사람 페이지 및 맞춤형 챗 |
| **eval API** | `api/eval.py` | A/B 비교 + regression | Status 페이지 평가 |
| **retrieval** | `services/retriever.py` | hybrid dense+sparse+rerank | 답변 정확도 |
| **vector store** | `services/vector_store.py` | Qdrant local/server/memory | 검색 인덱스 |
| **embedding** | `services/embedding/*` | KURE-v1 / bge-m3 / e5 | 검색 품질 |
| **reranker** | `services/reranker.py` | bge-reranker-v2-m3 | 상위 결과 순위 |
| **chunker** | `services/chunker.py` | kss 한국어 문장 분리 | 청크 크기/품질 |
| **LLM 추상** | `services/llm/base.py` | BaseLLM, Message, LLMResponse | 모든 provider 공통 |
| **LLM provider** | `services/llm/{gemini,openai,claude,ollama,deepseek}.py` | 각 API 호출 | 답변 품질·비용 |
| **LLM fallback** | `services/llm/fallback.py` | chain 시도 (rate limit 등) | 안정성 |
| **LLM factory** | `services/llm/factory.py` | name → 인스턴스 | provider 선택 |
| **policy** | `services/policy.py` | 입력 룰북 + LLM judge (FlatteryFlags 5종) | 답변 검열 |
| **classifier** | `services/classifier.py` | 4차원 입력 분류 (clarity/tone/spiritual_error/risk_level) | 상담 품질 분기 |
| **clarifier** | `services/clarifier.py` | clarity=ambiguous 시 재질문 생성 | G-2 분기 |
| **spiritual_correction** | `services/spiritual_correction.py` | 5종 영적 오류 교정 블록 (3언어) | G-3 시스템 프롬프트 prepend |
| **flattery_filter** | `services/flattery_filter.py` | 아첨 정규식 Layer A (YAML 패턴 사전) | G-4.5 결정론적 검출 |
| **regen** | `services/regen.py` | 아첨 재생성 Layer C (1회 STRICT 재호출) | G-4.6 fail-open |
| **safety** | `services/safety_service.py` | 자살/중독/율법 강제 안전망 | 안전성 (코드 박힘) |
| **memory** | `services/memory_service.py` | Interaction 조회/주입/통계 | 대화 기억 |
| **subscriber** | `services/subscriber_service.py` | 사용자 정보 및 상태 관리 | RAG 매칭 및 온보딩 연계 |
| **onboarding** | `services/onboarding_service.py` | 대화 중 프로필 수집 Drip | chat 파이프라인 |
| **llm router** | `services/llm/router.py` | 다중 LLM 협력 및 신호 분류 | chat 파이프라인 |
| **prompt** | `services/prompt_service.py` | DB 프롬프트 활성/저장/이력 | 운영자 톤 편집 |
| **dedup** | `services/dedup_service.py` | hash + 제목 + 본문 유사 감지 | Upload 경고 |
| **eval** | `services/eval_service.py` | 평가셋 회귀 실행 | 품질 회귀 |
| **source** | `services/source_service.py` | L1 immutable artifact 생성 | 업로드 |
| **extraction** | `services/extraction_service.py` | PDF/DOCX/TXT 추출 + 노이즈 제거 + 품질 점수 | 본문 보존 |
| **document** | `services/document_service.py` | L2 lifecycle 상태 머신 | 운영 워크플로우 |
| **publish** | `services/publish_service.py` | L2 → Qdrant 청크/임베딩 + alias swap | 검색 노출 |
| **audit** | `services/audit_service.py` | immutable audit_log 기록 | 추적성 |
| **tracing** | `services/tracing.py` | Langfuse 연동 (옵션) | 관찰성 |
| **시스템 프롬프트** | `prompts/system.py` | GOSPEL_SYSTEM_PROMPT + build_response_structure_block + build_strict_addendum | G-5 구조·G-4.6 STRICT |
| **분류기 프롬프트** | `prompts/classifier.py` | 4차원 분류 시스템 프롬프트 + few-shot | G-1 |
| **재질문 프롬프트** | `prompts/clarifier.py` | 재질문 생성 시스템 프롬프트 (3언어) | G-2 |
| **judge 프롬프트** | `prompts/policy_judge.py` | 아첨금지 5항목 LLM Judge 프롬프트 | G-4 Layer B |
| **아첨 패턴 사전** | `data/policy/flattery_patterns.yaml` | 한·영·중 57개 정규식 패턴 | G-4.5 Layer A |
| **분류 eval 셋** | `data/eval/counseling_classification.jsonl` | 26건 분류 기준 테스트 케이스 | G-X1 |
| **아첨 guard 셋** | `data/eval/flattery_guard.jsonl` | 위반 30 + 정상 30건 Layer D CI 게이트 | G-X1 |

---

## 5. UI 페이지 ↔ API ↔ 서비스 매핑

| UI 페이지 | 주 사용 API | 주 사용 서비스 |
|---|---|---|
| Admin Hub | `/admin/health`, `/admin/usage`, `/documents`, `/admin/collections` | (없음 - 통계만) |
| Library | `/documents`, `/documents/{id}`, `/documents/{id}/versions/...`, `/documents/bulk-action` | document, publish, audit |
| Upload | `/documents/upload` | source, extraction, dedup, document |
| Search | `/chat` | retriever, llm.fallback, policy, safety, memory |
| Status | `/admin/collections`, `/eval/regression` | vector_store, eval |
| 대화기록 | `/memory/list`, `/memory/stats`, `/memory/{id}`, `/memory/{id}/feedback` | memory |
| 사람 (관제탑)| `/admin/subscribers/list`, `/admin/subscribers/{id}`, `/admin/subscribers/categories` | subscriber |
| AI 관제 (Agent)| `/admin/agent/chat` | admin_agent |
| 프롬프트 | `/prompts/current`, `/prompts/history`, `/prompts/reset` | prompt |
| 분류관리 | `/admin/taxonomy` | document, version |
| User UI (8502) | `/chat/stream` (실패 시 `/chat` 폴백) | retriever, llm.fallback, safety |

---

## 6. 데이터 흐름 — "한 질문이 답이 되어 돌아오기까지"

```
사용자 입력 "죄란 무엇인가요?"
    │
    ▼
ChatRequest(query, history, user_id="self", debug=false)
    │
    ▼
chat.py
    │
    ├─► policy.check_input("죄란 무엇인가요?")
    │   └─► PolicyResult(allowed=True, severity="ok")
    │
    ├─► increment_question("self") + get_or_create("self")
    │   └─► profile = {"subscriber_id": "self", "journey_stage": ..., "faith_stage": ..., ...}
    │
    ├─► classify_user_signal("죄란 무엇인가요?")
    │   └─► signal = {"category": ..., "confidence": ...}
    │   └─► merge_auto_signal("self", signal) → profile 갱신
    │
    ├─► retriever.retrieve("죄란 무엇인가요?", profile=profile)
    │   ├─► embedder.embed_query → [0.13, -0.05, ..., 0.21] (1024 dims)
    │   ├─► qdrant.search_dense(vec, top_k=20)
    │   ├─► (server) qdrant.search_sparse("죄란 무엇인가요?", top_k=20)
    │   ├─► RRF fusion
    │   ├─► reranker.rerank(query, top_20_texts) → top_5 (profile 기반 랭킹 조정)
    │   └─► [RetrievedItem×5]
    │
    ├─► memory.build_context_for_llm("self", 3)
    │   └─► [Message(user, ...), Message(assistant, ...), ...]
    │
    ├─► prompt_service.current_text()
    │   └─► "당신은 한국 기독교 복음 상담사입니다..."
    │
    ├─► profile injection (system_prompt += profile 기반 맞춤형 지시)
    │   └─► "- 신앙 단계: ...", "- 현재 감정 상태: ...", "- 다락방 멤버 여부: ..."
    │
    ├─► chat_with_fallback(messages, system=...)
    │   ├─► gen = trace.generation(name="answer", model="auto", input=user_prompt)
    │   ├─► try gemini.chat() → response
    │   ├─► (실패 시) deepseek → openai → claude → ollama
    │   └─► gen.update(model=llm.model_name) + gen.end(output=resp.text, usage=...)
    │
    ├─► policy.judge_output(question, answer)
    │   └─► JudgeResult(pass_=True, score=0.85)
    │
    ├─► safety.apply(query, answer)
    │   └─► SafetyVerdict(answer=answer+disclaimer, triggered=[])
    │
    ├─► check_and_get_onboarding_question("self")
    │   └─► (온보딩 미완료 시) 질문 자동 추가
    │
    ├─► Interaction 저장 (subscriber_id="self", cited_versions=[...], trace_id=...)
    │
    └─► ChatResponse(answer, sources, policy, ...)
            │
            ▼
        UI 표시 + 출처 expander + 👍/👎 + (옵션) 디버그
```

---

## 7. 외부 통신 지도 (보안 점검용)

| 어디로 | 무엇 | 끄려면 |
|---|---|---|
| Google AI API (Gemini) | 질문 + 검색된 청크 텍스트 | `.env`에서 GOOGLE_API_KEY 비움 |
| HuggingFace (KURE/bge 모델) | 첫 1회 모델 파일 다운로드 | 캐시 후 통신 없음 |
| Langfuse cloud | trace/generation 메타 | `LANGFUSE_ENABLED=false` |
| (옵션) OpenAI / Claude / Deepseek | fallback 시 동일 텍스트 | 해당 키 비움 |
| 그 외 | **없음** (Qdrant local, SQLite local, 모든 데이터 PC 안에만) | - |

---

## 8. 파일 한 줄로 정리

```
backend/app/
  main.py            FastAPI 진입
  config.py          환경변수
  db.py              SQLAlchemy
  api/{chat,retrieval,documents,memory,prompts,eval,admin}.py
  services/{retriever,vector_store,chunker,reranker,policy,safety,memory,prompt,
            dedup,eval,source,extraction,document,publish,audit,tracing}.py
  services/{classifier,clarifier,spiritual_correction,flattery_filter,regen}.py  ← EPIC G
  services/llm/{base,gemini,openai,claude,ollama,deepseek,factory,fallback,router}.py
  services/embedding/{base,kure,bge,e5,factory}.py
  models/{orm,schemas}.py
  prompts/{system,classifier,clarifier,policy_judge}.py  ← G-1/G-2/G-4 프롬프트 분리
admin/
  app.py             Hub
  pages/{1..7}_*.py  Library/Upload/Search/Status/대화기록/프롬프트/분류관리
  lib/{api_client,auth,__init__}.py
user/
  app.py             단순 채팅 UI (streaming + fallback)
scripts/
  {init_db,diagnose,ab_test,backup,restore}.py
data/{documents,uploads,eval}/
```
