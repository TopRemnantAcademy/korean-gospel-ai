# 🧭 핸드오프 ⓿ 마스터 — 현재 상태 & 착수 순서

> 다른 모델에게: **이 문서를 먼저 읽어라.** 나머지 HANDOFF 1~4와 설계서의 진입점이다.
> 작성자(Claude)는 이제 기획만 한다. 구현은 너의 몫.

---

## 1. 지금 코드베이스의 정확한 상태 (2026-05-31)

### ✅ 완료·동작 검증됨
- **INGEST 파이프라인** (Stage 1~5,7): `normalizer`/`restructurer`/`contextualizer`/`quality_gate`/`ingest_pipeline`/`chunker`(재작성). publish_service 연결. recall@5=100%.
- **인용 라벨**: chat.py `_labeled_contexts()` → 답변에 출처 표시.
- **속도 최적화**: dense 병렬화, reranker=none, 모델 워밍업. 웜 ~7s.

### ⚠️ 작성됨, 검증 부분적 (V2 — 유지하기로 결정됨)
- **`sparse_index.py`** (신규): Kiwi+BM25 자체 sparse. **단위동작 검증됨**(렘넌트/동행 테스트 통과). 단 실서버 통합·멀티워커 미검증.
- **`retriever.py`** 수정: dense+sparse RRF 융합에 `_bm25_sparse()` fallback 추가, `dense_query`/`sparse_query` 파라미터 추가(HyDE 대비).
- **`publish_service.py`** 수정: 발행 시 BM25 인덱스에도 청크 반영.
- **`main.py`** 수정: 서버 시작 시 BM25 인덱스 Qdrant scroll로 재구축.
- **`requirements.txt`**: kiwipiepy/rank-bm25 추가됨(방금).

→ **이 V2 코드는 유지한다.** 너의 첫 작업은 이걸 "완성·검증"하는 것(아래 순서 P0).

### ❌ 미구현 (기획만 됨)
- Query Understanding/HyDE (`query_service.py`)
- Grounding Verifier (`grounding_service.py`)
- MMR 다양성, 조건부 reranker
- INGEST Stage 6 (요약·Q&A)
- 성경 원문 DB

---

## 2. ⭐ 착수 순서 (Claude가 정한 최적 순서 — 의존성·리스크 기반)

> 원칙: ①깨진 것부터 ②검증 토대 ③신뢰 ④품질 ⑤확장. 각 단계는 다음의 전제가 된다.

### P0. 토대 안정화 (먼저, 위험 0, 반나절)
1. **HANDOFF_4 C1~C3**: requirements 검증(완료), pyc 정리, 버전 단일화.
2. **HANDOFF_3 1~4군 테스트 작성**: chunker/sparse/quality_gate/ingest 단위테스트.
   - 이걸 먼저 하는 이유: **이후 모든 변경의 안전망.** 회귀를 즉시 잡는다.
3. **V2 sparse 통합 검증**: 서버 띄우고 debug=true로 dense+sparse 후보 둘 다 반영되는지. recall 재측정.

### P1. 신뢰 — 종교 AI의 생명 (최우선 기능)
4. **HANDOFF_2 A3: Grounding Verifier** (`grounding_service.py`).
   - 환각·없는 성경구절 차단. 이게 경쟁사 대비 1등 차별화의 핵심.
   - 테스트 33번(환각 탐지)으로 검증.

### P2. 검색 품질 (체감 큰 향상)
5. **HANDOFF_2 A2: Query Understanding/HyDE** (`query_service.py`).
   - retriever가 이미 `dense_query`/`sparse_query` 받을 준비됨 → chat.py에서 연결만.
6. **A4 조건부 reranker + A5 MMR**: retriever 후처리.

### P3. 중복 정리 (P0 테스트가 깔린 뒤 안전하게)
7. **HANDOFF_4 C4~C8**: 용어추출 통합, document_indexer 격리, 死코드 제거, 분류기 1회 통합.
   - **반드시 P0 테스트 green 상태에서** 진행 → 회귀 즉시 감지.

### P4. 콘텐츠 해자 (병렬 가능, 큰 작업)
8. **HANDOFF_2 B1: 콘텐츠 대량화** + **B2: 성경 원문 DB**.
9. **B3: INGEST Stage 6** (요약·Q&A 생성).

### P5. 운영·스케일 (서버 이전 시)
10. **HANDOFF_1 전체**: 서버 이전 (Qdrant 서버/PG/시크릿/멀티워커).
11. **HANDOFF_2 D1~D4**: drift 정합성, 관측성, 위기대응.

---

## 3. 문서 지도

| 문서 | 용도 |
|------|------|
| `HANDOFF_0_MASTER.md` | **이 문서** — 진입점, 상태, 순서 |
| `HANDOFF_1_SERVER_MIGRATION.md` | 서버 이전 (P5) |
| `HANDOFF_2_GAP_ANALYSIS.md` | 부족분석 (P1,P2,P4의 근거) |
| `HANDOFF_3_BUG_TEST_PLAN.md` | 38개 테스트 (P0) |
| `HANDOFF_4_CLEANUP.md` | 중복·死코드 정리 (P3) |
| `HANDOFF_5_DELETE.md` | 불필요 파일·코드·기능 삭제 명령서 (P0/P3) |
| `HANDOFF_6_ADDICTION_RECOVERY.md` | 중독자 회복 지원 기능 기획 (Crisis Surf·재발복귀·streak) |
| `ENGINE_V2_DESIGN.md` | 검색·답변 엔진 V2 상세설계 |
| `INGEST_PIPELINE_DESIGN.md` | 문서 재편집·청킹 설계 (구현됨) |

---

## 4. 작업 공통 규칙 (다른 모델 필수 준수)
- **LLM은 항상 `chat_with_fallback()` 경유** — 직접 SDK 호출 금지. `.env: LLM_PROVIDER`로 교체됨.
- **변경 전 `grep`로 참조처 확인**, 변경 후 `python -c "import backend.app.main"` 통과 확인.
- **각 기능은 `.env` feature flag로 on/off** 가능하게 (점진 배포·롤백).
- **CHANGELOG.md에 변경 기록.**
- **삭제는 신중히** — 死코드라도 grep 0 확인 후.
- 사용자 응답 규칙: 이름에 "님", 문장은 "~요"로 끝냄 (이 프로젝트 사용자 선호).
