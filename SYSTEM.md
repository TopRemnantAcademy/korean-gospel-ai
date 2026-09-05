# SYSTEM.md — (통합 시스템 문서 · 단일 소스 오브 트루스)

> **목적:** 이 파일 한 장으로 다른 AI 도구가 이 프로젝트의 **목적·전체 구조·아키텍처·핵심 로직·예외 처리·제약·설정·API 명세·데이터 모델·의존성·테스트·빌드/배포/운영**을 완전히 파악하고, **코드를 수정하거나 기능을 추가**할 수 있도록 한다.
> **범위:** `C:\Desktop\korean-gospel-ai` (Windows 로컬 개발 기준, **2026-08-14** 현재 검증된 상태 반영 — 2026-07-15 기준 + 2026-08 성능/기능 동기화 included).
> **우선순위:** 본 파일이 최신 "단일 소스 오브 트루스"다. `README.md`/`PROCESS_MAP.md`/`CLAUDE.md`/docs/*.md는 참조용 아카이브다.
> **⚠️ 현재 상태 우선:** 기존 문서 일부(README, PROCESS_MAP)는 "Qdrant 서버 모드"를 전제로 쓰여 있으나, **현재 운영 구성은 `local:./.qdrant_local` 임베디드 모드**다. §0·§19(수정 이력)를 우선 따를 것.
> **✅ 코드 불일치 5건 식별·해결 완료 (2026-07-15):** (1) `/health` 엔드포인트 **추가**(`main.py`), (2) `RATE_LIMIT_ENABLED`/`RATE_LIMIT_PER_MINUTE` 이제 `config.py`+`rate_limit.py`에서 **인식**, (3) `POLICY_RULES_PATH` 이제 `policy.py`에서 **인식**, (4) `user_context` 필드 `ChatRequest`에 **추가+프롬프트 주입**, (5) 비한국어 검색(`gospel_bge_m3` 비어 있음) `gospel_kure`로 **자동 폴백**. `.env`는 이미 `.gitignore`에 있어 미추적(시크릿 노출 없음). 미해결 잔여: `TOKEN_QUOTA_*` 등 일부 env는 여전히 미매핑(§7.3). 상세는 §19(7).
> **✅ 2026-08-14 동기화 반영:** LLM 공급자 `nvidia`(fallback `nvidia→tencent→gemini`), Reranker `bge_m3`(활성), `target_lang` 기본 `auto`+`detect_language()` 자동감지, 말씀 주석(`VerseAnnotation`+`/mobile/annotations` CRUD)+채팅 히스트리(`/mobile/history`)+모바일 하이라이트/메모/공유, Langfuse OFF 대신 셀프호스팅 JSONL 트레이스(`logs/traces.jsonl`), 성능 하드닝 9건(§15.5). 실제 코드(`schemas.py`/`config.py`/`.env`/소스)와 대조 검증 완료.

---

## 0. 현재 상태 핵심 (CURRENT STATE — 반드시 읽을 것)

이 절은 과거 문서와 충돌하는 **실제 동작 중인 구성**을 정리한다. 버그 수정 이력은 §19.

| 항목 | 현재 값 | 비고 |
|---|---|---|
| LLM 공급자 | **`nvidia`** (fallback chain `nvidia→tencent→gemini`) | `gemini`/`deepseek`/`openai`/`claude`/`ollama` 키는 비어 있음. `tencent`는 reasoning 모델(`reasoning_content` 폴백, §14.3) |
| Qdrant 모드 | **임베디드** `QDRANT_URL=local:./.qdrant_local`, `QDRANT_GRPC=false` | 서버 모드(`http://...:6333`)는 주석 처리됨. 임베디드 락은 프로세스 1개만 점유 |
| 벡터 컬렉션 | `gospel_kure` (임베더 `kure`, 1024-dim) | 인제스트 결과 **2,335 points** (44개 설교 파일). `gospel_bge_m3` 컬렉션은 기본 인제스트 경로에서 **미생성** — 단 비한국어(`en/zh/ja`) 검색 시 결과 0건이면 `gospel_kure`로 자동 폴백되어 빈 응답 방지(§5.4·§17 한계 7) |
| KURE 임베딩 | `nlpai-lab/KURE-v1`, SentenceTransformer, normalize=True | 정상 로드 확인됨 |
| Reranker | **`bge_m3`** (CrossEncoder) | `RERANKER=bge_m3` (활성). `none`/`cohere`도 선택 가능 |
| 활성 다국어 응답 | KO / ZH / EN / JA + **`auto`**(질문 언어 자동 감지) | `target_lang` 파라미터 구동. 미지정/auto 시 `detect_language()`로 질문 언어 감지(§5.4) |
| DB | SQLite `.gospel.db` (WAL) | ~25개 ORM 모델, 부팅 시 자동 마이그레이션(컬럼/인덱스 자동 패치, §5.1) |
| 실행 포트 | API `:8000` / Streamlit 통합앱 `:8501` / 모바일 PWA `:4174` | `STEP3_START.bat` 참조 |
| 추적(Tracing) | **Langfuse OFF**, **셀프호스팅 JSONL ON** | `LANGFUSE_ENABLED=false`(config 기본 `True`). 대신 `tracing.py` `_LocalTraceClient`가 `logs/traces.jsonl`(10MB×5 로테이션, 시크릿 마스킹)에 구조화 트레이스 기록(§17.6) |
| 활동 모니터링 | **ON** | 모바일/웹 클라이언트 활동 이벤트(시청·검색·화면이동·annotate·공유·세션·에러) 서버 동기화 → `ActivityEvent` 테이블 + 관리자 활동모니터링 페이지(`admin/pages/21_📡_활동모니터링.py`, §5.14·§12) |

**알려진 동작/제약:**
- 임베디드 Qdrant는 **동시 1 프로세스**만 접근 가능. 인제스트(`index_sermons`)와 API 서버는 **동시 실행 불가**. 인제스트 전 API 서버 종료 필수.
- sparse 검색: 서버 모드에서만 Qdrant BM42 사용. **임베디드 모드에서는 앱 레벨 BM25(`sparse_index`)로 폴백** (정상 동작, §14.2).
- CORS: `.env`의 `CORS_ORIGINS`에 `http://127.0.0.1:4174` 포함 → 모바일 PWA 브라우저 접근 허용.
- **헬스 엔드포인트:** `GET /health`(인증 불필요, `{status:"healthy",...}`) **추가됨(2026-07-15)**. 기존 `GET /admin/health`(인증 불필요), `GET /`(서비스 정보, 200), `GET /rag/health`도 사용 가능. `docker-compose.prod.yml`/`deploy.sh`의 `/health` 프로브가 이제 정상 동작(§18.4).

---

## 1. 시스템 개요 (SYSTEM OVERVIEW)

### 1.1 목적 (Purpose)
한국어 복음 설교 코퍼스를 기반으로 한 **신학적으로 안전한(안전 정책 내장) RAG 챗봇**이다. 상담·제자훈련·위기 개입(자해/중독/정죄) 시나리오를 다루며, 운영자(목회/콘텐츠)와 일반 사용자(웹·모바일) 두 계층을 지원한다. 다국어 응답(KO/ZH/EN/JA)과 Google 로그인, 푸시 알림, 오프라인 가능한 모바일 PWA를 특징으로 한다.

### 1.2 핵심 기능 (Core Features)
1. **하이브리드 검색 RAG 채팅** — dense(KURE) + sparse(BM25/BM42) → RRF 융합 → (rerank) → LLM 생성. `/chat`(동기)·`/chat/stream`(SSE).
2. **안전 정책 파이프라인** — 입력 룰북(정규식) + 출력 LLM-judge + HARD 차단(자살/중독/정죄 표현 → 위기 리소스).
3. **다국어 응답 + 자동 감지** — `target_lang`(ko/en/zh/ja/**auto**) → 언어별 시스템 프롬프트. `auto`(또는 미지정) 시 `detect_language()`로 질문 언어를 감지해 해당 언어로 응답. 비한국어 시 bge_m3 임베더로 자동 라우팅(§5.4).
4. **구원 상태 인식** — 사용자 프로필(Subscriber)의 구원 단계/다락방 여부로 프롬프트·검색 boost 조정.
5. **문서 수명주기 관리** — 업로드→버전(초안/발행)→품질 게이트→Qdrant 인제스트. 관리자 전용.
6. **모바일 PWA** — 성경/찬송/설교/묵상/채팅 화면, 오프라인 로컬 JSON 폴백, Capacitor Android 래핑 가능.
7. **운영 콘솔** — `/admin` 엔드포인트군(헬스/서비스헬스/컬렉션/오류로그/사용량/최근활동/설정).
8. **활동 모니터링** — 모바일/웹 클라이언트 활동 이벤트(시청·검색·화면이동·말씀 annotate·공유·세션·에러)를 서버에 동기화하고 관리자 UI에서 DAU/WAU/MAU·Top 시청 콘텐츠·인기 검색어·이벤트 로그·유저 타임라인을 집계(§5.14·§11·§12).
8. **Dify 호환 External Knowledge** — `/retrieval`로 외부 Dify 지식베이스로서 동작.

### 1.3 전체 아키텍처 (Architecture Summary)
3-tier: **프레젠테이션(Streamlit `:8501` + 모바일 PWA `:4174`) → API(FastAPI/uvicorn `:8000`) → 데이터(SQLite 메타DB + Qdrant 벡터 + 파일시스템)**.
LLM은 **Tencent DeepSeek-V4**(reasoning) 활성, 운영 폴백 체인 `tencent → nvidia → gemini`(.env.production.template 기준, nvidia/gemini 키 보유). openai/claude/ollama/deepseek 는 키 미설정 시 비활성. 임베딩은 **KURE-v1** 단일 활성(bge_m3 다국어 병행). 추적(Langfuse)은 운영에서 ENABLE. 상세 다이어그램은 §4.

---

## 2. 디렉토리 구조 (DIRECTORY STRUCTURE)

```
korean-gospel-ai/
├── .env # ★실제 환경변수 (git 무시 권장 — 현재 커밋됨, 시크릿 노출 위험 §17.6)
├── .env.example # 템플릿 (LLM_PROVIDER=gemini 기본)
├── .env.production.template # 운영 템플릿 (플레이스홀더)
├── SYSTEM.md # 본 파일 (통합 문서)
├── README.md / CLAUDE.md / PROCESS_MAP.md / PROJECT_VISION.md / CHANGELOG.md
├── Dockerfile / docker-compose.prod.yml / fly.toml / railway.toml / deploy.sh
├── docker-compose.prod.yml # ★운영 오케스트레이션 (qdrant+backend+ui). ⚠️ /health 프로브 오류 §18.4
├── capacitor.config.json / package.json # 모바일 Android 빌드
├── requirements.txt / requirements-deploy.txt / pytest.ini
├── .github/workflows/ # deploy.yml(테스트+배포), rollback.yml
├── app.py # ★ Streamlit 통합 앱 (채팅 + 관리 콘솔) :8501 (~1788줄)
├── backend/
│ └── app/
│ ├── main.py # FastAPI create_app(), lifespan, 미들웨어, 라우터 마운트, 루트 `/`
│ ├── config.py # ★Pydantic Settings (모든 env 매핑 — §7.3 검증 완료)
│ ├── db.py # SQLAlchemy engine/session, init_db()
│ ├── connections.py # 외부 클라이언트 싱글톤 (Gemini/DeepSeek/Qdrant…)
│ ├── logging_setup.py # RotatingFileHandler + Windows toast 알림
│ ├── api/ # 라우터 (chat, retrieval, admin, documents, memory,
│ │ # prompts, subscriber, auth, glossary, drafts, jobs,
│ │ # mobile, content_admin, media, bible, enhanced_rag)
│ ├── middleware/ # error_monitor.py, rate_limit.py
│ ├── models/ # orm.py (테이블), schemas.py (Pydantic 요청/응답)
│ ├── prompts/ # system.py(다국어 시스템 프롬프트), classifier, clarifier,
│ │ # policy_judge, quality_guide
│ └── services/ # retriever, vector_store, chunker, rag_engine, search_v4,
│ # reranker, sparse_index, llm/(base,factory,tencent,
│ # gemini,deepseek,openai,claude,ollama,fallback,router),
│ # embedding/(kure,bge,e5,factory…), policy, safety_service,
│ # flattery_filter, regen, classifier, clarifier,
│ # spiritual_correction, salvation_detector, memory_service,
│ # token_service, subscriber_service, ingest_pipeline,
│ # document_service, bible_service, media_service,
│ # music_service, push_service,
│ # push_scheduler, job_service, addiction_care, … + enhanced_rag/
├── mobile/ # ★ PWA (index.html, app.js, screens/, components/,
│ # services/, utils/, styles.css, sw.js, manifest.webmanifest, data/)
├── admin/ user/ # (레거시 Streamlit 분리 UI — 현재 app.py로 통합됨, 호환성 보존)
├── scripts/ # index_sermons.py(★), convert_sermons_pdf.py, ingest_documents.py,
│ # init_db.py, migrate_*.py, seed_gospel_core.py, backup/restore,
│ # diagnose.py, check_i18n.py, monitor_cache.py, test_search_v4.py, upgrade/
├── data/
│ ├── documents/ # ★ 인제스트 원본 설교 마크다운 (44개)
│ ├── uploads/ music/ bible/ eval/ # 업로드/음악/성경/정책룰북(policy_rules.yaml)
├── tests/ backend/tests/ # ★pytest/unittest 테스트 (§16)
├── examples/ logs/ docs/ _archive/ .workbuddy/
├── .qdrant_local/ # ★ 임베디드 Qdrant 데이터 (컬렉션 gospel_kure)
├── .gospel.db .gospel.db-wal .gospel.db-shm # SQLite 메타DB
└── venv/ .venv312/ # Python 가상환경 (프로젝트는 venv/ 사용, 3.12)
```

> **주요 진입점:** 백엔드 `backend.app.main:app`, 통합 UI `app.py`, 모바일 `mobile/index.html`, 인제스트 `scripts/index_sermons.py`, 테스트 `pytest backend/tests tests`.

**계층별 의존 관계 (상위 → 하위):**
- `app.py`(Streamlit) → `httpx` → FastAPI `/chat` 등
- `mobile/*`(PWA) → `fetch` → FastAPI `/chat`,`/mobile/*`,`/auth/*`
- `api/*`(라우터) → `services/*` + `models/schemas.py` + `prompts/*`
- `services/retriever.py` → `services/vector_store.py`(QdrantStore) + `services/embedding/*` + `services/reranker.py` + `services/sparse_index.py`
- `services/llm/*` → 외부 LLM API(Tencent 등)
- `scripts/index_sermons.py` → `services/embedding/kure.py` + `services/vector_store.py` + `services/chunker.py`
- 모든 모듈 → `config.py`(settings) · `db.py`(session) · `logging_setup.py`

---

## 3. 실행 방법 (로컬 개발)

프로젝트는 `venv/` (Python 3.12) 사용. 관리 런타임은 `venv/Scripts/python.exe`.

```bash
cd C:\Desktop\korean-gospel-ai

# 1) 환경변수 (.env 이미 임베디드+tencent로 설정됨)
copy .env.example .env # 최초 1회 (이미 존재하면 건드리지 말 것)

# 2) 인제스트 (API 서버 꺼진 상태에서만! 임베디드 락 충돌)
PYTHONPATH=. venv/Scripts/python.exe -u -m scripts.index_sermons --reset

# 3) API 서버 (:8000)
PYTHONPATH=. venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 4) Streamlit 통합앱 (:8501) — 별도 터미널
PYTHONPATH=. venv/Scripts/python.exe -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true

# 5) 모바일 PWA (:4174) — 별도 터미널
venv/Scripts/python.exe -m http.server 4174 --directory mobile --bind 127.0.0.1
```

- 접속: API Swagger `http://127.0.0.1:8000/docs`, 통합앱 `http://127.0.0.1:8501`, 모바일 `http://127.0.0.1:4174`
- 헬스/정보: `GET /health` → `{status:"healthy",version:"0.3.1",service:"korean-gospel-rag"}`(인증 불필요, 2026-07-15 추가), `GET /admin/health` → `{status:"ok",...}`, `GET /` → 서비스 정보(버전/엔드포인트/llm/embedder/qdrant).
- Windows 배치: `STEP1_INSTALL.bat`(설치) → `STEP2_INDEX.bat`(DB+인덱스) → `STEP3_START.bat`(API+앱) → `STEP4_TUNNEL.bat`(Cloudflare 터널).

---

## 4. 아키텍처 다이어그램

### 4.1 시스템 전체
```
            [운영자]──Admin Hub(:8502) [사용자]──User 통합앱(:8501) / Mobile PWA(:4174)
                                │ HTTP/JSON │
                                └──────────────┬─────────────────────────────────┘
                                               ▼
                         ┌──────────────────────────────────────────┐
                         │ FastAPI Backend (uvicorn :8000) │
                         │ 미들웨어: ReqID→ErrorMonitor→RateLimit→CORS│
                         │ /chat /chat/stream /retrieval /documents │
                         │ /admin /mobile /auth /memory /prompts … │
                         └──┬──────┬──────┬──────┬──────┬──────┬──────┘
        ┌──────────────────┘│ │ │ │ │ └──────────────┐
        ▼ ▼ ▼ ▼ ▼ ▼ ▼
   [Input Policy] [search_v4] [LLM + Fallback] [Output Judge] [Memory] [Safety]
   (룰북) (Qdrant) (Tencent…) (LLM) (Q/A DB) (HARD)
                            │ │
                    ┌───────▼──────┐ ┌──────▼──────┐
                    │ Embedder │ │ Tencent │
                    │ KURE-v1 │ │ DeepSeek-V4 │
                    │ Reranker │ │ (reasoning) │
                    └───────┬──────┘ └─────────────┘
                            │
              ┌─────────────▼──────────────────────────────────────┐
              │ 데이터 저장소 │
              │ SQLite (.gospel.db) — 메타/사용자/상호작용 │
              │ Qdrant (.qdrant_local) — 벡터 청크 (gospel_kure) │
              │ Filesys (data/uploads) — 원본 파일 │
              │ LocalJSON (mobile/data/*) — 오프라인 폴백 │
              └─────────────────────────────────────────────────────┘
```

### 4.2 채팅 파이프라인 (`api/chat.py` + `api/chat_pipeline.py`)
```
사용자 질문
  │
  ▼ [1] _verify_auth(Bearer→sub_id, 없으면 DEFAULT_USER)
  ▼ [2] check_input_and_quota → policy.check_input + token_service 할당량 (실패 시 400/429)
  ▼ [1.5] _route_embedder(req.embedder, req.target_lang)
  │ └─ target_lang∈{en,zh} 이고 kure → bge_m3 강제 (Cross-lingual RAG, §5.4). 검색 결과 0건이면 gospel_kure로 자동 폴백
  ▼ [3] retrieve_and_classify (병렬):
  │ ├─ classify_input(query) → clarity/tone/spiritual_error/risk_level
  │ ├─ search_v4.AdvancedSearchEngine.search(top_k=5) → RRF + rerank
  │ └─ _search_enhanced() (bilingual, 병렬, graceful degradation → 예외 시 [])
  ▼ [4] check_clarification_needed → Clarity.ambiguous면 재질문 반환 (sources=[])
  ▼ [5] 백그라운드(fire-and-forget): 프로필 갱신 + 구원 감지
  ▼ [6] build_prompts(sub_id, query, results, classification, target_lang)
  │ ├─ KO: prompt_service.current_text() / 그 외: get_system_prompt(target_lang)
  │ ├─ memory_service.build_context_for_llm (최근 3 Q/A)
  │ ├─ salvation_prompt_wrapper.build_final_system_prompt
  │ ├─ build_response_structure_block(classification) — 조건부 응답 구조
  │ └─ spiritual_correction / addiction addon
  ▼ [7] chat_with_fallback(messages, system, temperature=0.3, max_tokens=700)
  │ └─ 운영 체인: tencent → nvidia → gemini (LLM_FALLBACK_CHAIN=tencent,nvidia,gemini, .env.production.template 기준)
  │ └─ 미정의 시 기본 gemini; openai/claude/ollama/deepseek 는 키 설정 시 추가 폴백 후보
  ▼ [8] 품질 필터: flattery_filter → policy.judge_output → regen(위반 시 STRICT 1회)
  ▼ [9] safety_service.apply_safety (자살/중독/정죄 표현 → 위기 리소스)
  ▼ [10] 온보딩 질문 추가
  ▼ [11] token_service.save_interaction_and_finalize_tokens (Interaction 저장)
  ▼ ChatResponse(answer, sources, policy, llm_provider, llm_model, elapsed_ms, …)
```
> 스트리밍 `POST /chat/stream`은 동일 파이프라인을 `stream_with_fallback`로 처리, SSE `data:` 청크 + 종료 JSON 메타. 클라이언트 연결 끊김(`GeneratorExit`/`CancelledError`)은 조용히 종료, 기타 예외는 친절한 SSE 메시지(`[⚠️ 응답이 중간에 끊겼습니다. 다시 질문해 주세요.]`)로 폴백(§14.1).

### 4.3 검색 (Retrieval) 파이프라인
```
query
  │ analyze_query (search_optimizer): expanded_queries, weights, preferred_filters
  ▼ per 확장쿼리 병렬 _search_one:
  │ embedder.embed_query → store.search_dense(topo_k=recall_k)
  │ store.search_sparse (실패/빈 → _bm25_sparse 앱레벨 폴백)
  │ _rrf_fusion(rankings, weights, k=60) ← ★RetrievedPoint 정규화 수정 적용(§19)
  ▼ 중복 병합 → 후보 max(rerank_top_n*4, 30)
  ▼ reranker.rerank(query, docs) → final = rrf*0.3 + rerank*0.7 (reranker=none면 rrf만)
  ▼ profile boost (salvation/darakbang/assume_saved) → top rerank_top_n
  ▼ RetrievedItem(id, text, score, rrf_score, dense_rank, sparse_rank, metadata)
```

### 4.4 인제스트 파이프라인 (`scripts/index_sermons.py`)
```
data/documents/*.md (44파일)
  │ extract_korean_content (구어체/EN 마커 제거)
  │ extract_sermon_metadata (date/series/gospel_core_tag/target_salvation_stage/중독플래그)
  ▼ chunk_text(target_tokens=350, max=512, min=50, overlap=1문장) → Chunk[]
  ▼ get_embedder("kure").embed_documents(texts) → 1024-dim 벡터
  ▼ QdrantStore.delete_collection() (--reset 시) ← ★store.reset() 아님(§19)
  ▼ QdrantStore.upsert(ids, dense_vecs=vectors, texts, metadatas) ← ★dense_vectors= 아님
  ▼ 완료: store.count() (현재 2,335) ← ★store.client… 아님(§19)
```
> 설계 문서(`docs/INGEST_PIPELINE_DESIGN.md`)는 7단계(정규화→구조화→의미청킹→컨텍스트강화→메타→적극생성→품질게이트)를 제안. **현재 `index_sermons.py`는 이 중 청킹+임베딩+업서트만 구현** (나머지는 feature-flag 기반 별도 서비스로 존재하나 인제스트 스크립트 기본 경로엔 미포함). 청킹 품질은 양호(§19 더블체크 결과).

---

## 5. 구성 요소별 상세 (COMPONENT DETAILS)

각 컴포넌트의 **책임 / 입력 / 출력 / 내부 동작 / 상태 관리**를 정리한다.

### 5.1 `main.py` (FastAPI 진입점)
- **책임:** 앱 생성, 미들웨어 체인 구성, 라우터 마운트, 시작/종료 수명주기, 자동 DB 마이그레이션, 루트 엔드포인트.
- **입력:** 환경(`settings`), 부팅 시 인자 없음. **출력:** ASGI app.
- **내부 동작:**
  - 미들웨어 순서: `RequestIDMiddleware`(가장 바깥) → `ErrorMonitorMiddleware` → `RateLimitMiddleware` → `CORSMiddleware`(가장 안쪽).
  - **lifespan:** 설정 로깅 → `local:` 접두사 시 stale Qdrant `.lock` 삭제 → `connections.log_status()` → 미완료 백그라운드 잡 정리(`job_service.cleanup_stale_jobs(30분)`) → KURE 워밍업 + BM25 재구축(`sparse_index.rebuild_from_qdrant`)을 백그라운드 태스크로 → `push_scheduler.start_scheduler()`(PUSH_ENABLED일 때). 종료 시 스케줄러 정지·연결 종료·DB engine dispose.
  - **DB 자동 패치:** `init_db()` 후 ORM 메타 vs 실제 DB 비교, 누락 테이블 생성 + 누락 컬럼 `ALTER TABLE ADD COLUMN` + 누락 인덱스 `CREATE INDEX`(방어적 스키마 싱크, 예외는 경고만).
  - **라우터 마운트:** `chat, retrieval, admin, documents, memory, prompts, subscriber, auth, glossary, drafts, jobs, mobile, content_admin, media.admin_router, media.public_router, bible.admin_router, bible.public_router, enhanced_rag`.
  - `GET /` → 서비스명/버전/엔드포인트/`llm_provider`/`embedder`/`qdrant_url`(정보용, 200).
- **상태 관리:** 프로세스 레벨. 모듈 임포트 시 `app = create_app()` 생성. 전역 싱글톤: `settings`, DB `engine`, `connections`.

### 5.2 `config.py` — 중앙 설정
- **책임:** 모든 환경변수를 Pydantic `Settings`로 로드. `settings` 싱글톤.
- **입력:** `.env`(루트, `extra="ignore"`, `case_sensitive=False`). **출력:** `Settings` 인스턴스.
- **중요:** 모든 환경변수는 `config.py`의 `settings` 싱글턴을 통해 읽으며, `.env`/compose에 정의된 전체 앱 env(46종)가 매핑됨을 검증 완료(§7.3). 과거 inert였던 `TOKEN_QUOTA_*`/`WELCOME_VERSE`/`VAPID_*`/`PUSH_*`/`DATABASE_URL`도 2026-07-15에 모두 매핑·연결됨.
- `collection_name(embedder) -> f"{prefix}_{embedder}"`; 프로퍼티 `root_dir`, `embedders`(CSV 파싱).

### 5.3 `db.py` / `models/`
- **`db.py`:** SQLAlchemy `engine`(SQLite WAL), `get_session()`(제너레이터), `init_db()`(테이블 생성). `DATABASE_URL` env로 오버라이드 가능(기본 `sqlite:///./.gospel.db`).
- **`models/orm.py`:** ≈15개 테이블 — `SourceArtifact`, `Document`, `DocumentVersion`, `IndexSnapshot`, `Subscriber`, `Interaction`, `AuditLog`, `PromptTemplate`, `Category`, `SalvationJourney`, `AppErrorLog`, `BackgroundJob`, `DocumentDraft`, `ContentLink`. `Base.metadata`가 자동 패치 기준. `AppErrorLog` 컬럼: `level, method, path, status_code, error_type, error_message, traceback, duration_ms, request_id, client_ip`.
- **`models/schemas.py`:** Pydantic 요청/응답(§9).
- **상태 관리:** 영속 상태는 SQLite 파일. 세션은 요청 스코프.

### 5.4 `api/chat.py` + `chat_pipeline.py` (채팅 코어)
- **책임:** 채팅 요청 수신→파이프라인(§4.2)→응답.
- **입력:** `ChatRequest{query, history[], llm_provider?, embedder?, user_id?, debug?, target_lang?}`. **출력:** `ChatResponse` 또는 SSE 스트림.
  - ✅ `user_context: Optional[str]=None` 필드(2026-07-15 추가). Streamlit `app.py`가 전송하는 `saved_user_info`를 수용하며, `build_prompts()`에서 시스템 프롬프트의 `[사용자가 제공한 배경 정보]` 블록으로 주입되어 personalization에 활용됨. 백엔드는 여전히 서버-side `Subscriber` 프로필도 병행 사용.
- **`_route_embedder`(req.embedder, target_lang):** `target_lang=="ko"` → 요청 임베더 그대로. 비한국어(en/zh) → 임베더가 `kure`(또는 None+settings.embedder==kure)면 **`bge_m3`로 강제**. 단 `retrieve_and_classify`에서 해당 다국어 컬렉션(`gospel_bge_m3`) 검색 결과가 0건이면 **자동으로 한국어 기본 컬렉션(`gospel_kure`)으로 재검색**(cross-lingual fallback, 2026-07-15 추가) — 기본 인제스트가 kure만 수행하는 환경에서도 비한국어 검색이 빈 결과를 반환하지 않음(LLM이 `target_lang`으로 번역해 답변).
- **언어 자동 감지:** `target_lang`이 `"auto"`(또는 생략)로 들어오면 `chat.py`가 `prompts/system.py`의 `detect_language(query)`로 질문 언어(KO/EN/ZH/JA)를 판별해 구체 언어로 해석한 뒤 프롬프트/라우팅/캐시키에 사용. 강제 한국어 제약은 제거됨(2026-08).
- **내부 동작:** §4.2 참조. FAQ 정적 캐시(`faq_min_hits>=3` 반복 쿼리 → 캐시된 답변, 검색+LLM 스킵). 배경 판사(`_bg_judge`)·상호작용 저장은 예외를 삼키고 경고만(요청 실패 방지).
- **상태 관리:** 무상태(요청 스코프). FAQ 캐시는 모듈 레벨 딕셔너리. 토큰 잔액 등은 DB(Subscriber/token_service).

### 5.5 `services/retriever.py` — `HybridRetriever`
- **책임:** 하이브리드 검색 오케스트레이션.
- **입력:** `query`, `top_k`, `rerank_top_n`, `dense_weight`, `sparse_weight`, `profile`. **출력:** `list[RetrievedItem]`.
- **내부 동작:** 쿼리 분석(`search_optimizer.analyze_query`) → 확장쿼리별 병렬 `_search_one`(dense+sparse→RRF) → 중복 병합 → rerank → profile boost → top N. 30분 결과 캐시.
- **`_rrf_fusion(rankings, weights, k=60)`:** Reciprocal Rank Fusion. 각 item을 `{"point": r}`/`RetrievedPoint`로 정규화 후 처리(§19 수정).
- **`_bm25_sparse`:** `use_sparse=False` 또는 Qdrant sparse 실패 시 메모리 BM25(`sparse_index.get_index`) 폴백.
- **상태 관리:** `get_retriever()` 모듈 캐시 싱글톤. 내부 `self.store`(QdrantStore 싱글톤), `self.embedder`(CachedEmbedder LRU).

### 5.6 `services/vector_store.py` — `QdrantStore`
- **책임:** Qdrant 벡터 CRUD + 재시도.
- **입력:** `ids, dense_vecs, texts, metadatas, sparse_vecs?`. **출력:** 검색 `RetrievedPoint[]`, `count()`.
- **내부 동작:** 싱글톤 `_client_instance`/`_sparse_encoder_instance`(fastembed BM42). `_retry_qdrant_call` 3× exp backoff(`ConnectionError/TimeoutError`). `search_dense`는 동적 `ef_search=min(ef_search_cap, max(64, top_k*4+32))`. `search_sparse`는 `use_sparse=False`면 `[]`.
- **주의:** `scroll()` 메서드 없음(샘플링은 `store._client.scroll(...)`). 키워드 `dense_vecs=`(아님 `dense_vectors=`). `count()` 사용(아님 `store.client...`).
- **상태 관리:** 프로세스 내 단일 Qdrant 클라이언트. 임베디드 모드에선 파일 락으로 단일 프로세스独占.

### 5.7 `services/llm/` — provider layer
- **`base.py`:** `Message(role,content)`, `LLMResponse(text, prompt_tokens, completion_tokens, total_tokens, model, provider, raw)`, `BaseLLM(ABC)`.
- **`factory.py`:** `get_llm(provider)` — `LLM_PROVIDER`→`TencentLLM` 등. API 키 해시로 캐시 무효화.
- **`fallback.py`:** `chat_with_fallback`/`stream_with_fallback` — chain 소진 시 한국어 친화적 `RuntimeError("죄송합니다. 일시적인 오류...")`. 첫 토큰 15초 무응답 시 다음 provider로 전환(중간 끊김은 재시도 안 함).
- **`tencent.py`:** reasoning 모델 → `msg.content` 빈 경우 `reasoning_content`로 폴백(`chat()`·`stream()` 모두, §19). `stream()`은 `delta.content or delta.reasoning_content`를 yield.
- **상태 관리:** `get_llm`/임베더 LRU 캐시 모듈 레벨.

### 5.8 `services/search_v4.py` — `AdvancedSearchEngine`
- `search(query, top_k, enable_mmr, enable_compression, enable_explain, profile)` — 다중쿼리(HyDE/관점) → 병렬 dense+sparse → RRF → rerank → MMR → 컨텍스트 압축 → 신뢰도 → 설명. `get_search_engine(retriever)` 캐시.

### 5.9 `services/chunker.py` — `chunk_text`
- 한국어 휴리스틱 `_TOKEN_RATIO=0.55`. 섹션(`#` 헤딩)→문장 버퍼링, `target`(기본 350) 도달 시 flush, 긴 문장 분할(max 512), 꼬리 문장 overlap, min(50) 미만 병합.

### 5.10 `services/annotation_service.py` — 말씀 주석(VerseAnnotation)
- **책임:** 사용자가 말씀(절)에 설정하는 하이라이트 색/메모/북마크 CRUD.
- **ORM:** `models/orm.py`의 `VerseAnnotation`(`verse_annotation` 테이블, subscriber FK). 부팅 시 `init_db()`로 자동 생성(§5.1·§9.3).
- **핵심 함수:** `upsert_annotation(subscriber_id, book, chapter, verse, color?, note?)`(같은 절 있으면 갱신·없으면 생성, color/note 덮어씀), `list_annotations(subscriber_id)`, `delete_annotation(annotation_id, subscriber_id)`(소유자 필터), `delete_annotation_by_ref(subscriber_id, book, chapter, verse)`.
- **엔드포인트:** `/mobile/annotations`(GET/POST), `/mobile/annotations/{id}`(DELETE), `/mobile/annotations/ref/{book}/{chapter}/{verse}`(DELETE) — §10.
- **프론트:** 모바일 `AnnotationService`(list/save/remove/removeByRef + 로그인 시 서버 pull-merge, 생성 시 fire-and-forget push) — §11.

### 5.11 모바일 PWA (`mobile/`) — 상세는 §11
- **상태 관리:** `utils/state.js`의 `AppState` 싱글톤(pub/sub + `localStorage` 영속). 상태 키: `activeTab, darkMode, fontSize, bookmarks, recentReadings, hymnFavorites, hymnRecent, isLoggedIn, user, token, subId, currentBook, currentChapter, chatMessages, targetLang`.
- **활동 이벤트 수집(`EventService`, `services/event.js`):** 링 버퍼 + 30s/20건 플러시 + `visibilitychange`/`pagehide` 최종 플러시. 캡처: `session_start/end`, `page_view`(AppState activeTab 구독), `media_play_start/progress/complete`(Player tick/track 구독), `search`(Bible 로컬 검색), `verse_annotation_create/update/delete`, `share`, `js_error`(전역 에러). 게스트는 `device_id`(guestId)로만 귀속, 로그인 시 `Authorization` 토큰으로 서버가 sub_id 추출(§11).

### 5.12 Streamlit 통합 앱 (`app.py`) — 상세는 §12
- **상태 관리:** `st.session_state`(모드, subscriber_id, msgs, auth_token, theme, target_lang, streaming_mode).

### 5.13 스크립트 (`scripts/`) — 상세는 §13

### 5.14 `api/events.py` — 활동 이벤트 수신/조회 (★추가됨, 2026-08-14)
- **`mobile_router`(`/mobile/events`):** `POST /mobile/events/batch` — 클라이언트 활동 배치 수신(게스트 허용, Bearer 선택). `event_type` allowlist(15종) + 배치≤200건 검증, `payload` 4KB 가드. DB write는 `asyncio.to_thread`(비동기 벌크 인서트)로 202 즉시 반환(채팅/스트리밍 지연 차단). 서버는 클라이언트 주장 `subscriber_id`를 무시하고 검증된 토큰의 sub_id만 귀속(스푸핑 방지).
- **`admin_router`(`/admin/activity`, `check_admin` 의존):** `GET /summary`(DAU/WAU/MAU·이벤트분포·Top시청·인기검색 집계), `GET /events`(타입/유저/media_id/기간 필터 목록), `GET /user/{id}`(유저 타임라인). 집계는 조회 기간 내 이벤트를 메모리에서 계산(최대 5만 건).
- **ORM:** `models/orm.py`의 `ActivityEvent`(`activity_event` 테이블, 부팅 시 `init_db()`의 `create_all`로 자동 생성, §9.3).

---

## 6. 구성 요소 간 관계 (INTER-COMPONENT RELATIONSHIPS)

### 6.1 통신 방식 (Communication)
| 발신 → 수신 | 방식 | 프로토콜 | 인증 |
|---|---|---|---|
| Streamlit `app.py` → API | `httpx`(동기/SSE 스트리밍) | REST/JSON, SSE | Bearer(옵션) |
| 모바일 `fetch` → API | `fetch`(AbortController 15s) | REST/JSON | Bearer(옵션), `AppState.authHeaders()` |
| 라우터 → 서비스 | 동기/비동기 함수 호출 | in-process | — |
| 서비스 → 외부 LLM | `AsyncOpenAI`/SDK | HTTPS | API Key |
| 서비스 → Qdrant | `qdrant-client` | in-process(임베디드) / gRPC-REST(서버) | API Key(서버) |
| 서비스 → SQLite | SQLAlchemy | 파일 IO | — |
| 모바일 화면 ↔ 서비스 | `AppState` pub/sub + 직접 호출 | in-process JS | — |
| 라우터 → `ErrorMonitorMiddleware` | 미들웨어 훅 | in-process | — |

### 6.2 결합도 / 의존성 매트릭스 (Dependency / Coupling Matrix)
`X → Y` = "X가 Y에 의존". (의존) (약결합/인터페이스) (강결합)

| 모듈 | 의존 대상 | 결합도 | 비고 |
|---|---|---|---|
| `api/chat.py` | `chat_pipeline`, `models/schemas`, `auth` | 강 | 핵심 경로 |
| `chat_pipeline.py` | `services/retriever`, `search_v4`, `llm/fallback`, `prompts/*`, `policy`, `safety_service`, `memory_service`, `token_service` | 강 | 오케스트레이터 |
| `services/retriever.py` | `vector_store`, `embedding/*`, `reranker`, `sparse_index` | 중 | 인터페이스 기반 |
| `services/vector_store.py` | `qdrant-client`, `config` | 중 | 임베디드/서버 전환 가능 |
| `services/llm/*` | 외부 LLM API, `config` | 약(어댑터) | `BaseLLM` 추상화로 교체 용이 |
| `services/embedding/*` | SentenceTransformer/fastembed, `config` | 약(어댑터) | `Embedder` 추상화 |
| `prompts/system.py` | `config`(target_lang) | 약 | 순수 함수 |
| `scripts/index_sermons.py` | `embedding/kure`, `vector_store`, `chunker` | 강 | 인제스트 전용 |
| `mobile/services/*` | `AppState`, `fetch`(API) | 중 | 로컬 JSON 폴백으로 약결합 보강 |
| `app.py`(Streamlit) | `httpx`, API endpoints | 중 | API 계약에 의존 |

**순환 의존:** 발견되지 않음(단방향 계층). `services → api` 역방향 의존 없음.

### 6.3 데이터 흐름 (Data Flow) 요약
1. **채팅:** UI → `POST /chat` → `chat_pipeline` → (retriever↔Qdrant, llm↔Tencent) → `ChatResponse` → UI 렌더.
2. **인제스트:** `data/documents/*.md` → `chunker` → `embedding/kure` → `vector_store.upsert` → Qdrant(`gospel_kure`).
3. **관리:** Admin UI → `POST /documents/upload` → 버전 저장(SQLite) → 발행 시 `ingest` → Qdrant 동기화(`IndexSnapshot`).
4. **모바일 오프라인:** 백엔드 불가 → `mobile/data/*.json` 로컬 폴백.

---

## 7. 설정 및 환경 (CONFIGURATION & ENVIRONMENT)

### 7.1 로딩 규칙
`config.py`의 `Settings(BaseSettings)`가 `.env`(루트)를 로드. `extra="ignore"`라 알 수 없는 키는 버림. `case_sensitive=False`. `settings` 싱글톤. 일부 값은 `settings`를 통해서만 읽으며, 코드 내 `os.getenv` 직접 호출은 남아있지 않음**(§7.3 검증 완료).

### 7.2 매핑된 환경 변수 (`config.py` 기준, 실제 `.env` 값)
| 변수 | `.env` 값 | 기본값 | 의미 |
|---|---|---|---|
| `LLM_PROVIDER` | `nvidia` | `gemini` | 활성 LLM (fallback chain `nvidia,tencent,gemini`) |
| `LLM_FALLBACK_ENABLED` | `true` | `true` | fallback chain 사용 |
| `LLM_FALLBACK_CHAIN` | `nvidia,tencent,gemini` | `""`(비우면 기본 gemini) | 운영 명시 체인(.env.production.template 기준) |
| `LLM_PROVIDER_TIMEOUT_SEC` | (미설정) | `20` | 1 provider 최대 대기(초), 초과 시 다음 provider |
| `GOOGLE_API_KEY` | (공백) | None | Gemini 키 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | `gemini-2.5-flash` | |
| `OPENAI_API_KEY`/`OPENAI_MODEL` | (미설정) | None / `gpt-4o-mini` | |
| `ANTHROPIC_API_KEY`/`CLAUDE_MODEL` | (미설정) | None / `claude-sonnet-4-6` | |
| `OLLAMA_HOST`/`OLLAMA_MODEL` | (미설정) | `http://localhost:11434` / `qwen2.5:7b` | |
| `DEEPSEEK_API_KEY`/`DEEPSEEK_MODEL`/`DEEPSEEK_BASE_URL` | (공백)/`deepseek-chat` | None / `deepseek-chat` / `https://api.deepseek.com` | |
| `TENCENT_API_KEY` | `sk-J5wM…` | None | ★ Tencent Maas 키 |
| `TENCENT_MODEL` | `deepseek-v4-flash-202605` | `deepseek-v4-flash-202605` | |
| `TENCENT_BASE_URL` | `https://tokenhub-intl.tencentcloudmaas.com/v1` | 동일 | OpenAI 호환 |
| `EMBEDDER` | `kure` | `kure` | 활성 임베더 |
| `EMBEDDER_LIST` | `kure` | `kure,bge_m3` | 사용 임베더 목록(CSV) |
| `HF_TOKEN`/`VOYAGE_API_KEY` | (미설정) | None | hf_inference/voyage용 |
| `QDRANT_URL` | `local:./.qdrant_local` | `http://localhost:6333` | **임베디드**. 서버=`http://host:6333` |
| `QDRANT_API_KEY` | (공백) | None | 서버모드용 |
| `QDRANT_COLLECTION_PREFIX` | `gospel` | `gospel` | 컬렉션 = `{prefix}_{embedder}` |
| `QDRANT_SPARSE_ENABLED` | (미설정) | `True` | BM42 sparse 사용 여부 |
| `QDRANT_GRPC` | `false` | `""` | `"true"`→gRPC(6334) |
| `RERANKER` | `bge_m3` | `none` | `bge_m3\|none\|cohere` (활성: bge_m3 CrossEncoder) |
| `COHERE_API_KEY` | (미설정) | None | |
| `RETRIEVAL_TOP_K` | `20` | `20` | 검색 후보 수 |
| `RERANK_TOP_N` | `5` | `5` | 최종 리랭크 상위 N |
| `DENSE_WEIGHT`/`SPARSE_WEIGHT` | `0.7`/`0.3` | `0.7`/`0.3` | RRF 가중치 |
| `RECALL_K_FLOOR` | (미설정) | `80` | `recall_k` 하한 |
| `RECALL_K_PER_TOPK` | (미설정) | `3` | `recall_k = max(top_k*이값, floor)` |
| `MULTI_QUERY_RECALL_DECAY` | (미설정) | `0.6` | 확장쿼리별 recall 감쇠 |
| `EF_SEARCH_CAP` | (미설정) | `128` | Qdrant ef_search 상한 |
| `CONTEXT_MAX_TOKENS` | (미설정) | `900` | LLM 컨텍스트 토큰 예산 |
| `CONTEXT_TOP_K` | (미설정) | `3` | 컨텍스트 문서 수 |
| `CHAT_MAX_TOKENS` | (미설정) | `700` | LLM 최대 생성 토큰 |
| `FAQ_CACHE_ENABLED` | (미설정) | `True` | FAQ 정적 캐시 |
| `FAQ_CACHE_TTL_SEC` | (미설정) | `86400` | |
| `FAQ_MIN_HITS` | (미설정) | `3` | 캐시 후보 최소 반복 |
| `POLICY_ENABLED` | `true` | `True` | 입력 룰북 |
| `POLICY_RULES_PATH` | `data/eval/policy_rules.yaml` | `None` | 정책 룰북 yaml 경로(`None`→기본 후보 2개 순회). 2026-07-15부터 적용 |
| `RATE_LIMIT_ENABLED` | (미설정) | `True` | IP 속도제한 토글(`/chat` 경로). 2026-07-15부터 적용 |
| `RATE_LIMIT_PER_MINUTE` | (미설정) | `60` | IP 분당 최대 요청(초과 시 15분 차단). 2026-07-15부터 적용 |
| `LANGFUSE_ENABLED` | `false` | `True` | Langfuse OFF. 셀프호스팅 JSONL 추적은 `tracing.py`로 항상 동작(§17.6) |
| `LANGFUSE_PUBLIC_KEY`/`_SECRET_KEY`/`_HOST` | (공백) | None / `https://cloud.langfuse.com` | |
| `APP_PASSWORD` | (공백) | `""` | Admin UI 잠금(공백=OFF) |
| `ADMIN_API_KEY` | `WhwjZod_…` | `change-me` | 관리자 API 키(운영선 변경 필수) |
| `DIFY_API_KEY` | `change-me` | `change-me` | `/retrieval` Dify 키 |
| `AUTH_SECRET` | `X7zBcQV…` | `""` | JWT 서명(강한 랜덤 필수) |
| `GOOGLE_CLIENT_ID` | (미설정) | `""` | Google OAuth(공백=비활성) |
| `DATA_DIR` | `data/documents` | `data/documents` | 인제스트 소스 |
| `MAX_UPLOAD_SIZE_MB` | (미설정) | `100` | 업로드 제한 |
| `TOKEN_ESTIMATE_PER_REQUEST` | (미설정) | `2000` | 토큰 추정 단위 |
| `LOG_LEVEL` | `INFO` | `INFO` | |
| `CORS_ORIGINS` | `…,http://127.0.0.1:4174,…` | localhost 목록 | 콤마 구분, 모바일 `:4174` 포함 |
| `DATABASE_URL` | (미설정) | `None`(→`sqlite:///./.gospel.db`) | Postgres 전환용. `db.py`가 `settings.database_url` 사용. **2026-07-15부터 적용** |
| `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` | (미설정) | None | Web Push VAPID 키쌍. 비어 있으면 자동 생성→`.vapid_keys`. **2026-07-15부터 `settings` 경유** |
| `VAPID_SUBJECT` | (미설정) | `mailto:admin@example.com` | VAPID subject. **2026-07-15부터 적용** |
| `PUSH_ENABLED` | (미설정) | `False` | `true`→매일 `PUSH_HOUR_KST`시(KST) 말씀 발송 스케줄러 가동. **2026-07-15부터 적용** |
| `PUSH_HOUR_KST` | (미설정) | `7` | 발송 시각(KST). **2026-07-15부터 적용** |
| `TOKEN_QUOTA_ENABLED` | (미설정) | `False` | `true`→`token_service`가 일/월간 토큰 할당량 강제(기본 무제한). **2026-07-15부터 적용** |
| `TOKEN_QUOTA_DEFAULT` | (미설정) | `20000` | 일일 할당량(토큰). **2026-07-15부터 적용** |
| `TOKEN_QUOTA_MONTHLY` | (미설정) | `200000` | 월간 할당량(토큰). **2026-07-15부터 적용** |
| `WELCOME_VERSE` | (미설정) | `요한복음 3:16 …` | 오늘의 말씀(환영 구절) 기본 텍스트. `GET /mobile/verse/daily`로 노출. **2026-07-15부터 적용** |
| `INGEST_CHUNK_TARGET_TOKENS`/… | (미설정) | `350`/`512`/`50`/`2` | 청킹 파라미터 |

### 7.3 env→config 매핑 일관성 (검증 완료)
> **✅ 2026-07-15 기준 — 매핑 누락 0건.** `.env` + `.env.example` + `docker-compose.prod.yml`(컨테이너 전용 `PORT`/`PYTHON*` 제외)에 정의된 모든 앱 환경변수(46종)가 `config.py` `Settings` 필드에 매핑됨을 스크립트로 검증 완료. 과거 inert였던 변수들은 모두 해결됨:
> - `RATE_LIMIT_ENABLED`/`RATE_LIMIT_PER_MINUTE`/`POLICY_RULES_PATH` → 2026-07-15 매핑(§17.8 절차 2·3)
> - `TOKEN_QUOTA_ENABLED`/`TOKEN_QUOTA_DEFAULT`(+신규 `TOKEN_QUOTA_MONTHLY`) → 2026-07-15 매핑 + `token_service` 실제 강제 로직 연결(§15.4)
> - `WELCOME_VERSE` → 2026-07-15 매핑 + `GET /mobile/verse/daily` 응답에 노출
> - `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`/`VAPID_SUBJECT` → 2026-07-15 `settings` 경유(`push_service.py`의 `os.getenv` 직접 호출 제거)
> - `PUSH_ENABLED`/`PUSH_HOUR_KST` → 2026-07-15 `settings` 경유(`push_scheduler.py`의 `os.getenv` 직접 호출 제거)
> - `DATABASE_URL` → 2026-07-15 `settings.database_url` 경유(`db.py`의 `os.getenv` 직접 호출 제거)
>
> **일관성 규칙:** 모든 설정은 `backend/app/config.py`의 `settings` 싱글턴을 통해서만 읽는다. 코드 내 `os.getenv`/`os.environ` 직접 호출은 위 목록 외에 남아있지 않음(검증 완료). `extra="ignore"`라 알 수 없는 키는 버림되므로, 새 env를 추가할 땐 반드시 `config.py`에 필드를 추가해야 인식됨.

### 7.4 피처 플래그 (`.env` 한 줄 토글, `config.py` 매핑됨)
| 플래그 | 기본 | 의미 |
|---|---|---|
| `classify_input_enabled` | `True` | G-1 입력 분류(Gemini 쿼터 절약 위해 false 가능) |
| `salvation_detection_enabled` | `True` | D-C14 구원 신호 감지 |
| `salvation_prompt_enabled` | `True` | D-C18 구원 상태별 시스템 프롬프트 |
| `retriever_boost_enabled` | `True` | D-C16 구원·다락방 boost matrix |
| `legalism_check_enabled` | `False` | D-C23 응답 속도 우선(백그라운드 심사로 충분) |
| `gospel_core_fallback_enabled` | `True` | D-C24 검색 0건시 gospel_core 자동 노출(부스트 로직로 구현) |
| `rag_bilingual_enabled` | `True` | 중국어 우선 dual-storage(결정적) |

**인제스트 플래그:** `ingest_normalize_enabled`, `ingest_restructure_enabled`, `ingest_contextual_enabled`, `ingest_quality_gate_enabled`(모두 `True`), `ingest_chunk_target_tokens=350`, `ingest_chunk_max_tokens=512`, `ingest_chunk_min_tokens=50`, `ingest_chunk_overlap=2`, `ingest_restructure_window_chars=3000`.

### 7.5 빌드 모드 / 환경 차이
명시적 debug/release/production 스위치는 **없음**. "모드"는 env 주도:
- **로컬:** `QDRANT_URL=local:./.qdrant_local`, `EMBEDDER=kure`, `LANGFUSE_ENABLED=false`, `RERANKER=bge_m3`.
- **운영(Docker/compose):** `QDRANT_URL=http://qdrant:6333`+`QDRANT_API_KEY`, `RERANKER=bge_m3`, `LANGFUSE_ENABLED=false`(실제 `.env.production` 기준 — Langfuse 대신 셀프호스팅 JSONL 추적), `EMBEDDER=${EMBEDDER:-kure}`.
- **CI:** `EMBEDDER=hf_inference`, `HF_TOKEN=dummy_token`, `QDRANT_SPARSE_ENABLED=false`(모델/네트워크 없이 테스트).
- `Dockerfile`은 로컬 ML 모델을 포함하지 않음(클라우드 임베더/LLM 의존). `--workers 1`(RateLimitMiddleware의 in-process 딕셔너리가 워커 간 공유되지 않으므로 1워커 가정 안전).

---

## 8. 외부 의존성 (EXTERNAL DEPENDENCIES)

**Python (`venv`, `requirements.txt` 핵심):** fastapi, uvicorn, streamlit, pydantic, pydantic-settings, sqlalchemy, qdrant-client, sentence-transformers, torch, fastembed, openai(AsyncOpenAI), httpx, langfuse, kiwipiepy(kss 옵션), numpy, pandas, pyarrow, onnxruntime, huggingface_hub, pymupdf(설교 PDF→MD), alembic, pytest, altair, plyer(Windows toast).

**Node (`package.json`, 모바일/Capacitor):** @capacitor/core, @capacitor/android, @capacitor/cli. 빌드: `npm install` → `npx cap add android` → `npx cap sync android`.

**외부 서비스:**
- **Tencent Cloud Maas** (`tokenhub-intl.tencentcloudmaas.com/v1`) — 현재 유일 활성 LLM. 키 `.env TENCENT_API_KEY`.
- **Qdrant** — 임베디드 로컬(`.qdrant_local`) 또는 서버/클라우드(서버모드 시 `QDRANT_URL`+`QDRANT_API_KEY`).
- **Langfuse** (옵션) — 추적. 현재 OFF.
- **Google Identity** (옵션) — 모바일 구글 로그인(`GOOGLE_CLIENT_ID`).
- **Firebase FCM** (옵션) — 푸시 알림.

**CORS:** 프론트(`:8501`, `:4174`, `capacitor://localhost`, `https://localhost`)가 API(`:8000`) 호출 가능하도록 `.env CORS_ORIGINS` 필수. `allow_credentials=False`, 노출 헤더 `X-Request-ID`.

---

## 9. 데이터 모델 (DATA MODELS)

### 9.1 Qdrant 페이로드 (저장 청크)
```
PointStruct:
  id : uuid (chunk_uuid)
  vector : {"dense": [1024 floats], "sparse": SparseVector(optional)}
  payload : { "text": <display_text>, "source_file": <파일명>,
                "doc_title": <제목>, "section_title": <섹션>,
                "gospel_core_tag": <str|null>, "target_salvation_stage": <int|null>,
                "doc_type": "sermon", "token_estimate": <int>, <기타 메타> }
```
> 메타데이터 키는 `source_file`(아님 `source`/`file`).

### 9.2 Pydantic 스키마 (`models/schemas.py`)
- `TargetLang = Literal["ko","en","zh","ja","auto"]`
- `ChatMessage(role, content)`
- `ChatRequest`: `query: str`(공백 거부 — `field_validator`), `history: list[ChatMessage]=[]`, `llm_provider: Optional[str]`, `embedder: Optional[str]`, `user_id: Optional[str]`, `debug: bool=False`, `target_lang: TargetLang="auto"`(기본 auto → `detect_language()`로 질문 언어 감지), `user_context: Optional[str]=None`(2026-07-15 추가 — 프론트 `saved_user_info` 수용, 시스템 프롬프트에 배경 정보로 주입).
- `SourceItem(id, text, score, metadata)`
- `PolicyInfo(input_allowed, input_severity, input_flags, output_pass, output_score, output_notes)`
- `ChatResponse(answer, sources: list[SourceItem], policy, llm_provider, llm_model, embedder, elapsed_ms, trace_id, interaction_id, debug_info, target_lang)`
- 분류 enum: `Clarity(clear/ambiguous)`, `Tone(calm/distressed/rude/mocking/hostile)`, `SpiritualError(none/ghost_doctrine/superstition/exaggerated_demonology/legalism)`, `RiskLevel(low/medium/high/urgent)`, `InputClassification`.
- Dify 호환: `DifyRetrievalRequest(knowledge_id, query, retrieval_setting, metadata_condition, target_lang)`, `DifyRetrievalResponse(records, query_analysis)`, `DifyRecord(metadata, score, title, content)`.
- 인증: `SignupReq`, `LoginReq`, `AuthResponse(sub_id, token, display_name, is_new)`. 기타 `FeedbackRequest`, `GreetingResponse`, 문서/초안 메타(`DocMetaIn`, `DraftMetaIn`, `VersionDetail`, …).

### 9.3 ORM (SQLite, `models/orm.py`)
§5.3 참조(약 25개 ORM 모델 클래스, `verse_annotation` 등 포함). `Base.metadata`가 자동 패치 기준. `verse_annotation`은 `VerseAnnotation` 모델로 `annotation_service.py`가 관리(§5.10).
- **활동 로깅:** `ActivityEvent`(`activity_event`, §5.14) — `subscriber_id`(토큰 귀속, 게스트는 NULL·`device_id`로 구분), `device_id`, `session_id`, `event_type`, `platform`, `app_version`, `payload`(JSON), `created_at` + 인덱스(`event_type`, `subscriber_id`, `created_at`).

### 9.4 채팅 요청/응답 계약 (프론트↔백엔드)
모든 프론트(Streamlit `app.py`, 모바일 `ChatService.send`)는 `/chat`·`/chat/stream`에 아래를 전송:
```json
{ "query": "...", "history": [{"role":"user|assistant","content":"..."}],
  "user_id": "anon_<uuid>|subId", "target_lang": "ko|en|zh|ja|auto" }
```
> `llm_provider`/`embedder`는 런타임 스왑용 선택 필드. `user_context`는 이제 **수용되어** 시스템 프롬프트의 `[사용자가 제공한 배경 정보]` 블록으로 주입됨(2026-07-15).
응답 `ChatResponse`: `answer`(문자열), `sources[]`, `llm_provider`, `llm_model`, `elapsed_ms` 등.

---

## 10. API 레퍼런스 (주요 엔드포인트)

| 메서드 | 경로 | 인증 | 설명 | 요청 → 응답 |
|---|---|---|---|---|
| POST | `/chat` | Bearer(옵션) | 동기 채팅 | `ChatRequest` → `ChatResponse` |
| POST | `/chat/stream` | Bearer(옵션) | SSE 스트리밍 채팅 | `ChatRequest` → `data:`청크 + 종료 JSON |
| GET | `/chat/ping` | Bearer | 복귀자 감지 | → `{returning:bool}` |
| GET | `/chat/greeting` | Bearer | 인사말 | `?user_id&mode&target_lang` → `GreetingResponse` |
| POST | `/feedback` | Bearer(필수) | 피드백 | `FeedbackRequest` → ok |
| POST | `/retrieval` | DIFY_API_KEY | Dify External Knowledge | `DifyRetrievalRequest` → `DifyRetrievalResponse` |
| POST | `/documents/upload` | ADMIN_API_KEY | 파일 업로드 | multipart → `VersionDetail` |
| POST | `/documents/ingest-text` | ADMIN_API_KEY | 텍스트 인제스트 | form → ok |
| GET | `/admin/health` | — | 헬스(인증 불필요) | → `{status:"ok",...}` |
| GET | `/admin/services-health` | ADMIN_API_KEY | 서비스 헬스 | → `overall: healthy\|degraded\|unavailable` |
| GET | `/admin/collections` | ADMIN_API_KEY | 컬렉션 정보 | → Qdrant 컬렉션 목록 |
| GET | `/rag/health` | — | Enhanced-RAG 헬스 | → JSON |
| GET | `/health` | — | 헬스(인증 불필요, 2026-07-15 추가) | → `{status:"healthy", version:"0.3.1", service:"korean-gospel-rag"}` |
| GET | `/` | — | 서비스 정보 | → `{service, version, endpoints, llm_provider, embedder, qdrant_url}` |
| GET | `/mobile/music` `/mobile/content` `/mobile/bible/read` `/mobile/legal` | 공개 | 모바일 콘텐츠 | → JSON |
| GET | `/mobile/profile` `/mobile/history` | Bearer | 모바일 회원 | → JSON |
| POST | `/auth/login` `/auth/signup` `/auth/google` | — | 인증 | → `AuthResponse` |
| GET | `/memory/list` | Bearer | 대화 기록 | → JSON |
| GET | `/mobile/history` | Bearer | 모바일 대화 기록 목록 | → JSON(question/answer/created_at) |
| DELETE | `/mobile/history/{interaction_id}` | Bearer | 대화 기록 삭제(소유자 필터) | → ok |
| GET | `/mobile/annotations` | Bearer | 말씀 주석(하이라이트/메모) 목록 | → JSON(list) |
| POST | `/mobile/annotations` | Bearer | 말씀 주석 upsert `{book,chapter,verse,color?,note?}` | → annotation |
| DELETE | `/mobile/annotations/{annotation_id}` | Bearer | 주석 삭제(소유자 필터) | → ok |
| DELETE | `/mobile/annotations/ref/{book}/{chapter}/{verse}` | Bearer | 절 기준 주석 삭제 | → ok |
| POST | `/mobile/events/batch` | Bearer(옵션) | 클라이언트 활동 이벤트 배치 수신(게스트 허용) | `EventBatchIn`(device_id,subscriber_id,session_id,platform,app_version,events[]) → `{accepted:N}` |
| GET | `/admin/activity/summary` | ADMIN_API_KEY | 활동 집계(DAU/WAU/MAU·이벤트분포·Top시청·인기검색) | `?days` → JSON |
| GET | `/admin/activity/events` | ADMIN_API_KEY | 이벤트 목록(타입/유저/media_id/기간 필터) | `?event_type&subscriber_id&media_id&from&to&limit&offset` → JSON[] |
| GET | `/admin/activity/user/{id}` | ADMIN_API_KEY | 특정 유저 활동 타임라인 | → JSON[] |

> **헬스 확인:** `GET /health`(무인증, 2026-07-15 추가) 또는 `GET /admin/health` 사용. 기존 `GET /`도 정보용으로 항상 200.
> 공개 모바일: `/mobile/legal`, `/mobile/music`, `/mobile/music/{id}/stream`, `/mobile/bible/read`, `/mobile/push/vapid`, `/mobile/content`. 회원: `/mobile/profile`, `/mobile/history`, `/mobile/verse/daily`, `/mobile/bible/search`, `/mobile/bible/refs`, `/mobile/push/subscribe`, `/mobile/push/test`.

예시 (cURL):
```bash
# 채팅 (중국어 응답)
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"하나님은 어떤 분이신가요?","target_lang":"zh"}'
# Dify 호환 검색
curl -X POST http://127.0.0.1:8000/retrieval \
  -H "Authorization: Bearer $DIFY_API_KEY" -H "Content-Type: application/json" \
  -d '{"knowledge_id":"kure","query":"거듭난다는 것은?","retrieval_setting":{"top_k":5}}'
```

---

## 11. 모바일 PWA (`mobile/`)

Vanilla JS SPA(프레임워크 없음). `index.html`이 `window.GOSPEL_API_BASE`(기본 `http://127.0.0.1:8000`), `window.GOSPEL_GOOGLE_CLIENT_ID` 설정. 서비스워커 `sw.js`로 오프라인 캐시 + 설치 가능(`manifest.webmanifest`).

| 파일 | 역할 |
|---|---|
| `index.html` | PWA 셸, 전역 설정, 스크립트 로드 |
| `app.js` | 탭 라우팅(`SCREEN_RENDERERS` 맵), SW 등록, `AppState` 초기화 |
| `components/index.js` | `renderTabBar`, `Card`, `h()` 등 UI 프리미티브 |
| `screens/index.js` | 6화면: Bible, Hymns, Sermon, Meditation, **Chat**, Login |
| `services/index.js` | `BibleService`, `MediaService`, `WorshipService`, `SermonService`, `MeditationService`, `AuthService`, **`ChatService`**(로컬 JSON 폴백 포함) |
| `utils/dom.js` | `$`, `$$`, `h(tag,props,...children)`, `empty`, `show/hide` |
| `utils/state.js` | `AppState` 싱글톤(pub/sub + `localStorage`) |
| `styles.css` `styles-media.css` | 테마(다크 기본, `--accent`) |
| `data/*.json` | 오프라인 폴백(bible/hymns/meditation) |

**상태 관리 (`utils/state.js`):**
- `AppState`: 평범한 객체 `_store` + `get/set/setMultiple/on/_notify` pub/sub(키별 리스너 + 와일드카드 `'*'`).
- **상태 키:** `activeTab`("bible"), `darkMode`(true), `fontSize`, `bookmarks`, `recentReadings`, `hymnFavorites`, `hymnRecent`, `isLoggedIn`, `user`, `token`, `subId`, `currentBook`, `currentChapter`, `chatMessages`(배열), `targetLang`("auto"), `annotations`(말씀 주석 맵).
- **영속화:** `localStorage` 키 `gospel_font`, `gospel_bm`, `gospel_recent`, `gospel_hf`, `gospel_hr`, `gospel_token`, `gospel_sub_id`, `gospel_lang`, `gospel_dark`.
- **메서드:** `toggleDark`, `setFontSize`, `toggleBookmark`, `addRecentReading`, `toggleHymnFav`, `addHymnRecent`, `login(user,token,subId)`, `logout()`, `authHeaders()`(`{Authorization:'Bearer '+token}`), `setTargetLang`.

**화면 간 통신:** 라우터/이벤트버스 없음. `AppState` pub/sub + 직접 `AppState.set`로 교환. 예: `AppState.on('activeTab', id=>renderScreen(id))`; Bible 화면이 `currentBook`/`currentChapter` 설정 → 자기 재렌더.

**`ChatService.send(message, history=[], targetLang='auto')`** (★모바일 채팅 계약):
```js
POST {API_BASE}/chat
headers: { 'Content-Type':'application/json', ...AppState.authHeaders() }
body: { query: message, history: history.slice(-10),
        user_id: AppState.get('subId') || AppState.get('guestId'), target_lang: targetLang }
→ returns { role:'assistant', content: data.answer }
// 15s AbortController 타임아웃
```
**언어 토글 + 자동 감지:** 기본 `targetLang='auto'`(질문 언어 자동 감지). `screens/index.js`의 `renderChat()`에 `ko/zh/en` 버튼 행으로 명시 언어 고정 가능. 클릭 시 `AppState.setTargetLang(lang)` → 다음 `sendMessage`부터 `targetLang` 전송. CSS `.lang-toggle`/`.lang-btn.active`(`styles.css`).

**채팅 히스토리 (★추가됨):** `HistoryService`(`services/index.js`)로 `/mobile/history` 목록 조회·`/mobile/history/{id}` 삭제. "오늘" 탭에서 기록 카드 탭 → `_resumeConversation`으로 이전 질문/답변을 채팅창에 복원(로컬 `chatMessages` 영속 + 서버 이력).

**말씀 하이라이트/메모/공유 (★추가됨):** 성경 절 탭 → 액션시트(색 하이라이트/메모/공유/삭제). `AnnotationService`(list/save/remove/removeByRef)가 로컬 `annotations`(`gospel_ann`)에 영속 + 로그인 시 서버 pull-merge, 생성 시 fire-and-forget push(`/mobile/annotations`). 메모는 커스텀 모달(네이티브 `prompt()` 미사용), 공유는 `<canvas>` 720×900 카드(`_shareVerseCard`).

**예외 처리(모바일):** 모든 서비스가 `fetch`를 `try/catch` + 로컬 JSON 폴백. `ChatService`는 15s 초과→"응답 시간이 초과되었습니다…", 기타→"서버에 연결할 수 없습니다.", `!res.ok`→`throw Error('HTTP '+status)`, 빈 답변→"답변을 받지 못했습니다." `AuthService`는 `{ok:false, error}` 반환, Google Client ID 없으면 더미 게스트.

**활동 이벤트 수집(★추가됨, 2026-08-14):** `services/event.js`의 `EventService`가 `app.js` 부팅 시 `init()`. 캡처 지점: `Player.on('tick'/'track')`→미디어 재생(progress는 25/50/75% 버킷 + 90% 완료), `AppState.on('activeTab')`→화면이동, Bible 로컬 검색→`search`, 말씀 하이라이트/메모/삭제→`verse_annotation_*`, 설교/절카드 공유→`share`, `visibilitychange`/`pagehide`→세션 종료+최종 플러시, 전역 `error`/`unhandledrejection`→`js_error`. 인메모리 링 버퍼 + 30s·20건 임계 플러시, `fetch(keepalive)` 배치 전송. 게스트는 `device_id`(guestId) 귀속, 로그인 후 `Authorization` 토큰으로 서버가 sub_id 추출(스푸핑 방지). 상세는 §5.14·§5.11.

---

## 12. Streamlit 통합 앱 (`app.py`, `:8501`)

단일 파일 = 채팅 모드 + 관리자 모드 + 관리자 로그인(~1788줄).
- `load_dotenv(ROOT/.env)`; `API_BASE=os.getenv("API_BASE","http://127.0.0.1:8000")`.
- 세션 기본: `mode="chat"`, `subscriber_id="anon_<uuid>"`, `msgs=[]`, `auth_token=None`, `theme="dark"`, `target_lang=_pq_lang or "auto"`, `streaming_mode=True`.
- **언어 토글 (★추가됨):** 사이드바 상단 `한국어/中文/English` 3버튼 → `st.session_state.target_lang` 설정(기본 `auto`=질문 언어 자동 감지). 이후 전송 시 `target_lang`을 `/chat`·`/chat/stream` 요청에 포함.
- 채팅: 사용자 입력 → (기본) 스트리밍 `httpx.stream("POST", f"{API_BASE}/chat/stream", json={query, history, user_id, user_context, target_lang})` → SSE `data:` 파싱 실시간 표시; 또는 비스트리밍 `POST /chat`. `user_context`(=`saved_user_info`)는 이제 백엔드에서 수용되어 프롬프트에 반영됨(2026-07-15).
- 피드백 `POST /feedback`, 대화 저장(`_save_history`, 100msg/50conv cap).
- 관리자: `?admin` 쿼리 + `APP_PASSWORD` 게이팅, 관리 엔드포인트 호출.
- 연결 백엔드: `/chat`, `/chat/stream`, `/auth/login`, `/auth/signup`, `/feedback`.
- **예외 처리:** `_httpx_request_with_retry`는 `httpx.ConnectError`·5xx만 2회 재시도(선형 backoff). chat 블록 `except`→`st.error("연결에 문제가 있어요. 잠시 후 다시 시도해 주세요.")`. `_send_feedback`은 예외를 삼키고 `False` 반환.

---

## 13. 스크립트 (`scripts/`)

| 스크립트 | 용도 | 주요 진입점 |
|---|---|---|
| **`index_sermons.py`** | 설교 MD → 청킹 → 임베딩 → Qdrant | `extract_korean_content`, `extract_sermon_metadata`, `index_single_file`, `index_all_sermons`, `main`. CLI: `python -m scripts.index_sermons [--dir DIR] [--embedder NAME] [--reset]` |
| `convert_sermons_pdf.py` | 설교 PDF → MD | CLI convert |
| `ingest_documents.py` | `data/documents` → Qdrant | |
| `download_bible.py` | 성경 텍스트 fetch | |
| `init_db.py` | DB 초기화+마이그레이트 | `init_db()` |
| `migrate_db.py` / `migrate_sqlite_to_postgres.py` | 스키마/DB 이전 | |
| `seed_gospel_core.py` | gospel-core 큐레이션 | |
| `backup.py` / `restore.py` | SQLite+Qdrant+uploads 백업/복원 | |
| `diagnose.py` / `check_i18n.py` / `monitor_cache.py` / `test_search_v4.py` | 진단/점검 | |
| `upgrade/` | Alembic식 티어 마이그레이션 | `base.py`, `checks.py`, `rollback.py`, `tier_0_to_0_5.py` |

**`index_sermons.py` 정확한 API 계약 (★중요 — 과거 버그 수정 반영):**
```python
store = QdrantStore(embedder_name="kure", dim=1024) # __init__ 시그니처
if reset_collection:
    store.delete_collection() # ✅ reset() 아님
store.upsert(ids=ids, dense_vecs=vectors.tolist(), # ✅ dense_vecs= (dense_vectors= 아님)
             texts=texts, metadatas=metadatas)
count = store.count() # ✅ store.count() (store.client… 아님)
```
> 인제스트는 임베디드 Qdrant 락을 점유 → API 서버 종료 후 실행. 멀티프로세싱(임베딩) 자식 프로세스가 부모 대기. `--reset`로 컬렉션 전체 재구축. **bge_m3 컬렉션은 기본 경로에서 생성되지 않음**(§17 한계 7).

---

## 14. 예외 처리 규칙 (EXCEPTION HANDLING RULES)

### 14.1 레이어별 전략
| 레이어 | 전략 | 구체 동작 |
|---|---|---|
| **프레젠테이션(모바일)** | 방어적 폴백 | 모든 `fetch` `try/catch` → 로컬 JSON(bible/hymns/meditation) 또는 친절 메시지. `ChatService` 15s `AbortController` 타임아웃. `AuthService` `{ok:false,error}` 반환. Google ID 없으면 더미 게스트. |
| **프레젠테이션(Streamlit)** | 방어적 폴백 | `_httpx_request_with_retry`(ConnectError·5xx 2회 재시도). chat `except`→`st.error`. `_send_feedback` 예외 삼킴(`False`). |
| **API 게이트웨이** | 미들웨어 | `ErrorMonitorMiddleware`가 처리되지 않은 예외를 `AppErrorLog`(ORM)에 기록 + `ERROR/SLOW/CRITICAL` 분류. `RateLimitMiddleware`가 `/chat*` 초과 시 429. **전역 `@app.exception_handler`는 없음** — 라우터별 `HTTPException`이 1차 방어. |
| **비즈니스 로직** | fallback chain + graceful degradation | LLM 실패→다음 provider(§14.3). 검색 실패→`[]`(크래시 방지). `_search_enhanced` 예외 삼킴. 입력 정책 위반→400. 출력 HARD 차단→위기 리소스. |
| **데이터 접근** | 재시도 + 안전 기본값 | Qdrant `_retry_qdrant_call` 3× exp backoff. `search_dense/sparse` 실패→`[]`. DB 자동 패치(누락 컬럼/인덱스 추가). 임베디드 락 충돌→기동 시 stale `.lock` 삭제 + 인제스트 전 API 종료 권장. |

### 14.2 에러 타입 분류 (Error Taxonomy)
- **런타임 분류(유일한 공식 분류):** `ErrorMonitorMiddleware` 레벨 `ERROR | SLOW | CRITICAL`.
  - `ERROR`: 라우트가 500 이상 반환.
  - `SLOW`: 응답 10~30초. `CRITICAL`: 응답 >30초(`_CRIT_MS=30000`) 또는 처리되지 않은 예외(CRITICAL은 traceback 기록 + Windows toast `alert_on_critical`).
  - 노이즈 경로(`/docs`,`/openapi`,`/favicon`)는 건너뜀.
  - DB 기록은 fire-and-forget(`asyncio.create_task`); 내부 기록자 `_write_error_log`는 모든 예외 삼킴.
- **도메인 분류(HTTP 에러 아님, 안전 응답용):** `SpiritualError`(none/ghost_doctrine/superstition/exaggerated_demonology/legalism), `RiskLevel`(low/medium/high/urgent — urgent=자해/폭력/과복용), `CrisisLevel`(addiction_care). 이들은 안전 응답을 유도하지 HTTP 상태를 바꾸지 않음.
- **커스텀 예외 계층 없음.** 에러는 `HTTPException` 또는 `RuntimeError`로만 전달(도메인 enum/model은 예외 아님).

### 14.3 폴백 동작 (Fallback Matrix)
| 폴백 | 위치 | 트리거 | 동작 |
|---|---|---|---|
| **LLM provider chain** | `llm/fallback.py` | `ConnectionError`/재시도가능(429/503/502/504/quota/billing)/`TimeoutError` | 다음 provider(`resolve_fallback_chain`: primary+크레덴셜 보유순). 모두 실패→한국어 친화적 `RuntimeError("죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")`. 비재시도(`ValueError`/`ImportError`)도 스킵. |
| **스트리밍 첫 토큰 프로브** | `fallback.py` | 첫 토큰 15초(`_FIRST_CHUNK_TIMEOUT`) 무응답 | 총 무응답으로 간주→다음 provider. **중간 끊김은 재시도 안 함.** |
| **BM25 sparse 폴백** | `retriever.py` | `search_sparse` 빈/실패 | 메모리 `_bm25_sparse`로 폴백, RRF는 dense 가중치 `[1.0]` 단독. |
| **Qdrant sparse→dense-only** | `vector_store.py` | `search_sparse` 예외 | 경고 로그 + `[]` 반환(`qdrant_sparse_enabled` 게이트). |
| **`reasoning_content` 폴백** | `llm/tencent.py` | reasoning 모델 빈 `content` | `text = msg.content or getattr(msg,"reasoning_content",None) or ""`. 스트리밍은 `delta.content or delta.reasoning_content`. |
| **FAQ 정적 캐시** | `chat.py` | 반복 쿼리(≥`faq_min_hits=3`) | 캐시된 답변 반환, 검색+LLM 스킵(동기·스트리밍 모두). |
| **Enhanced-RAG 검색** | `chat_pipeline.py` | `_search_enhanced` 예외 | `[]` 반환(graceful degradation, 표준 결과 영향 없음). |
| **gospel_core 부스트** | `retriever.py`/`search_optimizer.py` | `gospel_core_fallback_enabled=True`(검색 0건 시 부스트) | `SALVATION_BOOST_MATRIX`/`preferred_filters`로 `gospel_core_tag` 부스트(0건 시 명시 핸들러는 단일 함수로 미존재 — 부스트 로직로 구현). |
| **기본 언어** | `schemas.py`/`chat.py` | `target_lang` 누락/auto | `detect_language(query)`로 질문 언어 감지 후 해당 언어 응답. 명시값(ko/en/zh/ja)은 그대로. 비한국어는 `_route_embedder`로 bge_m3 라우팅. |
| **Auth secret** | `auth.py` | `AUTH_SECRET` 미설정 | `.auth_secret` 파일 → `admin_api_key+"_auth_secret"`(CRITICAL 로그). |
| **모바일 오프라인** | `mobile/services/index.js` | 백엔드 불가 | 로컬 JSON(bible/hymns/meditation) / 더미 Google 사용자 / 친절 채팅 메시지. |

### 14.4 사용자에게 표시할 메시지 규칙
- **언어:** 시스템/에러 메시지는 **한국어** 고정. 다국어 응답은 `target_lang`(또는 `auto`로 감지된 질문 언어)에 따름 — 비한국어 질문엔 비한국어로 답변(강제 한국어 제약 없음).
- **HTTP 상태 → 메시지:**
  - `400` 입력정책/검증: 한국어 상세(`HTTPException(detail="<한국어>")`).
  - `401` 인증: "로그인이 필요합니다." / "토큰이 유효하지 않습니다."
  - `403` 권한: "관리자 권한이 없습니다." / "접근 권한이 없습니다."
  - `404`: "찾을 수 없습니다."
  - `409`: "이미 가입된 이메일입니다."
  - `422`: Pydantic 검증(예: 빈 query → "query must not be empty or whitespace-only").
  - `429`: `{"error":"ip_blocked"|"rate_limit_exceeded", "message":"요청이 너무 많습니다. 잠시 후 다시 시도해주세요."}`.
  - `502`: "구글 인증 서버에 연결할 수 없습니다."
  - `503`: 관리자 API 비활성(`ADMIN_API_KEY=="change-me"`→"관리자 API가 비활성화되어 있습니다.") / Google 미설정.
- **토큰 할당량 소진:** 구조화 `detail={"error":"token_quota_exhausted", "remaining":{...}, "reset_in_hours":..., "upgrade_url":"/signup"}` (429).
- **스트리밍 중단:** `yield _sse("[⚠️ 응답이 중간에 끊겼습니다. 다시 질문해 주세요.]")`.
- **모바일:** "응답 시간이 초과되었습니다. 다시 시도해주세요." / "서버에 연결할 수 없습니다." / "답변을 받지 못했습니다." / "로그인 실패".

---

## 15. 제약 조건 및 한계 (CONSTRAINTS & LIMITATIONS)

### 15.1 기술적 제약 (Technical)
- **임베디드 Qdrant 동시 1 프로세스:** 인제스트와 API 서버 동시 실행 불가. 락 충돌 시 인제스트가 무한 대기 → 고아 프로세스 정리 후 재실행(§19).
- **지원 브라우저:** 모던 브라우저(ES2020+, `fetch`, Service Worker). PWA 설치는 HTTPS 또는 `localhost` 필요(모바일 `:4174`는 `http://127.0.0.1`로 로컬만).
- **성능 임계값:** `llm_provider_timeout_sec=20`(provider 1개 한도). 스트리밍 첫 토큰 15초 무응답 시 provider 전환. `ef_search_cap=128`. `CHAT_MAX_TOKENS=700`. 채팅 검색 `top_k=5`.
- **메모리:** KURE 임베딩 모델(SentenceTransformer) 로드 시 수 GB. 임베디드 Qdrant는 디스크 기반.
- **Rate limit:** `/chat*` 경로 IP당 `RATE_LIMIT_PER_MINUTE`(기본 60 RPM) / 600 RPH, 초과 시 15분 차단. `RATE_LIMIT_ENABLED=false`로 비활성 가능(§7.2·§7.3).
- **워커:** Dockerfile `--workers 1`(RateLimitMiddleware in-process 딕셔너리 공유 불가 가정).
- **CORS:** `allow_credentials=False`. 인증은 `Authorization` 헤더만.

### 15.2 비즈니스 규칙 (Business Rules)
- **권한 체계:** 공개(채팅/모바일 콘텐츠) / Bearer 사용자(대화기록·피드백·회원 모바일) / `ADMIN_API_KEY`(관리 엔드포인트). `ADMIN_API_KEY=="change-me"`→관리 API 503 비활성. `APP_PASSWORD`는 Streamlit Admin UI 게이팅.
- **데이터 유효성:** `query`는 공백 불가(Pydantic validator). 업로드 파일 `MAX_UPLOAD_SIZE_MB=100`. 문서 버전은 `draft`→`published` 상태 머신.
- **동시성 제한:** SQLite WAL이나 단일 라이터 가정. 임베디드 Qdrant 단일 프로세스. 인제스트 `--reset`는 멱등(삭제 후 재구축).
- **안전 정책:** 입력 룰북(`policy_enabled`) + 출력 LLM-judge + HARD 차단(자살/중독/정죄 → 위기 리소스 핫라인 `1393`/`1577-0199`). `legalism_check_enabled=False`(백그라운드 심사로 충분).
- **다국어 규칙:** `target_lang="auto"`(기본) 또는 미지정 시 `detect_language()`로 질문 언어 감지. 명시값(ko/en/zh/ja) 우선. 비한국어→bge_m3 라우팅(§5.4).

### 15.3 알려진 한계 (Known Limitations)
1. ~~루트 `/health` 없음~~ → **✅ 해결(2026-07-15):** `main.py`에 `GET /health` 추가. compose/deploy.sh 프로브 정상(§18.4).
2. **inert env 전면 해결(2026-07-15):** `RATE_LIMIT_*`/`POLICY_RULES_PATH`(이전 해결) + `TOKEN_QUOTA_*`/`WELCOME_VERSE`/`VAPID_*`/`PUSH_*`/`DATABASE_URL`을 `config.py`에 매핑하고 실제 로직에 연결. 46종 env 매핑 누락 0건 검증(§7.3).
3. ~~Cross-lingual RAG 미완성~~ → **✅ 부분 해결(2026-07-15):** 비한국어 검색 시 다국어 컬렉션(`gospel_bge_m3`)이 비어 있으면 `gospel_kure`로 자동 폴백(§5.4). 진짜 다국어 임베딩 효과를 보려면 bge_m3 컬렉션도 인제스트해야 함(이중 저장 `rag_bilingual_enabled`).
4. **원본 트랜스크립트 노이즈:** 설교 원본에 띄어쓰기 노이즈/타임스탬프 숫자 일부 포함. LLM 응답은 깨끗하나 청킹 품질 여지. (원본 정제는 별도 작업 권장)
5. **임베디드 락 수동 관리:** 고아 프로세스 정리 습관 필요(§19).
6. **테스트 커버리지 부족:** 프론트엔드(Streamlit/모바일) 자동 테스트 없음(§16).
7. ~~배포 healthcheck 깨짐~~ → **✅ 해결(2026-07-15):** `/health` 엔드포인트 추가로 게이트 통과(§18.4).
8. ~~`.env` 시크릿 커밋됨~~ → **✅ 사실 아님:** `.env`는 이미 `.gitignore`(line 2)에 있어 추적되지 않음(`git ls-files`로 확인). 시크릿 노출 위험 없음. (운영 시에도 `.env`를 repo에 커밋하지 말 것)

### 15.5 성능 하드닝 (2026-08 반영)
운영/부하 테스트 기반 개선(성능 종합 점검 리포트). 주요 항목:
- **임베딩 락 분리:** `embedding/factory.py`의 모델 로드 락을 호출 스코프 밖 모듈 레벨로 이동 → 동시 요청 직렬화 제거.
- **동기 DB → `asyncio.to_thread`:** `api/chat.py`의 `get_session()` 동기 쿼리를 `to_thread`로 래핑 → 이벤트 루프 블로킹 방지.
- **Reranker 캐시 키:** `(query, doc)` 조합 키로 변경 → 동일 (쿼리,문서) 재계산 방지.
- **BM25:** `sparse_index`에서 `heapq.nlargest`로 상위 N 추출 → O(N log N) → O(N).
- **FAQ 캐시:** LRU + 상한 바운드 + 질문 원문 보존으로 무한 성장/정규화 편향 방지.
- **sparse 캐시 락:** `sparse_index` 캐시 갱신에 명시 락 추가.
- **DB PRAGMA:** `db.py` 두 엔진 모두에 `WAL`/`busy_timeout`/`foreign_keys` PRAGMA 적용.
- **Rate limit:** 미들웨어 캐시 상한 바운드 추가(무한 딕셔너리 성장 방지).
- **Streamlit 공유 httpx:** `app.py`에서 `@st.cache_resource`로 단일 `httpx.Client` 재사용(요청마다 생성 제거).

### 15.4 토큰 할당량 (Token Quota) — 2026-07-15 연결
- **토글:** `TOKEN_QUOTA_ENABLED`(`config.py: token_quota_enabled`, 기본 `False`). `False`면 `token_service`가 **무제한 스텁**을 반환(기존 동작과 동일 — 할당량 강제 없음).
- **활성 시 동작:** `True`면 채팅 요청마다 `check_consume_and_prepare_profile_sync()`가 `Subscriber.tokens_daily`/`tokens_monthly`를 소비(예약=`settings.token_estimate_per_request`=2000토큰). 잔여가 부족하면 `chat_pipeline.check_input_and_quota()`가 **HTTP 429**(`{error:"token_quota_exhausted", remaining:{daily,monthly,bonus}, reset_in_hours, upgrade_url:"/signup"}`)로 거부. 응답 완료 후 `save_interaction_and_finalize_tokens_sync()`가 예약→실제 차이를 보정(순사용량 반영).
- **할당량:** 일일 `TOKEN_QUOTA_DEFAULT`(기본 20000), 월간 `TOKEN_QUOTA_MONTHLY`(기본 200000). `Subscriber.tokens_bonus`는 추가 허용량(기본 0).
- **주기 리셋:** `Subscriber.tokens_daily_reset`(YYYY-MM-DD) / `tokens_monthly_reset`(YYYY-MM) 컬럼으로 일/월 단위 자동 리셋(`token_service._maybe_reset_periods`). **신규 컬럼은 기동 시 `main.py`의 DB auto-patch(§17.2)가 기존 SQLite에 자동 추가**하므로 마이그레이션 불필요.
- **상태 조회:** `get_quota_status(sub_id)` → 비활성 시 `{"unlimited":True}`, 활성 시 `{daily_used, daily_quota, monthly_used, monthly_quota, bonus}`.
- **운영 주의:** 활성화하려면 `.env`에 `TOKEN_QUOTA_ENABLED=true`만 설정하면 즉시 적용(재배포 불필요, `config.py` 싱글턴이 `.env` 로드).

---

## 16. 테스트 전략 (TEST STRATEGY)

### 16.1 범위
- **단위(Unit):** 도메인 로직 순수 함수 — `addiction_care`(위기/중독 탐지, 안전 메시지, 핫라인 확인), `enhanced_rag` 내부(`DocumentChunker`, `SimpleBM25`, `HybridRetriever._rrf_fusion`, `RAGEvaluator`).
- **통합(Integration):** RAG 파이프라인 e2e — **in-memory Qdrant(`settings.qdrant_url="memory:"`) + `hash` embedder + `heuristic` reranker**로 모델/네트워크 없이 ingest→query→evaluate.
- **E2E(라이브):** `test_adversarial.py` — `httpx`로 실제 API(기본 `http://127.0.0.1:8000`) against 20개 엣지 케이스(admin 인증 업로드+채팅). pytest 수집에서 제외된 독립 스크립트.
- **스모크:** `backend/tests/test_main.py` — `TestClient`로 `GET /`→200, `service`/`version`/`endpoints` 확인.
- **프론트엔드 테스트:** 없음(Streamlit/모바일 자동 테스트 미존재).

### 16.2 프레임워크 / 설정
- `pytest` + `unittest`(`tests/test_addiction_care.py`는 `unittest.TestCase`).
- `pytest.ini`: `pythonpath = .`, `testpaths = backend/tests tests`.
- **모킹 규칙:** `unittest.mock`/`pytest-mock` 미사용. 격리는 **설정 교체**로 달성 — `memory:` Qdrant, `hash` embedder, `heuristic` reranker 주입 → 네트워크/모델 다운로드 없이 결정적. (외부 LLM 호출은 테스트에서 최소화; e2e만 라이브.)

### 16.3 테스트 파일 / 데이터
- `backend/tests/test_main.py` — 스모크.
- `tests/test_addiction_care.py` — `unittest`, 9클래스, 순수 단위(모킹 없음, 직접 함수 호출).
- `tests/test_enhanced_rag.py` — pytest + e2e 러너(`test_pipeline_e2e`: in-memory Qdrant + hash embedder + heuristic reranker).
- `test_adversarial.py` — 라이브 API 20케이스(독립 스크립트).
- 유사 스크래치: `_test_chat.py`, `_test_embed.py`, `_inspect_test_chat.py`, `scripts/test_search_v4.py`.
- **테스트 데이터:** `tests/addiction_test_set.json`(빈), `tests/test_set_info.json`, `data/eval/counseling_classification.jsonl`, `data/eval/flattery_guard.jsonl`, `data/eval/policy_rules.yaml`, `data/enhanced_rag_manifest.json`(e2e가 reset), 모바일 `mobile/data/{bible,hymns,meditation}.json`.

### 16.4 CI 실행
`.github/workflows/deploy.yml`의 test job:
```bash
EMBEDDER=hf_inference HF_TOKEN=dummy_token QDRANT_SPARSE_ENABLED=false \
  pytest backend/tests tests -v
# + alembic upgrade head --sql (dry-run)
```
> 운영 배포 전 검증. 실패 시 배포 중단.

---

## 17. 배포 및 운영 (DEPLOYMENT & OPERATIONS)

### 17.1 로컬 (§3)

### 17.2 Docker Compose (운영 권장)
`docker-compose.prod.yml` + `deploy.sh`:
```bash
cp .env.production.template .env.production # 모든 비밀키
./deploy.sh production
# 또는: docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```
- 3 서비스: `qdrant`(v1.13.4, 헬스체크 `:6333/health`), `backend`(uvicorn `--workers 1`), `ui`(Streamlit).
- 운영 시 `QDRANT_URL=http://qdrant:6333`+`QDRANT_API_KEY`, `RERANKER=bge_m3`, `ADMIN_API_KEY`/`APP_PASSWORD` 강한 값.
- **UI 컨테이너 보안:** 루트 `.env` 마스킹(`/dev/null:/app/.env`) → UI는 `API_BASE`/`APP_PASSWORD`만 주입.

### 17.3 Railway / Fly.io
- Railway: GitHub repo 연결, env 주입, 자동 배포. 볼륨 `/data`.
- Fly.io: `fly launch` → `fly secrets set ADMIN_API_KEY=… GOOGLE_API_KEY=…` → `fly deploy`.

### 17.4 헬스체크 (운영 장애 복구 관련)
- `docker-compose.prod.yml:92` backend healthcheck: `curl -f http://localhost:8000/health`. **2026-07-15에 `main.py`에 `GET /health` 엔드포인트가 추가되어 이제 정상 동작**(인증 불필요, 항상 200 `{status:"healthy",...}`).
- `deploy.sh`도 `/health`로 게이트 → 이제 통과.
- 기타 항상 200인 엔드포인트: `GET /`(정보), `GET /admin/health`(무인증), `GET /rag/health`.

### 17.5 CI/CD 파이프라인
- `.github/workflows/deploy.yml`: push/PR to `main` → test job(`pytest` + alembic dry-run) → `deploy-backend`(Fly.io `flyctl deploy --remote-only`) → `deploy-streamlit`(HuggingFace Spaces force-push) → `migrate`(`alembic upgrade head`). `.github/workflows/rollback.yml`도 존재.

### 17.6 로깅 전략
- `logging_setup.py`: `RotatingFileHandler` → `logs/backend.log`(INFO+, 10MB×5), `logs/errors.log`(ERROR+, 5MB×3), 콘솔. 중복 핸들러 방지.
- `notify_critical(title,msg)` → Windows toast(`plyer`, 60s 쿨다운) — 실패는 삼킴. `alert_on_critical`은 `ErrorMonitorMiddleware`가 호출.
- 로거 네임: `gospel-api.*`(chat/auth/mobile/bible…). `loguru`/`structlog` 미사용(표준 `logging`만).

### 17.7 모니터링 지표
- **Prometheus/`/metrics` 없음.** 모니터링은:
  - **셀프호스팅 트레이스(`tracing.py` `_LocalTraceClient`):** `logs/traces.jsonl`(10MB×5 로테이션, 시크릿 마스킹)에 채팅/생성/이벤트 트레이스 기록. Langfuse는 `LANGFUSE_ENABLED=true`+키 설정 시에만 추가 사용(현재 OFF).
  - **`ErrorMonitorMiddleware` → `AppErrorLog`**(DB) — ERROR/SLOW/CRITICAL.
  - **헬스:** `/admin/health`(무인증), `/admin/services-health`(인증, `healthy|degraded|unavailable`), `/rag/health`, `GET /`.
  - `MONITORING_GUIDE.md`는 Langfuse 알림(error_rate>5%, p95>10s, daily_tokens>100k), Slack `#korean-gospel-alerts`, UptimeRobot, 일일 점검 항목 문서화(헬스 프로브는 `/health` 사용 — §17.4).

### 17.8 장애 복구 절차 (Failure Recovery)
1. **API crash/불응답:** `logs/errors.log` + `AppErrorLog` 확인. 프로세스 재기동(uvicorn). 임베디드 Qdrant stale `.lock`은 lifespan에서 자동 삭제.
2. **인제스트 무한 대기:** 고아 python 프로세스(`Get-CimInstance Win32_Process`/`Stop-Process`) 정리 후 재실행. API 서버 먼저 종료.
3. **DB 스키마 불일치:** `main.py` lifespan 자동 패치(누락 컬럼/인덱스 추가). 수동 시 `scripts/migrate_db.py`/`upgrade/`.
4. **Qdrant 손상:** `--reset` 재인제스트(`index_sermons.py`). 백업은 `scripts/backup.py`(SQLite+Qdrant+uploads), 복원 `restore.py`.
5. **배포 실패(healthcheck):** `/health` 엔드포인트가 정상(200)인지 확인 후 재배포(§17.4).
6. **시크릿 노출:** `.env`의 실제 키가 외부에 유출됐다면 교체 + 운영 secrets(Railway/Fly) 갱신. `.env`는 이미 `.gitignore`에 있어 repo에 커밋되지 않음(§15.3-8). `ADMIN_API_KEY`/`AUTH_SECRET` 강한 랜덤 필수.
7. **LLM 전체 장애:** fallback chain 소진 시 사용자에게 친절 메시지(§14.3). 다른 provider 키 채우면 자동 복구.

### 17.9 보안 체크리스트
- `.env` 절대 커밋 금지(이미 `.gitignore`에 있어 미추적 — §15.3-8). API 키는 운영 시 Railway/Fly secrets 사용.
- `ADMIN_API_KEY`(기본 `change-me`→503), `APP_PASSWORD`, `DIFY_API_KEY`, `AUTH_SECRET`(강한 랜덤) 설정.
- CORS는 실제 도메인만. `allow_credentials=False`.

---

## 18. 기능 추가/수정 가이드 (WHERE TO CHANGE)

| 작업 | 위치 |
|---|---|
| 새 LLM 공급자 | `services/llm/` 신규 모듈 + `factory.get_llm` 등록 + `config.py` 필드 + `.env` |
| 임베딩 교체 | `services/embedding/` + `config.EMBEDDER` + `QdrantStore` 컬렉션명 |
| 검색 로직 | `services/retriever.py`(`_rrf_fusion`, `retrieve`), `services/search_v4.py` |
| 청킹 변경 | `services/chunker.py`(`chunk_text`) + `config.INGEST_CHUNK_*` |
| 시스템 프롬프트/다국어 | `prompts/system.py`(`get_system_prompt`, `build_user_prompt`) |
| 새 API 엔드포인트 | `api/<name>.py` 작성 → `main.py`에 `include_router` |
| 모바일 UI/기능 | `mobile/screens/index.js`, `mobile/services/index.js`, `mobile/styles.css` |
| 통합 앱 UI | `app.py` (Streamlit) |
| 인제스트 파이프라인 | `scripts/index_sermons.py` + `services/ingest_pipeline.py` |
| 정책/룰북 | `POLICY_RULES_PATH` env 경로(기본 `data/eval/policy_rules.yaml`, §7.2·§7.3) |
| DB 스키마 | `models/orm.py` (자동 마이그레이션됨) + 필요시 `scripts/migrate_*.py` |
| Rate limit 한도 변경 | `RATE_LIMIT_ENABLED`/`RATE_LIMIT_PER_MINUTE` env(`config.py` → `middleware/rate_limit.py`, §7.2) |
| 헬스 엔드포인트 추가 | `backend/app/main.py`(`@app.get("/health")`) — 현재 누락 §17.4 |

---

## 19. 수정 이력 (이 문서 작성 시점 기준 verifiable)

세션 중 실제 버그를 진단·수정하고 라이브 사이트에서 검증 완료:

1. **Retriever `_rrf_fusion` 크래시 (매 쿼리 `TypeError`)** — `search_dense/sparse`가 `RetrievedPoint`를 반환하는데 융합이 dict 가정. `retriever.py`에서 각 item을 `{"point": r}`로 정규화 + list-of-lists 구조 보존으로 수정. 검증: `retrieve("복음이란 무엇인가?")` → 관련 청크 5건.
2. **Tencent LLM 빈 출력** — DeepSeek-V4 reasoning 모델은 답이 `content` 아닌 `reasoning_content`에 옴. `tencent.py` `chat()`/`stream()` 모두 `reasoning_content` 폴백. 검증: `answer_len>0`, 스트리밍 정상.
3. **`.env` Qdrant 서버모드(서버 없음) → 임베디드 복원** — `QDRANT_URL=local:./.qdrant_local`, `QDRANT_GRPC=false`.
4. **`index_sermons.py` API 불일치 (인제스트 실패 진짜 원인)** — `store.reset()`→`delete_collection()`, `dense_vectors=`→`dense_vecs=`, `store.client.get_collection().points_count`→`store.count()`.
5. **고아 프로세스로 인한 인제스트 무한대기** — 세션 전환 시 잔존 python 프로세스가 임베디드 Qdrant 락 점유. 기동 전 프로세스 정리 습관화(MEMORY.md 기록).
6. **언어 버튼 추가 (KO/ZH/EN)** — Streamlit `app.py` 사이드바 + 모바일 `screens/index.js` 토글. `target_lang`을 `/chat`·`/chat/stream`에 전송. 검증: `target_lang=en`→영어, `zh`→간체중국어(모델 fluke로 가끔 일본어 나올 수 있으나 정상적으로 중국어 생성).

**인제스트 더블체크 결과:** `points_count=2,335` (기존 381→전체 재구축), 벡터 1024-dim, 빈 청크 0, 44파일 `source_file` 메타 정상, 검색 관련성 `sources=5` + 신학적으로 타당한 답변. 원본 트랜스크립트에 띄어쓰기 노이즈/타임스탬프 숫자가 일부 포함되나 LLM 응답은 깨끗. (원본 정제는 별도 작업 권장)

**본 문서 개정(2026-07-15)으로 추가/수정된 사실:**
- §1(개요)·§5(컴포넌트 I/O·상태)·§6(의존성 매트릭스)·§14(예외 분류·폴백 매트릭스·사용자 메시지)·§15(제약/비즈니스 규칙)·§16(테스트 전략) 신설/대폭 확장.
- §0·§7·§17: 코드 불일치 식별 및 해결(§19 항목 7). `.env`는 이미 `.gitignore`에 있어 미추적임을 명시(시크릿 노출 없음).

**7. 코드 불일치 5건 식별·해결 (2026-07-15, 실제 코드 적용 + 검증):**
   - **(1) `/health` 엔드포인트 부재** → `backend/app/main.py`에 `GET /health`(무인증, `{status:"healthy",...}`) 추가. compose/deploy.sh 프로브 정상화.
   - **(2) `RATE_LIMIT_ENABLED`/`RATE_LIMIT_PER_MINUTE` inert** → `config.py`에 `rate_limit_enabled`/`rate_limit_per_minute` 필드 추가, `middleware/rate_limit.py`가 이를 인식(비활성 토글 + RPM 한도 적용, 기본 60 RPM / 600 RPH / 15분 차단). 검증: 설정 로드 확인.
   - **(3) `POLICY_RULES_PATH` inert** → `config.py`에 `policy_rules_path` 필드 추가, `services/policy.py _load_rules()`가 env 경로를 최우선 후보로 사용. 검증: `.env`의 `data/eval/policy_rules.yaml` 로드 확인(차단 항목 3건).
   - **(4) `user_context` 스키마 누락** → `models/schemas.py ChatRequest`에 `user_context: Optional[str]=None` 추가, `chat_pipeline.build_prompts()`가 시스템 프롬프트에 `[사용자가 제공한 배경 정보]`로 주입, `api/chat.py`(동기+스트림)에서 전달. (프론트 `app.py`가 보내던 `saved_user_info`가 더 이상 드롭되지 않음)
   - **(5) Cross-lingual RAG 빈 결과** → `chat_pipeline.retrieve_and_classify()`에 폴백 추가: 비한국어 임베더 컬렉션(`gospel_bge_m3` 등) 검색이 0건이면 한국어 기본 컬렉션(`gospel_kure`)으로 자동 재검색. 인제스트가 kure만 수행하는 환경에서도 비한국어 검색이 빈 결과를 반환하지 않음.
   - 미해결 잔여 없음: `TOKEN_QUOTA_*`/`WELCOME_VERSE`/`VAPID_*`/`PUSH_*`/`DATABASE_URL` 모두 `config.py`에 매핑·연결 완료(2026-07-15). `.env`는 이미 `.gitignore`에 있어 추적되지 않음(시크릿 노출 없음).

**8. env→config 매핑 전면 정합성 확보 (2026-07-15, 2차):**
   - **문제:** `config.py`에 매핑되지 않은 env가 잔존 — `TOKEN_QUOTA_*`/`WELCOME_VERSE`는 완전히 inert(코드에서 무시), `VAPID_*`/`PUSH_*`/`DATABASE_URL`은 `os.getenv`를 우회 직접 호출(단일 소스 원칙 위배).
   - **조치:** `config.py`에 `database_url`, `vapid_public_key/private_key/subject`, `push_enabled`, `push_hour_kst`, `token_quota_enabled/default/monthly`, `welcome_verse` 필드 추가. `db.py`(`settings.database_url`), `auth.py`(`settings.auth_secret`), `push_service.py`/`push_scheduler.py`(`settings.vapid_*`/`push_*`)의 `os.getenv` 직접 호출을 `settings.*`로 교체.
   - **`TOKEN_QUOTA` 실제 동작 연결:** `token_service`가 `settings.token_quota_enabled`를 게이트로 삼아 일/월간 할당량을 `Subscriber.tokens_daily/monthly`(+신규 `tokens_daily_reset`/`tokens_monthly_reset` 리셋 컬럼) 기반으로 강제. 예약→실제 차이 보정, 소진 시 429. 기본 `False`(무제한)로 기존 동작 보존. 단위 검증 완료(예약/소진/리셋/비활성 경로).
   - **`WELCOME_VERSE` 실제 동작 연결:** `GET /mobile/verse/daily` 응답에 `welcome_verse` 필드로 노출.
   - **검증:** 스크립트로 `.env`+`.env.example`+`docker-compose.prod.yml` 앱 env **46종 전체가 `config.py` 필드에 매핑됨을 확인(누락 0건)**. 전체 수정 파일 `py_compile` 통과, 앱 import 스모크 통과.

---

## 20. 관련 문서 지도 (참조용)

| 분류 | 문서 | 용도 |
|---|---|---|
| 통합(본파일) | `SYSTEM.md` | ★단일 소스 오브 트루스 |
| 진입/운영 | `README.md`, `DEPLOYMENT_GUIDE.md`, `MONITORING_GUIDE.md` | 빌드/실행/운영(일부 서버모드·`/health` 전제는 §0·§17.4 우선) |
| 흐름/책임 | `PROCESS_MAP.md`, `CLAUDE.md` | 모듈 지도/ORM/파이프라인 |
| 설계 노트 | `docs/INGEST_PIPELINE_DESIGN.md`, `docs/ENGINE_V2_DESIGN.md`, `docs/DISCIPLESHIP_TRAINING_DESIGN.md` | 파이프라인/엔진 설계(제안 단계 포함) |
| 모바일 빌드 | `ANDROID_BUILD.md`, `mobile/README.md` | Capacitor Android |
| 비전 | `PROJECT_VISION.md` | 신학 상수/미션 |
| 변경 이력 | `CHANGELOG.md` | 라운드별 누적 |
| 아카이브 | `_archive/` | 폐기/대체 자료 |

> **수정 시:** 본 `SYSTEM.md`를 최신으로 유지하고, 다른 문서와 충돌하면 §0·§19(현재 상태)를 우선할 것.

---

## 21. 채널 아키텍처 · DB 위치 · APK 보관 규칙 (2026-08-18)

> 본 절은 **결제 채널 분리·데이터베이스 위치·APK 아카이빙**의 단일 소스 오브 트루스다.
> "DB가 어디 있는지 모르겠다"는 혼선을 근본 차단하기 위해 작성.

### 21.1 채널 아키텍처 (3채널)

| 채널 | 대상 | 백엔드 | 포트 | 결제 방식 | 패키지 ID |
|---|---|---|---|---|---|
| `global` (다이렉트) | 공식 사이트 직링크 배포 | korean-gospel-ai 메인 (FastAPI) | **8000** | PortOne (한국카드 + 중국 위챗/알리페이 해외채널 내장) | `com.gospelai.app` |
| `googleplay` | Google Play 상점 | korean-gospel-ai 메인 (FastAPI) | **8000** | Google Play Billing (제3자 결제 0 — GP 정책 준수 물리적 격리) | `com.gospelai.app.play` |
| `china` (CN) | 중국 시장 | **`payment-gateway`** (별도 모노레포) | **5000** | payment-gateway 전담 (PortOne/Google SDK OFF, 중국 크레딧 동기화) | `com.gospelai.app.cn` |

- **중국 채널 전용 백엔드 = `payment-gateway`**: `C:\Desktop\korean-gospel-ai\payment-gateway\` (과거 "NEO"로 불리던 모노레포. 명칭은 더 이상 사용하지 않음). 한국 고객 PII와 중국 처리 시스템을 분리하는 결제 게이트웨이.
- 빌드 시 채널 분리는 `scripts/build-config.js`로 처리:
  - `node scripts/build-config.js android --market=cn` → `CN_API_BASE`(기본 `http://127.0.0.1:5000`) 주입, Google SDK OFF.
  - `node scripts/build-config.js android --channel=googleplay` → PortOne SDK 완전 제거, 런타임 채널=`googleplay`(GP Billing 폴백).
  - `node scripts/build-config.js android` (기본) → `GLOBAL_API_BASE`(기본 `http://127.0.0.1:8000`), PortOne + Google SDK ON.

### 21.2 데이터베이스 위치 (헷갈리지 않게 명시)

| 용도 | DB | 위치 | 엔진 |
|---|---|---|---|
| **앱 사용자 / 설교 / 대화 / 크레딧(글로벌)** | `.gospel.db` | `C:\Desktop\korean-gospel-ai\.gospel.db` | SQLite (WAL, 자동 마이그레이션) |
| **중국 채널 결제 / 크레딧 동기화 원장** | `gospel_pay_db` | `payment-gateway` 전용 Postgres (컨테이너 `gospel-pay-db`, 호스트 `:5432`) | PostgreSQL 15 |
| **중국 채널 결제 큐/캐시** | redis | 컨테이너 `gospel-pay-redis` (호스트 `:6379`) | Redis 7 |

- **사용자 계정(로그인/회원가입)은 모두 `.gospel.db`(메인 백엔드:8000)에 저장된다.** 중국 채널도 동일 사용자 DB를 공유하되, 결제/크레딧 원장만 `payment-gateway`의 Postgres에 분리 보관.
- `payment-gateway` 기동 전 Postgres(`gospel-pay-db`)가 없으면 결제 API가 동작하지 않음. `docker compose -f payment-gateway/docker-compose.payment-gateway.yml up -d db redis` 로 먼저 띄울 것.

### 21.3 APK 보관 규칙 (아카이브)

- **단일 폴더 원칙:** 모든 산출물은 `C:\Desktop\korean-gospel-ai` 안에만 존재. 별도 프로젝트 폴더로 분산 금지.
- **아카이브 구조:**
  ```
  releases/
    MANIFEST.json          # 채널별 릴리스 메타데이터(단일 소스)
    global/                # 글로벌/다이렉트 APK
    googleplay/            # GP 상점용 APK (제3자 결제 0)
    china/                 # 중국 채널 APK (payment-gateway:5000 연동)
  ```
- **릴리스 등록:** 빌드된 APK는 `scripts/release-channel.js`로 아카이브 + MANIFEST 갱신.
  ```
  node scripts/release-channel.js --channel=china --apk=android/app/build/outputs/apk/release/app-release.apk --version-name=1.0.1 --version-code=2
  ```
- **버전 단일 소스:** `version.json`(저장소 루트)의 `versionName`/`versionCode`가 정설. `scripts/build-config.js`가 이를 `android/app/build.gradle`로 동기화(수동 불일치 방지).
- `download.html`(사이트 직링크 배포용)은 `./releases/global/flow-ai.apk`를 가리킴. 중국 배포는 별도 china 다운로드 페이지에서 `./releases/china/*.apk` 노출 권장.
- `releases/`는 `.gitignore` 대상(대용량 바이너리) — 로컬/배포 서버에만 보관, git 추적 안 함.

### 21.4 payment-gateway (구 NEO) 운영 요약

- 경로: `C:\Desktop\korean-gospel-ai\payment-gateway\` (모노레포: `apps/api` Node/NestJS, `apps/user-web`/`apps/admin-web` React, `packages/shared`).
- 패키지 스코프: `@gospel-pay/*` (구 `@neo/*`). 컨테이너: `gospel-pay-api`(5000) / `gospel-pay-db` / `gospel-pay-redis`.
- 컴포즈: `payment-gateway/docker-compose.payment-gateway.yml` (루트 `docker-compose.yml`과 충돌 안 함).
- 관리자 로그인: `POST /api/admin/auth/login` (`ADMIN_EMAIL`=`piaoyhyh@gmail.com`, `ADMIN_PASSWORD` env). 비번 복구 플래그 `ADMIN_PASSWORD_FORCE_SYNC=true`(env 일치 시 해시 재동기화).
- 중국 크레딧 동기화: `CHINA_CREDIT_API_URL`/`CHINA_CREDIT_API_KEY` env로 외부 중국 크레딧 서버와 연동.
