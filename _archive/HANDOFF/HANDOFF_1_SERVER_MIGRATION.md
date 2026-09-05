# 📦 핸드오프 ① 서버 이전 기획 (로컬 → 프로덕션)

> 대상 모델에게: 이 문서는 "지금 로컬에서 돌아가는 것을 서버로 옮길 때 무엇을 바꿔야 하는가"의 완전한 체크리스트다.
> **핵심 원칙: 코드는 그대로, 환경변수(.env)와 인프라만 교체.** 그렇게 설계되어 있다.

---

## 0. 결론 먼저: 로컬 그대로 써도 되는가?

**대부분 그대로 된다.** 단, 4가지는 반드시 교체해야 한다:

| 항목 | 로컬 (현재) | 서버 (프로덕션) | 교체 방법 |
|------|------------|----------------|----------|
| **Vector DB** | embedded Qdrant (`local:./.qdrant_local`) | Qdrant 서버 (Docker/Cloud) | `.env: QDRANT_URL` 한 줄 |
| **관계형 DB** | SQLite (`.gospel.db`) | PostgreSQL | `.env: DATABASE_URL` 한 줄 |
| **Sparse 검색** | 자체 BM25 (메모리) | Qdrant 서버 BM42 OR 자체 BM25 유지 | 코드 자동 분기 (아래 §3) |
| **시크릿** | `.env` 평문 | 환경변수/시크릿매니저 | 배포 플랫폼 설정 |

→ 나머지(LLM, 임베더, 파이프라인, 검색 로직)는 **코드 한 줄 안 바꿔도** 작동한다.

---

## 1. 왜 "그대로" 되는가 — 이미 추상화돼 있음

이 프로젝트는 처음부터 환경 교체를 염두에 두고 설계됨:

- **LLM**: `chat_with_fallback()` 추상 계층 → `.env: LLM_PROVIDER`로 DeepSeek/Gemini/OpenAI 교체
- **임베더**: `get_embedder()` 팩토리 → `.env: EMBEDDER`로 교체
- **Vector DB**: `vector_store._make_client()`가 `QDRANT_URL` 접두어로 자동 분기:
  - `local:` → embedded
  - `memory:` → 인메모리(테스트)
  - `http(s)://` → 서버 모드 (sparse BM42 자동 활성화)
- **관계형 DB**: `db._resolve_db_url()`가 `DATABASE_URL` 환경변수 우선, 없으면 SQLite

→ **이전 작업의 90%는 `.env` 파일 교체다.**

---

## 2. 서버 이전 단계별 체크리스트 (다른 모델이 실행)

### Step 1 — Qdrant 서버 전환
```bash
# Docker로 Qdrant 서버 구동 (또는 Qdrant Cloud 사용)
docker run -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```
```env
# .env 변경
QDRANT_URL=http://localhost:6333        # 또는 https://xxx.qdrant.tech
QDRANT_API_KEY=<클라우드면 키>
QDRANT_SPARSE_ENABLED=true              # 서버모드는 BM42 네이티브 sparse 지원
```
- **재인덱싱 필수**: embedded → 서버는 데이터가 자동 이전 안 됨. 모든 published 버전을 재발행하거나 마이그레이션 스크립트 작성(아래 §4).

### Step 2 — PostgreSQL 전환
```env
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/gospel
```
- `db.py`는 이미 `DATABASE_URL` 우선 → SQLite 전용 PRAGMA(WAL/foreign_keys)는 `if sqlite` 가드 있음, 그대로 OK.
- **Alembic 마이그레이션 실행**: `alembic upgrade head` (스키마 생성).
- ⚠️ SQLite → PG 데이터 이전: `scripts/migrate_sqlite_to_postgres.py` 이미 존재 — 검증 후 사용.
- ⚠️ JSON 컬럼: SQLite는 JSON을 TEXT로 저장, PG는 native JSONB. ORM이 `JSON` 타입이라 호환되지만 **인덱스·쿼리 성능 재확인** 필요.

### Step 3 — 시크릿 관리
- `.env` 평문 키(`DEEPSEEK_API_KEY`, `GOOGLE_API_KEY`, `ADMIN_API_KEY` 등)를 배포 플랫폼 환경변수/시크릿 매니저로 이동.
- **`ADMIN_API_KEY`는 반드시 강한 값으로 변경** (현재 `local-admin-key`). main.py가 `change-me`면 경고 띄움 — 프로덕션 값 강제.
- `.env`는 `.gitignore`에 있는지 확인.

### Step 4 — 서버 구동 방식
```bash
# 로컬: uvicorn 단일 프로세스
# 서버: gunicorn + uvicorn worker (멀티프로세스)
gunicorn backend.app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000
```
- ⚠️ **자체 BM25 인덱스는 메모리 상주** → 멀티워커면 워커마다 인덱스 중복 로딩 + 발행 시 한 워커만 갱신되는 문제. **서버모드에선 Qdrant BM42로 전환**해 이 문제 회피(§3).

### Step 5 — CORS / 도메인
```env
CORS_ORIGINS=https://your-frontend.com
```

---

## 3. ⭐ Sparse 검색 — 로컬 BM25 vs 서버 BM42 자동 분기 설계

**현재 설계 (이미 반영됨):**
- `retriever._sync_search()`가 `store.search_sparse()` 먼저 시도(서버 BM42) → 비면 자체 BM25 fallback.
- 즉, **서버 전환 시 BM42가 자동으로 우선 사용**되고, 자체 BM25는 자동으로 비활성. 코드 수정 0.

**다른 모델이 해야 할 일:**
1. 서버 전환 후 `QDRANT_SPARSE_ENABLED=true` 확인.
2. 재인덱싱 시 BM42 sparse 벡터가 함께 저장되는지 검증 (`vector_store.upsert`의 `_to_sparse_batch` 경로).
3. 멀티워커 환경에서 자체 BM25를 **완전히 끄는 flag** 추가 권장:
   ```python
   # config.py 추가 제안
   self_bm25_enabled: bool = True   # 서버모드(BM42)면 false 권장
   ```
   `retriever._bm25_sparse()` 진입부에서 이 flag 체크.

---

## 4. 재인덱싱 마이그레이션 (embedded → 서버)

다른 모델이 작성할 스크립트 `scripts/reindex_all.py`:
```
1. DB에서 state=published 인 모든 DocumentVersion 조회
2. 각 버전마다 publish_service.publish_version() 재호출 (새 Qdrant에 인덱싱)
   - INGEST 파이프라인 전체 재실행되므로 최신 청킹/컨텍스트 적용됨 (보너스)
3. 진행률 로깅, 실패 건 별도 기록
```
- ⚠️ LLM 단계(구조화/컨텍스트) 켜져 있으면 문서당 ~5분 → **배치/야간 실행** 권장.
- 또는 `INGEST_RESTRUCTURE_ENABLED=false`로 빠르게 1차 인덱싱 후, 점진 고도화.

---

## 5. 미래 방향 설계 (서버에서 바로 켤 것들)

| 기능 | 로컬 | 서버에서 활성화 |
|------|------|----------------|
| Reranker | `none` (CPU 느림) | Cohere API (`RERANKER=cohere` + 키) 또는 GPU BGE |
| 멀티 임베더 | KURE 단일 | KURE + BGE-M3 (다국어) 동시 인덱싱 |
| LLM | DeepSeek | 트래픽 따라 Gemini/Claude 혼합 라우팅 |
| 캐시 | 인메모리 LRU | Redis (멀티워커 공유) |
| 모니터링 | 로그파일 | Langfuse(`LANGFUSE_ENABLED=true`) + Sentry |
| Rate limit | 인메모리 | Redis 기반 분산 |

**설계 포인트**: 위 전부 이미 `.env` flag 또는 팩토리로 추상화돼 있어 코드 변경 최소.
다른 모델은 "새 코드 작성"보다 "flag 켜고 인프라 연결 + 검증"에 집중하면 된다.

---

## 6. 서버 이전 직전 검증 체크리스트
- [ ] `.env.production` 작성 (로컬 .env와 분리)
- [ ] `requirements.txt`에 `kiwipiepy`, `rank_bm25` 추가됨 (현재 누락! §핸드오프④ 참조)
- [ ] Alembic `upgrade head` 성공
- [ ] 재인덱싱 후 `eval_retrieval.py` recall 측정 (로컬과 동등 이상)
- [ ] ADMIN_API_KEY 등 시크릿 프로덕션 값
- [ ] 멀티워커 시 BM25/캐시 공유 문제 해결(Redis 또는 BM42)
- [ ] HTTPS / CORS 도메인 확정
