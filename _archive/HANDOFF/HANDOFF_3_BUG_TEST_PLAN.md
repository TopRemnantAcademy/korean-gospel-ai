# 🐞 핸드오프 ③ 버그 테스트 계획 (35개 방법)

> 대상 모델에게: 아래 35개 테스트를 작성·실행하라. 각 항목은 [무엇을] [어떻게] [기대결과] [발견시 조치].
> 우선 `tests/` 디렉토리에 pytest로 구성. 서버 필요한 건 표시함.

---

## 1군 — 청킹 엔진 (chunker.py)

1. **빈 입력**: `chunk_text("")` → `[]` 반환, 예외 없음.
2. **공백만**: `chunk_text("   \n\n  ")` → `[]`.
3. **초장문 단일문장**: 2000자 한 문장 → max_tokens 초과분 강제분할, 모든 청크 ≤ 512토큰.
4. **토큰 경계**: 모든 청크 `token_estimate ≤ ingest_chunk_max_tokens` 검증.
5. **부스러기 병합**: min_tokens 미만 청크가 인접에 병합됐는지 (작은 문장 다수 입력).
6. **헤딩 경계**: `## 제목` 포함 마크다운 → 각 청크 `section_title` 채워짐.
7. **문장 절단 금지**: 각 청크가 문장부호로 끝나는 비율 측정 (overlap 제외).
8. **하위호환 인자**: `chunk_text(text, chunk_size=500)` 옛 인자로도 동작.
9. **이모지/특수문자**: 깨지거나 토큰추정 폭주 안 하는지.
10. **한자·영문 혼용**: 다국어 텍스트 청킹 안정성.

## 2군 — Sparse BM25 (sparse_index.py)

11. **정확어 검색**: "렘넌트" 포함 청크가 "렘넌트" 질의에 1위.
12. **성경장절 토큰**: `tokenize("요 3:16")` → `요3:16` 통째 토큰 존재.
13. **빈 인덱스 검색**: 인덱스 0개일 때 `search()` → `[]` (예외 없음).
14. **중복 id 교체**: 같은 chunk_id 재add 시 중복 안 쌓임.
15. **remove_by**: predicate로 특정 doc_id 청크만 제거되는지.
16. **재구축 일관성**: add_batch 후 size() 정확, dirty 플래그 갱신.
17. **Kiwi 실패 fallback**: Kiwi 강제 예외 시 공백분리로 graceful.
18. **대량 성능**: 1만 청크 인덱싱+검색 시간 측정 (< 1s 목표).

## 3군 — 품질 게이트 (quality_gate.py)

19. **빈 청크 제거**: 빈 text 청크 입력 → empty_removed 카운트.
20. **중복 제거**: 동일 내용 3개 → 1개만 통과, duplicate_removed=2.
21. **신학왜곡 차단**: "회개 없이 구원" 류 → blocked=True.
22. **정상 통과**: 정상 설교 청크 → blocked=False, 전부 통과.
23. **과대 청크 경고**: max 초과 청크 → oversize 카운트(차단 아님).
24. **HARD_BLOCK 패턴**: safety_service 패턴(번영신학 등) 검출.

## 4군 — INGEST 파이프라인 (ingest_pipeline.py)

25. **flag off 전부**: 모든 ingest flag false → 청킹만 수행, LLM 호출 0.
26. **정규화 단독**: normalize만 켜고 "삼장 십육절"→"3:16" 변환 확인.
27. **품질차단 전파**: 신학왜곡 문서 → IngestResult.blocked=True, embed_texts 빈.
28. **메타 추출**: scripture_refs/topic_tags 채워지는지.
29. **LLM 단계 실패격리**: 구조화 LLM 강제실패 → 원문유지+warning, 파이프라인 계속.

## 5군 — 검색/답변 통합 (서버 필요)

30. **하이브리드 융합**: debug=true로 dense+sparse 후보 모두 반영되는지.
31. **빈 질의 422**: `{"query":""}` → 422 (이미 검증 있음, 회귀확인).
32. **출처 라벨**: 답변 sources에 section_title/context_prefix 존재.
33. **환각 탐지**(A3 구현 후): 근거에 없는 성경구절 답변 → 플래그.
34. **속도 회귀**: 동일질의 P50 응답시간 측정, 기준치 비교.
35. **토큰쿼터**: TOKEN_QUOTA_ENABLED=true에서 한도 초과 시 429.

## 6군 — 회귀·통합

36. **eval_retrieval 회귀**: recall@5 ≥ 기준(95%) 유지.
37. **발행 멱등성**: 같은 버전 2번 발행 → 청크 중복 안 됨(deterministic id).
38. **재시작 후 BM25**: 서버 재시작 → BM25 인덱스 자동 재구축됨.

---

## 실행 방법 (다른 모델 지시)
```bash
# 1) tests/ 디렉토리에 pytest 파일 작성 (1군~4군은 서버 불필요)
# 2) 서버 불필요 테스트 먼저:
venv/Scripts/python -m pytest tests/ -v -k "not server"
# 3) 서버 필요 테스트는 서버 띄우고:
venv/Scripts/python -m pytest tests/ -v -k "server"
```

## 발견 버그 처리 원칙
- 각 실패는 `docs/BUG_LOG.md`에 [재현법][원인][수정][검증] 기록.
- 수정 후 해당 테스트가 green 되는지 + 인접 테스트 회귀 없는지 확인.
- LLM 의존 테스트는 mock 우선 (비용/속도), 통합테스트만 실LLM.
