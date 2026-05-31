# 🚀 검색·답변 엔진 V2 — "한국 1등" 종합 설계

> 목표: 이 기능만으로 기존 한국 종교 AI를 압도한다.
> 승부처: **① 신학적 정확성+근거  ② 상담 깊이+공감  ③ 속도+정확도 동시** (셋 다)
> 인프라 결정: **embedded Qdrant 유지 + 자체 한국어 BM25 하이브리드** (Docker 불필요, 클라우드 승격 경로 보존)

---

## 0. 현재 엔진의 치명적 약점 (진단)

| 약점 | 현재 | V2 해결 |
|------|------|---------|
| Sparse 죽음 | embedded=dense only | **자체 Kiwi+BM25 하이브리드** |
| Reranker 꺼짐 | RERANKER=none | **경량 cross-encoder 선택적 + RRF 개선** |
| 질의이해 0 | 질문 그대로 임베딩 | **Query Understanding (HyDE+확장)** |
| 근거검증 0 | LLM 자유생성 | **Grounding Verifier (인용강제+환각차단)** |
| 단일임베더 | KURE만 | (유지, 단 BM25가 보완) |
| 속도 6.7s | dense+병렬 | **2-tier 캐시 + 조기종료로 1~2s** |

---

## 1. V2 검색 파이프라인 (Retrieval)

```
질의
 │
 ▼ [A] Query Understanding (LLM, 캐시됨)
 │     · 감정/의도 분류 (이미 classifier 있음)
 │     · HyDE: 가상 모범답변 생성 → 그것을 임베딩 (dense recall↑)
 │     · 키워드 추출: 정확어·성경장절·고유명사 → BM25 쿼리
 │     · 다국어 질의는 그대로
 ▼ [B] 하이브리드 검색 (병렬)
 │     ├─ Dense: KURE 임베딩 (HyDE 답변 + 원질의 평균)
 │     └─ Sparse: Kiwi 토큰화 → BM25 (정확어·장절·고유명사)
 ▼ [C] RRF 융합 (가중치 튜닝)
 ▼ [D] Reranker (선택적, 후보 적을 때만)
 │     · cross-encoder 재순위 (속도 위해 top-10만)
 ▼ [E] Profile Boost (기존 D-C16 matrix)
 ▼ [F] Diversity (MMR) — 같은 설교 청크 쏠림 방지
 → top-N 청크
```

### [A] Query Understanding `query_service.py` (신규)
- **HyDE (Hypothetical Document Embeddings)**: "힘들어요" → LLM이 *이 질문에 답할 법한 설교 문장*을 가상 생성 → 그 문장을 임베딩.
  대명사·구어체 질의의 dense recall을 극적으로 높임. (LLM 1회, 캐시)
- **키워드 추출**: Kiwi로 명사·고유명사·성경장절 추출 → BM25 쿼리로.
- **질의 캐시**: 같은 질문은 LLM 재호출 없이 재사용 (LRU + TTL).

### [B] Sparse 부활 `sparse_index.py` (신규) — ⭐ 핵심
- embedded Qdrant가 BM42를 못 쓰므로, **앱 레벨 BM25 인덱스**를 메모리에 유지.
- Kiwi 형태소 토큰화 → rank_bm25(BM25Okapi).
- publish 시 청크를 BM25 인덱스에 추가, 서버 시작 시 Qdrant에서 전체 로드해 재구축.
- dense 후보 + sparse 후보를 RRF로 융합 → "렘넌트", "요 3:16" 정확매칭 부활.

### [C] RRF + [F] MMR
- RRF 가중치: dense 0.6 / sparse 0.4 (튜닝 가능, eval로 검증).
- MMR(λ=0.7): 상위 결과의 의미 다양성 확보 → 한 설교만 5개 나오는 쏠림 방지.

---

## 2. V2 답변 파이프라인 (Generation) — ② 깊이 + ① 근거

```
검색결과(근거청크)
 ▼ [G] 근거 기반 프롬프트 (출처라벨 포함, 이미 구현)
 ▼ [H] LLM 답변 생성 (DeepSeek)
 ▼ [I] Grounding Verifier (신규) ⭐
 │     · 답변의 각 핵심주장이 근거청크에 있는가 검증
 │     · 근거 없는 주장 = 환각 → 재생성 or 제거
 │     · 성경 인용 정확성 검사 (장절이 실제 청크에 있나)
 ▼ [J] 출처 명시 답변
 │     "이 내용은 『통영다락방』 설교에 근거합니다" 자동 첨부
 ▼ [K] 안전망 (기존 safety_service)
```

### [I] Grounding Verifier `grounding_service.py` (신규) — ⭐ 신뢰의 핵심
- **환각 0% 목표**: LLM 답변을 문장 단위로 쪼개 → 각 문장이 근거청크에서 지지되는지 임베딩 유사도+키워드로 검증.
- 지지 안 되는 문장은 "근거 부족" 플래그 → soft 재생성.
- **성경 인용 검증**: 답변에 "요 3:16" 나오면 → 실제 근거청크에 그 구절이 있는지 확인. 없으면 경고.
- 종교 AI에서 *환각된 성경구절*은 치명적 — 이게 1등의 신뢰 차별화.

---

## 3. 속도 전략 (③ 1~2초)

| 기법 | 효과 |
|------|------|
| Query 캐시 (LRU+TTL) | 반복 질문 LLM 0회 |
| HyDE/Verifier 병렬화 | 직렬 대비 절반 |
| Reranker 조건부 (후보≤N 생략) | 평시 reranker 비용 0 |
| dense+sparse asyncio.gather | 동시 실행 |
| 임베딩 결과 캐시 | 동일 질의 재임베딩 0 |
| Grounding은 백그라운드 검증+조기응답 | 사용자 대기↓ |

목표: 캐시 히트 <1s, 미스 2~3s.

---

## 4. 구현 우선순위

| # | 작업 | 임팩트 | 의존 |
|---|------|--------|------|
| **V1** | sparse_index.py — Kiwi+BM25 하이브리드 부활 | ★★★★★ | — |
| **V2** | retriever.py — dense+sparse RRF 융합 통합 | ★★★★★ | V1 |
| **V3** | query_service.py — HyDE + 키워드추출 + 캐시 | ★★★★☆ | V2 |
| **V4** | grounding_service.py — 환각·인용 검증 | ★★★★★ | — |
| **V5** | MMR 다양성 + RRF 가중치 튜닝 | ★★★☆☆ | V2 |
| **V6** | 속도: 질의/임베딩 캐시 + 조건부 reranker | ★★★★☆ | V2,V3 |
| **V7** | eval 확장 + 전체 회귀검증 | ★★★★☆ | 전부 |

각 단계 `.env` flag로 on/off. LLM은 chat_with_fallback 경유 (DeepSeek 런타임).

---

## 5. 삭제·정리 대상
- `RERANKER=none` 강제 → 조건부 reranker로 대체 (속도 유지하며 정밀도 회복)
- dense-only fallback 경고 → sparse 부활로 불필요
- 단순 글자수 청크 잔재 (이미 V1 INGEST에서 토큰기반으로 교체됨)

---

## 6. "1등" 검증 기준 (eval_retrieval 확장)
- recall@5 ≥ 95% (현재 100%, 더 어려운 질문셋으로 재측정)
- **정확어 recall**: "렘넌트"/"요 3:16" 질의에서 정확매칭 ≥ 95%
- **환각율**: Grounding Verifier로 측정, < 2%
- **성경인용 정확도**: 100% (없는 구절 인용 0건)
- 속도: P50 < 2s
