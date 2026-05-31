# 🧹 핸드오프 ④ 중복·불필요 코드 정리 지시

> 대상 모델에게: 아래 항목을 순서대로 처리하라. 각 항목 [위치][문제][조치][검증].
> ⚠️ 삭제 전 반드시 grep으로 참조처 0개 확인 후 진행.

---

## 즉시 처리 (위험 낮음)

### C1. `requirements.txt` 누락 의존성 추가 — 필수 ⭐
- **문제**: `kiwipiepy`, `rank_bm25`가 로컬엔 설치됐지만 requirements.txt에 없음 → 서버 배포 시 ImportError.
- **조치**: requirements.txt에 추가:
  ```
  kiwipiepy==0.23.1
  rank-bm25==0.2.2
  ```
- **검증**: 클린 환경 `pip install -r requirements.txt` 후 `import kiwipiepy, rank_bm25`.

### C2. orphan `.pyc` 정리
- **문제**: `__pycache__`에 소스 없는 `pdf_vision_indexer.cpython-312.pyc` 존재 (삭제된 모듈 잔재).
- **조치**: `find backend -name "*.pyc" -delete` 또는 `__pycache__` 전체 삭제. `.gitignore`에 `__pycache__/` 확인.
- **검증**: 재실행 시 정상 import.

### C3. Python 버전 혼재 pyc (3.10/3.12/3.14)
- **문제**: `chat.cpython-310.pyc`, `*.cpython-314.pyc` 등 여러 버전 캐시 혼재 → 혼란.
- **조치**: 캐시 전체 삭제. venv Python 버전 단일화 확인(현재 3.12).

---

## 중복 기능 통합 (위험 중간 — 신중히)

### C4. 용어 추출 3중 중복 ⭐
- **위치**: `cleanup_pipeline.extract_terms()`, `cleanup_pipeline.extract_metadata()`, `glossary_service.extract_terms_from_text()`
- **문제**:
  - `extract_terms()`: 표시용 라벨 문자열 `"[성경구절] 요 3:16"` 반환
  - `extract_metadata()`: 검색용 깨끗한 리스트 반환 (INGEST가 사용)
  - `glossary_service.extract_terms_from_text()`: DB 저장용 (publish가 호출)
  - → 3개가 비슷한 정규식·신학용어 목록을 **각자 중복 보유**.
- **조치**: 공통 추출 로직(성경구절 정규식, 신학용어 화이트리스트)을 **하나의 모듈**(`term_extraction.py` 신규)로 통합. 3개 함수는 이 공통 코어를 호출하는 얇은 래퍼로.
- **검증**: 발행 시 scripture_refs/topic_tags + glossary DB 저장 모두 정상.

### C5. `cleanup_pipeline.run_cleanup()` / `CleanupResult` 死코드 ⚠️
- **위치**: `cleanup_pipeline.py:79 CleanupResult`, `run_cleanup()`
- **문제**: "하위 호환 유지용"이라 적혀있으나 실사용처는 `documents.py`의 `/cleanup` 엔드포인트(거의 안 쓰임)뿐. INGEST 도입으로 사실상 死코드.
- **조치**: `/cleanup` 엔드포인트가 정말 필요한지 확인 → 불필요하면 엔드포인트+run_cleanup+CleanupResult 삭제. extract_terms만 남김.
- **검증**: admin UI에서 cleanup 호출하는 곳 없는지 grep.

### C6. 청킹 경로 이원화 ⚠️
- **위치**: `publish_service`(INGEST 경유) vs `source_service.py:119`(직접 chunk_text) vs `document_indexer.py`(독립 청킹)
- **문제**: 청킹이 3곳에서 제각각 호출. INGEST 파이프라인이 표준인데 source_service/document_indexer는 옛 경로.
- **조치**: source_service의 청킹이 실제 인덱싱에 쓰이는지 확인. 미사용이면 제거. 표준은 publish_service→ingest_pipeline 하나로.
- **검증**: 업로드→발행 흐름에서 INGEST만 타는지.

### C7. `document_indexer.py` — MVP 잔재 ⚠️
- **위치**: `document_indexer.py` (index_documents_folder, index_text_file)
- **사용처**: `api/eval.py:123`, `scripts/ingest_documents.py` (둘 다 개발/평가용)
- **문제**: DB publish 없이 폴더를 직접 Qdrant에 때려넣는 MVP 경로. 정식 경로(publish_service)와 **메타데이터·청킹 정책이 불일치** → 같은 컬렉션에 품질 다른 청크 혼입 위험.
- **조치**: eval/스크립트를 정식 publish 경로로 통일하거나, document_indexer를 "eval 전용"으로 명확히 격리(주석+별도 컬렉션). 프로덕션 컬렉션엔 절대 안 쓰도록.
- **검증**: 프로덕션 검색이 publish 경로 청크만 보는지.

---

## 분류기/LLM 호출 정리 (위험 중간)

### C8. 분류기 다중 LLM 호출
- **위치**: `classifier.classify_input`(4차원), `llm/router.classify_user_signal`(감정/여정), `salvation_detector.detect_salvation_signal`(구원신호)
- **문제**: 한 요청에 사용자 발화를 **3번 따로** LLM 분류 → 비용·지연. (이미 일부 백그라운드/flag off 했으나 여전히 분산)
- **조치**: 가능하면 **1회 LLM 호출로 통합 분류**(4차원+감정+구원신호를 한 JSON으로). 프롬프트 통합.
- **검증**: 분류 정확도 유지하며 LLM 호출 1회로 감소.

### C9. chat.py `_route_embedder` / locals() 흔적 점검
- **위치**: `chat.py`, `retriever.py`
- **문제**: V2 작업 중 `dense_query=locals().get(...)` 같은 임시 코드가 남았을 수 있음(이미 정리했으나 재확인).
- **조치**: retriever.retrieve의 dense_query/sparse_query 파라미터가 정식 시그니처로 들어갔는지 확인. locals() 잔재 없는지.
- **검증**: 문법+동작 테스트.

---

## 임시조치 승격 (위험 낮음)

### C10. "N2 drift 임시 완화" 정식화
- **위치**: `publish_service.py:161,174`
- **문제**: DB-Qdrant 정합성이 "임시 완화" 상태로 방치.
- **조치**: 핸드오프②-D1 참조. 발행 후 정합성 검증 추가.

### C11. admin 페이지 번호 불연속
- **위치**: `admin/pages/` — 8,11,12,13,16,17,18번 결번(삭제됨)
- **문제**: 페이지 번호 8→9, 10→14 등 점프. 기능상 문제 없으나 혼란.
- **조치**: 페이지 번호 재정렬(1~N 연속). 또는 그대로 두되 문서화.
- **검증**: Streamlit 사이드바 순서 정상.

---

## 처리 순서 권장
1. C1(필수), C2, C3 — 즉시, 위험 0
2. C9, C10, C11 — 빠른 정리
3. C5, C7 — 死코드 확인 후 삭제
4. C4, C6, C8 — 중복 통합 (신중, 테스트 동반)

## 공통 원칙
- 삭제 전 `grep -rn "함수명\|클래스명" backend/ admin/ scripts/`로 참조 0 확인.
- 각 변경 후 `python -c "import backend.app.main"` 통과 확인.
- 변경 내역 CHANGELOG.md 기록.
