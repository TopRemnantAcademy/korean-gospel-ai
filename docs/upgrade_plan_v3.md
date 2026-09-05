# 업그레이드 기획안 v3 — "기능 이름만 있는" 시스템을 실제로 만들기

> 근거: `설교 전사 Markdown 정제 + 청크 기반 RAG 시스템 설계서`(Perplexity)
> 작성: 2026-07-16 / 태도: 냉정·과감 (기존 스택 일부 폐기 포함)
> 핵심 전제: **측정 없이 튜닝하지 않는다. 상류(전사 정제)를 먼저 고친다. 스택 이중화를 끝낸다.**

---

## 0. 냉정한 현주소 진단 (코드로 확인한 사실)

현재 시스템은 "설계서에 나온 기능 이름"은 상당수 갖췄지만, **실제로 동작·연결·측정되는지**는 별개다. 확인 결과:

| 항목 | 설계서 요구 | 현재 실체 | 판정 |
|---|---|---|---|
| 평가 루프 | 골드 쿼리셋 + Recall/MRR/nDCG 정기 측정 | `evaluation.py`(측정 코드)만 존재, **골드셋 데이터 0개** → 아무것도 안 돌아감 | 🔴 치명 |
| 상류 정제 | ASR 띄어쓰기/오타 복원 | `normalizer.py`는 규칙만, **Kiwi 미적용** → 띄어쓰기 파괴 그대로 | 🔴 치명 |
| RAG 스택 | 단일 일관 파이프라인 | `rag_engine.py`(구·챗경로 사용) + `enhanced_rag/`(신·병렬) **2개 coexist** | 🔴 혼선 |
| 구조 파싱 | section_type 분류(서론/본문/예화/적용/기도) | `restructurer.py`에 section_type **자체가 없음**(검색 0건) | 🟠 누락 |
| sentence-window | 문장단위 색인+윈도우 교체 | **완전 누락**(검색 0건) | 🟠 누락 |
| hybrid 검색 | BM25+dense+RRF+rerank | `enhanced_rag`에 존재(좋음) | 🟢 양호 |
| contextual retrieval | 2~4문장 맥락 프리픽스 | `contextualizer.py` 있으나 **40자 1문장 + heading 의존(취약)** | 🟡 약함 |
| 성경구절 추출/필터 | ref 파서→메타/쿼리정규화/필터 | `extract_metadata`가 refs 추출만, **쿼리정규화·필터 연결 약함** | 🟡 약함 |
| human review queue | low-confidence→검토큐 | **없음** | 🟠 누락 |

**결론: 가장 큰 문제는 "고장 난 부품"이 아니라 "측정이 없어 고장을 모르는 것"과 "상류 정제가 안 돼 하류가 다 오염된 것".** 고급 기능(BM25/rerank/contextual)을 아무리 붙여도 입력이 `했습니 다`면 의미 없다.

---

## 1. 업그레이드 철학 (뒤집을 것)

1. **측정 선행**: 코드 한 줄 바꾸기 전에 골드셋으로 베이스라인 수치를 낸다. 그 수치가 모든 의사결정의 기준.
2. **상류 절대 우선**: 전사 정제(Kiwi) 하나가 BM25·dense·청킹·맥락을 동시에 살린다. 하류 꾸미기보다 상류가 10배 효과.
3. **스택 단일화**: 두 RAG를 하나로. 구형(`rag_engine.py`)은 폐기/래핑, 신형(`enhanced_rag`)을 단일 소스로 승격.
4. **fail-open 유지하되 측정**: 기능은 꺼져도 시스템은 안 멈추되, 꺼진 구간은 지표로 드러나게.

---

## 2. 우선순위별 실행 계획

### P0 — 측정 인프라 구축 (가장 과감·최우선)
**왜**: 지금은 맹목 튜닝 중. 베이스라인 없이 바꾸면 "나아졌다"를 증명 못 함.
- `data/eval_sets/`에 실제 설교 5~10편 골드셋 구축 (문서당 30~50 질의):
  - 주제/구절/적용/예화/신학개념/화자문맥 6유형 (설계서 §13.1)
  - `expected_chunk_ids` 라벨링
- `enhanced_rag/evaluation.py`의 `evaluate(qa_pairs)`를 CLI/스크립트로 실행:
  - `scripts/run_eval.py` 신설 → Recall@5/10, MRR, nDCG, faithfulness 출력(markdown 리포트)
- **베이스라인 수치 문서화** → 이후 모든 변경의 비교 기준.

### P1 — 상류 정제 고정 (최고 레버리지)
**왜**: 띄어쓰기 파괴가 BM25/dense/청킹/맥락을 모두 오염. Kiwi는 이미 실측 검증 완료.
- `services/spacing.py` 신설: Kiwi 싱글턴(`space()`+`split_into_sents()`), `requirements.txt`에 `kiwipiepy` 추가.
- `normalizer.normalize_text` **최선단**에 Kiwi `space()` 호출 (성경표기 정규화는 Kiwi 이전 실행 순서 고정).
- 잔여 오염(실제 전사 오류)만 `llm/fallback.py::chat_with_fallback`로 선택적·캐시 교정.
- `chunker.py` 문장분리 정규식(`:89` 부근) → Kiwi `split_into_sents()`로 교체.
- **P0 골드셋으로 before/after Recall@k 비교** → 효과 수치화.

### P2 — RAG 스택 단일화 (기존 뒤집기)
**왜**: 구형(`rag_engine.py`, 챗경로 사용)과 신형(`enhanced_rag`)이 둘 다 살아있어 혼선+중복 유지보수.
- 결정: **`enhanced_rag`를 단일 소스로 승격** (hybrid+rerank+contextual+evaluation 이미 보유).
- `api/chat_pipeline.py`(`:8,11` `rag_engine` import) → `enhanced_rag.RAGPipeline`로 전환.
- `rag_engine.py` + 구형 `chunker.py` 래퍼로 격리 후 점진 삭제 (동작 동일성 테스트 후).
- 중복 임베더·스토어 설정 정리.

### P3 — sentence-window retrieval 추가
**왜**: 설계서 §20, 짧은 질의("은혜 말한 데") 미스의 방어. 현재 완전 누락.
- `enhanced_rag`에 sentence-node 색인 추가 (문장단위 인덱스 + `window_text`).
- 검색 시 문장단위 후보 → 윈도우 교체 → 동일 parent chunk 병합.
- P0 골드셋의 "짧은 질의" 부분집합으로 효과 검증.

### P4 — 구조 파싱 + 컨텍스트 강화 강화
**왜**: contextual 프리픽스가 heading에 의존해 취약. section_type이 없으면 "적용만 찾아줘" 불가.
- `restructurer.py`에 **section_type 분류** 추가(intro/main_text/illustration/application/prayer/reading/qna) — 규칙+LLM 혼합.
- 성경구절 블록 별도 태깅 (`extract_metadata` 확장 → `bible_refs` 블록 메타).
- `contextualizer` 프리픽스를 **2~4문장**으로 강화(위치·역할·주제·구절 포함), section_type 활용.
- 성경구절 추출기를 **쿼리 정규화 + metadata 필터**에 연결 (`창 1:1`→`창세기 1:1` 표준화 후 필터).

### P5 — human review queue + 관측성
**왜**: 교정 신뢰도 낮은 구간은 사람이 봐야 함. 실패는 보여야 고침.
- low-confidence 교정/`[REVIEW]` 태그 → 관리자 검토큐 (admin 페이지 확장).
- 관측: BM25-only vs dense-only 잡힌 질의 분리 로깅, reranker 승패, 자주 실패하는 Bible ref 표기.
- 실패 질의 로그 → P0 골드셋 자동 보강(active learning).

---

## 3. KEEP / KILL / BUILD

**KEEP (유지·승격)**
- `enhanced_rag/` 전체 (hybrid BM25+dense+RRF, reranker, evaluation 코드, bilingual 골격)
- `llm/fallback.py` (멀티프로바이더 폴백 — Tier2 교정 재사용)
- `quality_gate.py`, `cleanup_pipeline.py` (메타추출)

**KILL (폐기/래핑)**
- `rag_engine.py` (구형, 챗경로에서 분리 후 삭제)
- `services/chunker.py` (enhanced_rag/chunking.py가 대체, 중복)
- rule-based 어절빈도 사전 (Kiwi로 대체, v2 설계서 정정 반영)

**BUILD (신규)**
- `services/spacing.py` (Kiwi 싱글턴)
- `data/eval_sets/` + `scripts/run_eval.py` (골드셋·측정)
- sentence-window 노드 색인/검색
- `restructurer` section_type 분류 + 성경 블록 태깅
- human review queue + 관측 대시보드

---

## 4. 실행 순서 (bold but measured)

```
[1] P0 골드셋 + run_eval → 베이스라인 수치 확보   (측정 없으면 다음 단계 금지)
[2] P1 Kiwi 정제 → P0로 before/after 비교         (상류가 most leverage)
[3] P2 enhanced_rag 단일화 → 동작 동일성 검증
[4] P3 sentence-window → 짧은 질의 지표 개선 확인
[5] P4 구조파싱/컨텍스트/성경필터 → 적용·구절 질의 지표 개선
[6] P5 review queue + 관측 → 운영 루프 폐쇄
```

각 단계는 **P0 수치와 대비**해 진행. 수치가 안 오르면 그 단계는 되돌림.

---

## 5. 위험·가정
- `enhanced_rag`의 **bilingual(중국어 primary)** 레이어가 실제 제품에 필요한지 확인 필요. 불필요하면 복잡도이므로 단순화.
- Kiwi `space()`가 성경 인용(`삼 장 십 육 절`)을 분해하는 역효과 → 정규화 순서로 상쇄(검증 필요).
- 골드셋 구축에 실제 설교 원문 접근 권한/시간 필요. 불가 시 소규모(3편)로 먼저.
