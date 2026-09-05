# — Project Knowledge Base

> 이 파일을 먼저 읽으세요. 전체 코드를 탐색할 필요 없이 프로젝트 구조와 패턴을 이해할 수 있습니다.
> 마지막 업데이트: 2026-07-20

## 빠른 참조

| 질문 | 답변 |
|------|------|
| **venv 경로** | `venv/` (streamlit, alembic 있음). `.venv312/`는 보조. |
| **실행 명령** | `venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` |
| **모바일 PWA** | `venv/Scripts/python.exe -m http.server 4174 -d mobile --bind 127.0.0.1` |
| **Streamlit** | `venv/Scripts/streamlit.exe run app.py --server.port 8501` |
| **DB** | `.gospel.db` (SQLite, WAL 모드, 자동 마이그레이션) |
| **주요 LLM** | `gemini` (기본), fallback chain: openai, claude, deepseek, ollama |
| **임베딩** | `kure` (한국어 특화), `bge_m3` (다국어) |
| **CORS** | `.env`에 `CORS_ORIGINS` 추가 필수 (localhost:4174, capacitor://localhost 등) |

## 디렉토리 구조

```
root/
├── backend/app/
│ ├── api/ # 15개+ 라우터 (chat, mobile, auth, admin, content_admin, trending...)
│ ├── services/ # 90+ 서비스 모듈 (retriever, search_v4, trending, insight, subscriber, faq_cache...)
│ ├── models/ # orm.py (18개 테이블) + schemas.py (Pydantic 요청/응답)
│ ├── middleware/ # error_monitor, rate_limit
│ ├── prompts/ # system.py, classifier.py, clarifier.py, policy_judge.py
│ ├── config.py # Pydantic Settings (모든 환경변수)
│ ├── db.py # get_session(), init_db(), 자동 마이그레이션
│ └── main.py # FastAPI app + lifespan (KURE 로딩, BM25 재구축, push scheduler)
├── mobile/ # PWA (index.html, app.js, styles.css, sw.js, manifest) — "Espresso Atelier" 다크 디자인
├── admin/ # Streamlit 관리자 (pages/, lib/api_client.py, lib/auth.py)
├── user/ # (구 user/app.py → _archive/user_app.py 로 이동, 현재 사용자 앱은 루트 app.py)
├── scripts/ # init_db.py, ingest_documents.py, seed_*.py, run_eval.py, publish_documents.py, upgrade/*
├── data/ # bible/, music/, documents/, uploads/, eval/
├── docs/ # 설계 문서 (DISCIPLESHIP_TRAINING_DESIGN.md 등)
├── app.py # 루트 통합 Streamlit 사용자 앱 (채팅 UI)
├── .env # 실제 환경변수 (git 무시)
├── .env.example # 환경변수 템플릿
├── requirements.txt # Python 의존성
├── capacitor.config.json # Capacitor Android 설정
└── package.json # Node (Capacitor)
```

## ORM 모델 (15개) — `backend/app/models/orm.py`

| 모델 | 테이블명 | 용도 |
|------|---------|------|
| SourceArtifact | source_artifact | 업로드된 원본 파일 + 추출 텍스트 |
| Document | document | 논리 문서 (doc_key로 식별) |
| DocumentVersion | document_version | 버전별 콘텐츠 (draft/published) |
| IndexSnapshot | index_snapshot | Qdrant 동기화 메타 |
| Subscriber | subscriber | 사용자 프로필, 구원 상태, 토큰, 다락방 |
| Interaction | interaction | Q&A 1턴 (피드백, 인용, 추적 포함) |
| AuditLog | audit_log | 상태 변경 로그 |
| PromptTemplate | prompt_template | 시스템 프롬프트 |
| Category | category | 분류 체계 (faith_stage, emotional_state...) |
| SalvationJourney | salvation_journey | 영적 여정 타임라인 |
| AppErrorLog | app_error_log | 런타임 에러 로그 |
| BackgroundJob | background_job | 비동기 작업 진행 추적 |
| DocumentDraft | document_drafts | 편집 중 충돌 해결 |
| ContentLink | content_link | YouTube/Spotify 영성훈련 링크 |

## API 라우터 등록 순서 (`main.py`)

1. `chat` — (root) POST /chat, /chat/stream, /feedback, /chat/greeting, /chat/ping
2. `retrieval` — (root) POST /retrieval (Dify 호환)
3. `admin` — /admin (health, collections, taxonomy, settings)
4. `documents` — /documents (업로드, 버전, publish)
5. `memory` — /memory (대화 기록)
6. `prompts` — /prompts
7. `subscriber` — (root) /subscribers/me, /admin/subscribers/* (+ /admin/bot/stats, /admin/bot/list 봇관리)
8. `auth` — /auth (signup, login, me)
9. `drafts` — /drafts
10. `jobs` — /jobs
11. `mobile` — /mobile (PWA 전용: legal, music, bible, push, profile, history, content)
12. `content_admin` — /admin/content (영성훈련 링크 CRUD)
13. `trending` — /trending (사용자: cards, insight, answers) + /admin/trending, /admin/insight (인기Q&A+통찰)

## 모바일 API 접근 규칙

**공개** (Bearer 불필요): `/mobile/legal`, `/mobile/music`, `/mobile/music/{id}/stream`, `/mobile/bible/read`, `/mobile/push/vapid`, `/mobile/content`

**회원** (`get_current_user`): `/mobile/profile`, `/mobile/history`, `/mobile/verse/daily`, `/mobile/bible/search`, `/mobile/bible/refs`, `/mobile/push/subscribe`, `/mobile/push/test`

## 채팅 파이프라인 (`chat.py` + `chat_pipeline.py`)

1. 인증 (Bearer → sub_id, 없으면 DEFAULT_USER)
2. 입력 정책 검사
3. 프로필 로드 + 토큰 할당량 체크
4. ⚡ 병렬: LLM 입력 분류 + 검색 (v4: MMR + 압축)
5. 재질문 분기 (Clarity.ambiguous → clarifier 응답)
6. ⚡ 백그라운드: 프로필 업데이트 + 구원 감지
7. 프롬프트 구성 (메모리 + 시스템 + 수정 + 구조)
8. LLM 답변 (스트리밍 또는 동기, fallback 체인)
9. 품질 필터 (아첨 + 율법주의)
10. 안전망 (중독/위기)
11. 온보딩 질문 추가
12. 토큰 정산 + Interaction 저장

> **검색 엔진 현황 (2026-07-16 확정)**: 라이브 단일 엔진은 **`search_v4.AdvancedSearchEngine`** (hybrid BM25+dense+RRF+cross-encoder rerank+MMR+압축). 구형 `rag_engine.py`는 데드코드(라이브 미호출)로 폐기 대상. `enhanced_rag`는 bilingual 기본 ON이라 한국어 제품에 부적합 → `get_pipeline`을 `cfg.bilingual.enabled = settings.rag_bilingual_enabled` 무조건 대입으로 수정해 `RAG_BILINGUAL_ENABLED=false` 적용 가능. 한국어 청킹은 `services/spacing.py`(Kiwi 싱글턴) 도입으로 ASR 띄어쓰기 파괴·문장분리 '다' 과분리 버그 해결.

## 관리자 API 인증 패턴

```python
from .auth import check_admin as _check_admin

@router.get("/admin/...")
def endpoint(authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization) # ADMIN_API_KEY == "change-me" → 503
    # ... 실제 로직
```

## Streamlit 페이지 패턴

```python
import sys; from pathlib import Path
_ROOT = Path(__file__).resolve().parent
while _ROOT.name in ("pages","lib"): _ROOT = _ROOT.parent
_ROOT = _ROOT.parent
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))

import os, streamlit as st; from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")
from admin.lib.auth import gate; gate(os.getenv("APP_PASSWORD",""))
# ... api_client 함수로 백엔드 호출
```

## 이미 수정 완료된 것들 (재수정 금지)

아래는 이미 확인/수정 완료되어 다시 볼 필요 없는 항목들입니다:

- CORS: .env에 `http://127.0.0.1:4174, http://localhost:4174` 포함됨
- SW 보안: API 응답 캐싱 차단, 정적 카탈로그만 선택적 캐싱
- SW 업데이트: skipWaiting + clients.claim 적용됨
- content_service: setattr 화이트리스트, source/URL 불일치 검증, _NULLABLE_FIELDS
- ContentLink ORM: NOT NULL 컬럼 전부 추가, 인덱스 생성
- DB 자동 마이그레이션: main.py lifespan에서 신규 테이블/컬럼/인덱스 자동 생성
- bible_service: 경로 순회 차단, BOM 처리, 빈 결과 미캐싱
- ChatService: 실제 /chat API 연동, AbortController 15초 타임아웃 (작업 A, 2026-07-11)
- bible_service: list_available_books 하위 디렉토리(개역개정/,화합본/) 스캔 + 중복제거 (작업 B, 2026-07-11)
- chat.py: max_tokens 700(_settings.chat_max_tokens), FAQ 정적 캐시 동기 /chat 적용, legalism_check_enabled 기본 False (작업 C, 2026-07-11)
- MeditationService: /mobile/content?category=devotion 연동(로컬 JSON 폴백 유지) (작업 D, 2026-07-11)
- 성경 다운로드: getbible.net 차단으로 scrollmapper/bible_databases(GitHub raw) 대체, 테스트 모드(요한복음/约翰福音) 성공 — 전체 66권은 사용자 요청 시 다운로드 (작업 E, 2026-07-11)
- Tencent LLM: backend/app/services/llm/tencent.py 신규 추가, config/factory/fallback 등록, .env TENCENT_API_KEY 추가 (작업 F, 2026-07-11)
- auth: guest_sub_id 덮어쓰기 차단 (auth_status 검증)
- chat.py: value=0 피드백 클리어 허용
- app.js: debounce, loadHistory 캐싱, scrollIntoView, chatInFlight 잠금, messages cap
- app.js: Enter 키 auth 제출, embed_url 없으면 window.open, 탭 전환 시 embed 정리
- app.js: daily-verse 삭제 방지, refreshHistory force=true, 이중 append 제거
- MMR: word set precompute, 남은 인덱스 추적으로 O(n²) 제거
- Reranker: OrderedDict LRU (full-clear → popitem)
- retriever: hard floor 100 → max(top_k*4, 30)
- search_v4: ContextCompressor asyncio.gather 병렬화
- dedup: SQL LIKE 필터링 + limit 20
- sparse cache: MD5 제거, text 직접 dict 키
- push_service: platform 기반 분기, webpush timeout=10
- push_scheduler: async 코루틴 직접 등록 (새 루프 생성 제거)
- push_unsubscribe: Body(Optional[dict]) → 422 방지
- Subscriber ORM: 누락된 토큰/bot 컬럼 전부 추가
- scripts/ingest_documents.py: 신규 API로 재작성
- scripts/init_db.py: get_session() 패턴 적용
- PWA UI: 전체 재디자인 완료 (v2 Professional Design System)
- enhanced_rag 번역: LLMTranslator 실제 Tencent DeepSeek-V4 구현(async, glossary 폴백), TranslationManager.translate_chunk async 전환 (작업 G)
- publish_service: publish_version()/finalize_publish()에 enhanced_rag 이중 저장 인제스트 통합 (graceful degradation, 예외 삼킴) (작업 H)
- chat_pipeline: retrieve_and_classify()에 _search_enhanced() 병렬 코루틴 + _merge_enhanced() 병합(id 중복 제거, graceful degradation) — 주의: 실제 API는 `pipeline.query()` (get_pipeline().retrieve() 아님) (작업 I)
- prompts/system: _ALLOWED_OUTPUT_LANGS에 "zh" 추가 + _safe_target_lang zh 차단 해제 (작업 J)
- scripts/migrate_to_enhanced_rag.py: published DocumentVersion 순회 → enhanced_rag 재인제스트 마이그레이션 스크립트 신규 (작업 K)
- enhanced_rag/config: BilingualConfig.enabled=True, translator="llm" 기본값 변경 + .env LLM_PROVIDER=tencent (rag_bilingual_enabled 기본 True) (작업 L)
- bilingual_smoke.py: translate_chunk async 전환 대응 + translator 기본값 "llm" 반영 (G~L 일관성)

## 최근 대규모 업데이트 (2026-07-16 ~ 2026-07-20) — 요약

아래는 이 문서 최초 작성(2026-07-06) 이후 대규모로 추가/수정된 항목들로, 기존 "이미 수정 완료된 것들" 목록에 통합 기록한다.

- **인기 Q&A + 통찰 시스템 (2026-07-16)**: `trending_service`(Wilson Score+임베딩 클러스터링), `insight_engine`(4-step LLM: 루트원인/진단/호평답변/성찰), `edit_diff`/`edit_validator`(XSS 방지, 한글 diff), `trending_scheduler`(1분 APScheduler), `api/trending.py` 신규 라우터. `orm.py` 3 테이블 추가(**QATrendSnapshot, QAAdminEditLog, QAEditDraft** + EditFieldType/ReviewStatus/SnapshotType Enum), `schemas.py` 17종 Pydantic. `admin/pages/18_📈_인기QA관리.py`(4탭), 루트 `app.py` 트렌딩 카드+insight 패널.
- **검색 엔진 확정 (2026-07-16)**: **`search_v4.AdvancedSearchEngine` = 라이브 단일 엔진**. `rag_engine.py`=데드코드(폐기), `enhanced_rag`=redundant/중국어 secondary.
- **한국어 청킹 수정 (2026-07-16)**: `services/spacing.py`(Kiwi 싱글턴, fail-open) 신설 → `normalizer` 최선단 + `chunker.split_korean_sentences` Kiwi 교체. ASR 띄어쓰기 파괴·문장분리 '다' 과분리 해결 (기존 인덱스 재인덱스 권장).
- **bilingual 결정적 교정 (2026-07-16)**: `enhanced_rag/__init__.get_pipeline`이 `RAG_BILINGUAL_ENABLED=false`여도 기본 True 유지 → `cfg.bilingual.enabled = settings.rag_bilingual_enabled` 무조건 대입으로 수정.
- **봇 관리 (2026-07-17)**: `admin/pages/12_🤖_봇관리.py` 구현, `subscriber_service` bot 필드(`flagged_as_bot`/`bot_score`)+`_OPERATOR_ONLY` 화이트리스트, `subscriber.py` `/admin/bot/stats`·`/admin/bot/list`, `schemas.ProfileUpdateReq` bot 필드, `api_client` bot_stats/bot_list/bot_toggle_flag.
- **UI 전면 재설계 (2026-07-17)**: 루트 `app.py`·`admin/app.py` "Sacred Garden · Editorial Luxe"(세리프+에메랄드+황동), 모바일 PWA "Espresso Atelier" 다크, iPad 스와이프 최적화(`admin/lib/mobile_swipe.py`).
- **RAG 데드코드 감사 (2026-07-17)**: `search_optimizer.merge_duplicate_candidates`, `chunker.chunk_documents`, `embedding/factory.list_supported`, `faq_cache.faq_stats`/`clear_faq_cache`, `rag_engine`(전체), `enhanced_rag/bilingual_smoke` 확정 데드 → 삭제 보류(기록만).
- **publish 이중저장 버그 (2026-07-17)**: `rag_bilingual_enabled=false`여도 bge-m3 로드→이중저장 → `publish_service._ingest_to_enhanced_rag` 상단 `if not settings.rag_bilingual_enabled: return` 가드 추가.
- **백엔드 전수 점검 수정 (2026-07-20)**:
  - `faq_cache`: `faq_min_hits` 임계치 무시 → 도달 전엔 hit 누적만, 임계치 이상 조회 시만 캐시 서빙.
  - `api/chat.py` [보안]: `/chat`·`/chat/stream`의 `req.history`를 `sanitize_history` 없이 append → system-role 프롬프트 인젝션(LLM01) 가능 → 두 경로 모두 `sanitize_history` 적용.
  - `api/chat.py` [일관성]: sync `/chat` FAQ 히트 시 Interaction 저장 누락 → `save_interaction_and_finalize_tokens(estimated=0)` 추가(스트리밍과 동일).
  - `services/retriever.py` [A/B 불변식]: 부스트 곱셈형 `base*(1+tb)*(1+pb)` → 덧셈형 `base*(1+tb+pb)`로 수정해 `enhanced_rag/pipeline._apply_profile_boost`와 공식 일치 (부스트 단일 소스 불변식).

## 배치 파일

- `STEP1_INSTALL.bat` → 패키지 설치
- `STEP2_INDEX.bat` → DB 초기화 + 문서 인덱싱 (init_db.py + ingest_documents.py)
- `STEP3_START.bat` → API(:8000) + 앱(:8501) 실행
- `STEP4_TUNNEL.bat` → Cloudflare Tunnel
