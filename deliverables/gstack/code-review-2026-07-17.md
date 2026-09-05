# 코드 리뷰 — korean-gospel-ai (백엔드 핫패스 + 감사 지적 모듈)

> 검토 일시: 2026-07-17
> 범위: 제가 수정한 코드(OPT-A/B/C/D, P10-9) + 대규모 변경 고위험 파일(token_service, vector_store) + 감사 지적 모듈(main, enhanced_rag, auth, config, base, faq_cache, connections)
> 방법: `py_compile` 전수 + `pyflakes` + 핵심 파일 정밀 독해 + 하위 에이전트 스캔. 각 항목은 **실제 코드 라인으로 확인**함.

---

## 0. 검증 결과 요약

| 항목 | 결과 |
|---|---|
| 문법 오류 (`py_compile` backend/app 전체) | **0건 통과** |
| 미정의 이름 (`pyflakes`) | **0건** (런타임 NameError 없음) — 미사용 import/변수만 40여 건(치명하지 않음) |
| 제가 수정한 OPT-A/B/C/D, P10-9 | OPT-C·OPT-D 정상 / OPT-A 1건의 경미한 비대칭 발견 / OPT-B 정상 |
| 신규 P0/P1 버그 | **P0 4건, P1 2건** 확인 (아래 상세) |

---

## 1. P0 — 블로커 (기능/보안, 즉시 조치 권고)

### P0-1. `/health` 가 항상 healthy 를 하드코드 반환 — `backend/app/main.py:359-365`
- **범주**: 논리결함 · 완전성(헬스체크 누락)
- **원인**: 엔드포인트가 정적 딕셔너리를 즉시 리턴. DB / Qdrant / LLM 연결 상태를 전혀 확인하지 않음. K8s/Docker 가 프로브로 사용하므로, 워커가 죽었거나 Qdrant 락에 걸려 응답 불가 상태여도 `healthy` 로 판단해 트래픽을 계속 라우팅.
- **수정 방안**: liveness(`/health`)와 readiness(`/ready`) 분리. `/ready` 에서 `DB ping + Qdrant count() + (선택) LLM 1토큰 호출` 수행, 실패 시 503. `/health` 는 프로세스 생존만 확인.
- **영향**: 운영 신뢰성. 죽은 워커에 트래픽 라우팅 → 사용자 체감 "응답 없음".

### P0-2. `/rag/*` 4개 엔드포인트 무인증 — `backend/app/api/enhanced_rag.py:127, 149, 164, 180`
- **범주**: 보안(인가 누락)
- **원인**: `require_admin` 이 적용된 것은 `POST /ingest`(106), `DELETE /documents/{id}`(155), `PUT /config`(170) 뿐. **`POST /query`(127), GET `/documents`(149), GET `/config`(164), `POST /evaluate`(180) 에는 `Depends(require_admin)` 가 없음.** 누구나 KB 를 질의·열람·설정 조회·평가 실행 가능.
- **수정 방안**: 위 4개(및 정보노출 가능한 `/health` 제외)에 `Depends(require_admin)` 부착. 프론트엔드/관리UI 호출부가 `X-API-Key` 를 보내는지 사전 grep 필요(`app.py`/`admin/`/`mobile/`).
- **영향**: 지식베이스 데이터 노출 + 무단 평가 트래픽(비용).

### P0-3. `llm_provider_timeout_sec=20` 이 reasoning 모델 실제 지연(~78s) 과 불일치 — `backend/app/config.py:25`
- **범주**: 설정·논리(경계조건)
- **원인**: 타임아웃(20s)이 실제 모델 응답(78s)보다 짧음. `connections.deepseek()` 는 `read=timeout+5s` 로 클라이언트 타임아웃을 걸어 둠. tencent reasoning 모델은 1회 호출 ~78s 소요 → 호출 도중 타임아웃→fallback 체인 발동→의도치 않은 다른 provider 로 답변 생성(품질 저하/지연).
- **수정 방안**: `llm_provider_timeout_sec` 을 ≥90 으로 상향(또는 provider 별 타임아웃). `.env` 오버라이드 확인 필수.
- **영향**: 채팅 답변 품질/지연. 기능적 결함.

### P0-4. 기본 약한 비밀 — `backend/app/config.py:110-112` (`admin_api_key="change-me"`, `auth_secret=""`)
- **범주**: 보안(기본 자격증명)
- **원인**: `.env` 미설정 시 기본값 사용. `auth.py` 는 `== "change-me"` 일 때 관리자 비활성화(503)로 1차 방어하나, `auth_secret=""` 이면 `.auth_secret` 파일 자동생성 또는 `admin_api_key` 파생값으로 폴백(경고만).
- **수정 방안**: 운영 `.env` 에 강력한 `ADMIN_API_KEY`·`AUTH_SECRET` 설정 강제(부재 시 기동 실패 또는 명시적 경고). 기본값을 빈 문자열/랜덤으로 변경.
- **영향**: 운영 환경에서만 실질 위험(로컬 개발은 저위험).

---

## 2. P1 — 고위험 (확인됨)

### P1-1. 토큰 정산 `actual_tokens=0` 시 과금 버그 — `backend/app/services/token_service.py:297`
- **범주**: 논리(토큰 수식) · 경계조건
- **원인(확인)**: `delta = (actual_tokens or estimated) - estimated`. `actual_tokens` 가 실제로 `0`(FAQ히트 아님, 정상 경로에서 빈/필터링 응답)이면 `0 or estimated == estimated` 가 되어 `delta = 0`. 그런데 `check_consume_and_prepare_profile_sync`(line 237-239) 는 이미 `tokens_daily/monthly += estimated`(기본 2000) 를 예약함. 따라서 실사용 0토큰임에도 예약분 2000을 그대로 청구 → **사용자 과금**.
  - 참고: FAQ 스트림 경로(`chat.py:419-420`)는 `actual_tokens=0, estimated=0` 이고 예약도 스킵하므로 과금 없음. 버그는 **일반 경로**(`estimated=2000` 예약, `actual` 이 0이 될 수 있음)에서 발동.
- **수정 방안**:
  ```python
  # None(측정불가) 과 0(실측 0토큰) 을 구분
  actual = estimated if actual_tokens is None else actual_tokens
  delta = actual - estimated
  ```
- **영향**: `token_quota_enabled=True`(기본 False) 일 때만 발동하는 **잠재 버그**이나, 할당량 켜면 실결함.

### P1-2. Qdrant 재시도 무력화 + 검색 예외 침묵 — `backend/app/services/vector_store.py:77-89` + `340/365/386/406`
- **범주**: 예외처리 누락 · 신뢰성(에러 마스킹)
- **원인(확인)**:
  1. `_retry_qdrant_call` 가 `except (ConnectionError, TimeoutError)` 만 잡음. qdrant-client 는 실제로 `requests.exceptions.Timeout` / `requests.exceptions.ConnectionError` / `qdrant_client.http.exceptions.UnexpectedResponse` 를 발생시킴 → builtin 형이 아니므로 재시도 분기로 안 들어가고 즉시 전파(또는 아래의 `except Exception: return []` 으로 삼킴).
  2. `search_dense`(340,365)·`search_sparse`(386,406) 가 `except Exception: return []` 로 **모든 예외를 빈 리스트로 침묵**. 일시적 Qdrant 네트워크 끊김에도 재시도 없이 빈 결과 → 사용자에게 "관련 본문 없음"으로 노출, 로그에도 안 남음(일부만 warning).
- **수정 방안**:
  ```python
  from requests.exceptions import Timeout as ReqTimeout, ConnectionError as ReqConnError
  from qdrant_client.http.exceptions import UnexpectedResponse
  except (ConnectionError, TimeoutError, ReqTimeout, ReqConnError, UnexpectedResponse) as e:
  ```
  그리고 search_* 에서 빈 `[]` 무단 반환 대신: 재시도 후에도 실패하면 로그 기록 + 상위로 예외 전파(또는 명시적 "검색 일시장애" 응답). 최소한 warning 로그는 남겨야 함.
- **영향**: 검색 신뢰성. 일시장애가 조용히 빈 답변으로 이어짐.

---

## 3. P2 — 중위험 (확인됨 또는 스캔 확인)

### P2-1. `_sparse_cache` 동시성 락 없음 — `backend/app/services/vector_store.py:153-170`
- **범주**: 동시성
- **원인(확인)**: 모듈 전역 `_sparse_cache` dict 가 `asyncio.to_thread` 워커 다수에서 변형됨. `if text in cache / del / cache[text]=` 가 락 없이 수행되어, 동시 eviction(`del`) 과 insert 가 엇갈리면 `KeyError` 또는 항목 유실 가능.
- **수정 방안**: `_sparse_cache_lock = threading.Lock()` 추가 후 read-modify-write 를 임계구역으로 감쌈. 또는 `cachetools.LRUCache` 사용.

### P2-2. `upsert` 길이 검증 없음 — `backend/app/services/vector_store.py:444-458`
- **범주**: 경계조건 · 예외처리
- **원인(확인)**: `dense_vecs[i]`, `sparse_vecs[i]`, `extra_vecs[name][i]`, `metadatas[i]`, `texts[i]` 를 위치로 인덱싱하되 길이 일치 검증 없음. 호출측에서 길이가 어긋나면 루프 중간 `IndexError` → 부분 points 리스트로 실패.
- **수정 방안**: upsert 시작 시 `assert len(ids)==len(texts)==len(dense_vecs)` (및 sparse/extra 일치) 후 아니면 명확한 `ValueError`.

### P2-3. `text_from_*` 가 `reasoning_content` 로 폴백(사고사슬 유출 위험) — `backend/app/services/llm/base.py:16,21`
- **범주**: 보안(정보노출) · 논리
- **원인(확인)**: `return (content or reasoning_content or "")`. 본 프로젝트의 tencent deepseek-v4-flash 는 답이 `reasoning_content` 에 오므로 의도된 채널이나, 모델이 CoT(`reasoning_content`) 와 최종답(`content`) 을 분리해서 스트리밍할 경우 CoT 가 사용자에게 그대로 노출됨. 현재 동작은 "answer 채널" 이지만 방어 코드가 없음.
- **수정 방안**: content 와 reasoning_content 를 별도 추적. 스트리밍에서는 content 델타만 사용자에게 emit, reasoning_content 는 관측용 로그만. 폴백은 `content` 가 비었을 때만(현행 유지) 하되, CoT 위상은 emit 하지 않도록 버퍼링.

### P2-4. FAQ 캐시 히트 시 상호작용 저장 비대칭 — `backend/app/api/chat.py:107-132` vs `412-422`
- **범주**: 완전성 · 일관성(데이터 무결성)
- **원인(확인)**: `/chat`(비스트림) FAQ 히트는 `Interaction` 를 저장하지 않고 즉시 리턴. `/chat/stream` FAQ 히트는 `save_interaction_and_finalize_tokens` 를 호출. 코드 주석은 "일반 경로와 일관성" 이라지만 정반대(비대칭). 분석/통계 데이터 누락 불일치.
- **수정 방안**: 둘을 정렬 — FAQ 는 정적이므로 **양쪽 모두 저장 안 함**(권장) 또는 양쪽 모두 저장. 일관성만 맞추면 됨.

### P2-5. `_JOSA_RE` 를 호출마다 재컴파일 — `backend/app/services/faq_cache.py:42`
- **범주**: 성능(핫패스)
- **원인(확인)**: `_normalize_query` 내부에서 매 호출 정규식 컴파일. 모든 채팅 요청이 FAQ 조회를 하므로 중복 컴파일 발생.
- **수정 방안**: `search_v4.py` OPT-C 와 동일하게 모듈 레벨로 hoist.

### P2-6. FAQ 캐시 무제한 성장 — `backend/app/services/faq_cache.py:55`
- **범주**: 메모리
- **원인(확인)**: `_cache` 가 TTL 로만 만료, distinct 쿼리 폭증 시 상한 없이 증가(프로세스 로컬).
- **수정 방안**: 최대 항목 수 캡(LRU) 또는 `cachetools.LRUCache(maxsize=...)`.

### P2-7. OPT-A 잔여 미사용 import — `backend/app/api/chat.py:29,49`
- **범주**: 코드 품질(데드코드) — 버그 아님
- **원인**: OPT-A 리팩터 후 `from fastapi.responses import StreamingResponse`(로컬 import 로 대체) 와 `from ..services.search_v4 import get_search_engine`(미사용) 가 잔류.
- **수정 방안**: 두 import 제거(프로젝트 백로그 A5 "미사용 import 정리" 와 병합).

---

## 4. P3 — 저위험 / 정보

- **`main.py:333-357` `root()`** — `qdrant_url`, `llm_provider`, `embedder` 를 인증 없이 노출(경미한 정보노출). `qdrant_url` 항목 제거 권장.
- **`auth.py`** — 토큰 무효화/리볼케이션 없음(`/logout` 은 클라이언트 측만). 세션 탈취 방어 범위 밖. 스코프상 수용 가능.
- **`pyflakes` 미사용 import 40여 건** — `chat_pipeline.py`(Header/get_session/tracing/addiction_care), `db.py:134`, `main.py:220`, `admin.py`, `auth.py:21` 등. 런타임 영향 없음, 정리 권장.
- **`connections.py`** — `_make_client` 가 내부에서 `_client_lock`(DCL) 보유. 하위 에이전트가 지적한 "락 누락 경쟁"은 **사실 아님**(129행 `with _client_lock` 확인). `_once`/`_recover_client` 모두 안전.

---

## 5. 검증 완료 — 버그 없음(안전 확인)

- ✅ `py_compile` backend/app 전체 통과 — 문법 오류 0.
- ✅ `pyflakes` 미정의 이름 0 — NameError 리스크 없음.
- ✅ **OPT-C** (`search_v4.py`): `_WORD_RE`/`_SENT_SPLIT_RE`/`_STOPWORDS` 모듈레벨 hoist 정상, 동작 동일.
- ✅ **OPT-D** (`chat_pipeline.py`): 루프 내 `import re` → 모듈 상수로 교체(py_compile 통과, 저위험).
- ✅ **OPT-B** (`logging_setup.py`): `RedactingFilter` 1회 부착, `_looks_like_secret` 키워드 사전게이트 정상.
- ✅ **faq_cache 반환형**: `get_cached_answer` → `(answer, sources)`, `sources` 는 `build_cited(items)`(list[dict]) 와 동형 → `cited_versions` 타입 안전.
- ✅ **auth 토큰**: HMAC-SHA256 서명 + 30일 만료 + 상수시간 비교(`hmac.compare_digest`). `_verify_token` 안전.
- ✅ **connections**: 싱글턴/지연초기화/종료 정리 구조 정상. `_registry` 락 안전.

---

## 6. 우선순위 권고 (다음 액션)

| 순위 | 항목 | 이유 |
|---|---|---|
| 1 | P0-2 `/rag/*` 인증 | 보안 노출, 1시간 내 조치 가능 |
| 2 | P0-3 타임아웃 상향 | 기능적 결함(답변 품질) |
| 3 | P1-2 Qdrant 재시도/예외 | 신뢰성, 조용한 빈 검색 |
| 4 | P0-1 `/ready` 분리 | 운영 헬스 |
| 5 | P1-1 토큰 정산 0-case | 할당량 활성 시 과금(잠재) |
| 6 | P2-3 CoT 유출 가드 | 보안 |
| 7 | P2-1/2/4/5/6/7 | 동시성/일관성/성능 정리 |

> 구현 지시 시 각 항목을 독립 PR/커밋으로 분리하고, py_compile + 경로별 smoke 테스트로 회귀 확인 권장.
