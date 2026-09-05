# 청크/RAG 미세 오류 추가 점검 리포트 (성능·품질)

> 대상: `embedding/factory.py` · `sparse_index.py` · `reranker.py` · `search_optimizer.py` · `retriever.py` · `contextualizer.py` · `quality_gate.py` · `ingest_pipeline.py`
> 방식: 정적 분석 + 실제 실행 검증. "미세하지만 성능·품질에 누적 영향을 주는" 항목 위주.

---

## ✅ 이번 턴에 수정한 항목 (2건)

### 1. `_expansion_cache` 무한 성장 (메모리 누수) — 수정
**위치**: `search_optimizer.py`
**문제**: 쿼리 확장 캐시가 TTL(1시간) 만료를 기다릴 뿐 **상한이 없음**. 만료는 조회 시에만 lazy 제거되므로, 재조회되지 않는 쿼리 엔트리는 영구히 잔존 → 고트래픽에서 무한 성장.
**수정**: `_EXPANSION_CACHE_MAX=2000` + `_cache_expansion()` 헬퍼 도입 (초과 시 만료 항목 우선 제거, 그래도 많으면 LRU 제거).

### 2. 동기 `analyze_query`가 `search_expand_enabled` 게이트 무시 — 수정
**위치**: `search_optimizer.py` `analyze_query`(동기, `/retrieval` API가 사용)
**문제**: 비동기 버전(`analyze_query_async`)은 `settings.search_expand_enabled`(기본 False)를 확인하지만, 동기 버전은 확인 없이 LLM 확장을 호출 → 플래그로 끌 수 없던 경로. (단, FastAPI 루프가 돌면 `_expand_query_with_llm`의 "루프 실행 중 → skip" 가드로 실제로는 대부분 무시됨 — 잠재적 불일치)
**수정**: 동기 버전에도 동일 게이트 적용.

---

## 📋 보고만 한 항목 (권고, 안전성 검토 후 조치 권장)

### 3. 임베딩 락 직렬화 — 동시성 쓰루풋 병목
**위치**: `embedding/factory.py` `CachedEmbedder.embed_query/embed_documents`
**문제**: 두 메서드가 `self._lock`을 **모델 추론 내내 보유**. `CachedEmbedder`는 임베더명별 싱글턴이므로, 동시 채팅 요청의 KURE 임베딩이 **전부 직렬화**됨. 트래픽이 올라가면 검색 지연이 선형 증가.
**권고**: SentenceTransformer/KURE의 스레드 안전 여부를 확인한 뒤 (안전하면) 락을 캐시 접근으로만 한정하거나 세마포어(2~4)로 제한. 모델이 스레드 안전하지 않다면 현행 유지가 정답.

### 4. BM25 검색이 쿼리당 O(N) 전수 스캔
**위치**: `sparse_index.py` `BM25Index.search` → `rank_bm25.BM25Okapi.get_scores`
**문제**: `get_scores`는 코퍼스 전체 문서에 대해 점수 계산(O(N)). 청크 수가 수천~수만이 되면 sparse 검색이 지연 병목. (스레드로 격리되므로 이벤트루프는 안 막지만 응답은 느려짐)
**권고**: top-K 가지치기(WAND/BlockMax) 또는 코퍼스 분할, `rank_bm25` → `bminf` 등 최적화 검토.

### 5. BgeReranker 캐시가 사실상 무효
**위치**: `reranker.py` `BgeReranker.rerank` 캐시 키 `(query, tuple(docs))`
**문제**: `docs`(후보 청크 집합)가 쿼리마다 달라 캐시 히트가 거의 없음. 재순위 모델 추론을 매번 수행.
**권고**: 필요 시 (query, 단일 doc) 단위로 쪼개 캐시하거나, 캐시 제거(오버헤드만 줄임).

### 6. 한국어 쿼리 단어 수 오판 (`len(q.split())`)
**위치**: `search_optimizer.py` `analyze_query*`의 `word_count`
**문제**: 띄어쓰기가 거의 없는 한국어 쿼리("구원이란무엇인가")는 `split()` 결과 1개 → "짧은 쿼리" 판정과 쿼리 타입/가중치 분류가 부정확. (LLM 확장은 게이트로 꺼져 있어 직접 피해는 작으나, dense/sparse 가중치 결정에는 영향)
**권고**: 한국어 형태소 기반 단어 수(kiwi) 또는 글자 수 기준으로 보정.

### 7. 데드 코드 2건
- `search_optimizer.merge_duplicate_candidates` — 호출처 없음. 내부 점수 결합(`item.score*0.5 + rr_score*10*0.5`)이 차원 비일관(재사용 시 오류 유발 가능).
- `chunker.chunk_documents` — 호출처 없음.
**권고**: 제거 또는 주석 명시.

### 8. `chunk_text`의 `chunk_overlap` 무효 파라미터
**위치**: `chunker.py` `chunk_text(chunk_overlap=...)`
**문제**: 인자는 받지만 본문에서 전혀 읽지 않음. 호출자가 글자 오버랩을 의도하고 넘겨도 무시(실제는 `overlap_sentences`).
**권고**: `overlap_sentences`로 단일화하고, 넘어온 `chunk_overlap`은 경고 로그.

### 9. 맥락/제목/섹션이 LLM 프롬프트에 미주입
**위치**: `chat_pipeline.py` `build_prompts` + `contextualizer.py`/`publish_service.py`
**문제**: `context_prefix`(맥락강화)·`title`·`section_title`은 **임베딩에만** 반영되고, LLM이 실제 보는 컨텍스트는 `it.text`(원문 3문장 제한)뿐. 문서 제목/섹션이 답변 맥락에서 빠져 품질 저하 여지.
**권고**: `build_prompts`에서 `[제목/섹션] + 본문` 형태로 병기(토큰 예산 내).

### 10. reranker 기본값 `none`(NoOp) — 재순위 미동작
**위치**: `config.py` `reranker="none"` → `get_reranker`가 NoOp 반환
**문제**: cross-encoder 재순위(bge_m3)가 기본 비활성. 현재 검색 순위는 RRF 융합에만 의존. (메모리/속도 트레이드오프로 의도된 선택)
**권고**: 서버 여유 메모리 확보 후 `RERANKER=bge_m3` 활성화 검토(정밀도 향상).

### 11. `rrf_k=60` 하드코딩 vs config 불일치
**위치**: `retriever.py` `_search_one`의 `_rrf_fusion(..., k=60)` 하드코딩 ↔ `enhanced_rag/config.py` `rrf_k=60`
**권고**: 설정 단일화.

### 12. `ingest_pipeline` docstring 스테이지 순서 불일치
**위치**: `ingest_pipeline.py` 모듈 docstring(Stage 4 컨텍스트강화 → Stage 7 품질게이트) vs 실제 실행(Stage 7 품질게이트 → Stage 4 컨텍스트강화)
**문제**: 문서만 불일치(기능은 정상 — 품질게이트가 원문 청크 대상, 임베딩은 맥락강화본). **권고**: docstring 수정.

### 13. 토큰 추정 비율(0.55)의 혼합 문자 오차
**위치**: `chunker.py` `_TOKEN_RATIO=0.55`
**문제**: 한국어 기준 계수. 영문/숫자/성경장절("요 3:16")이 섞인 청크는 토큰 추정이 실제와 편차. (실 임베더 토크나이저가 로드되면 정확해짐 — `_get_tokenizer` 캐시)
**권고**: 토크나이저 로드 실패 환경에서도 영문/숫자 구간은 별도 계수로 보정.

### 14. 맥락강화 `embed_text`가 임베더 한도 초과 가능
**위치**: `contextualizer.py` `embed_text = context_prefix + "\n\n" + c.text`
**문제**: `c.text`가 최대 512토큰(초장문 강제분할 직후)일 때 맥락이 더해지면 512 초과 → KURE가 truncate(조용히 손실).
**권고**: `embed_text` 토큰 상한을 `max_tokens`와 동일하게 클램프.

---

## 검증
- 수정 2건(`search_optimizer.py`) `py_compile` 통과, `pytest tests/test_main.py` 통과, 전체 모듈 import 정상.
- `analyze_query('구원이란 무엇인가')` 게이트 적용 확인 (확장 미호출, 캐시 미증가).
