# 데이터 품질 엔진 전면 업그레이드 설계 (v2 — 확정판)

> 공통 근본 원인: **ASR 띄어쓰기 파괴**가 모든 하류(문장분리→청킹→임베딩)를 오염시킨다.
> 상류를 고치면 하류 품질이 덩달아 회복한다.

## ★ 확정된 해결 엔진 (2-Tier, 실측 검증 완료)
이전 v2의 "rule-based 어절빈도 사전"은 **사전 미등록어를 못 고치고 문맥을 못 봐서 부족**. 대신 아래 2단 엔진으로 확정.

**Tier 1 — Kiwi 형태소 복원 (결정적·오프라인·무료·고속)**
- 패키지명 정정: `kiwipiepie`(오타, 404) ✗ → **`kiwipiepy` ✓ 설치 성공** (cp312 win64 pre-built wheel, C++ 백엔드).
- `Kiwi().space()` = 띄어쓰기 복원, `Kiwi().split_into_sents()` = 정확한 문장분리. **둘 다 형태소 기반이라 사전 불필요**.
- 실측(실제 ASR 오염 패턴):

| 오염 입력 | Kiwi `space()` 출력 | 판정 |
|---|---|---|
| `했습니 다 우리 가 함께 기도 하 겠습니다` | `했습니다 우리가 함께 기도하겠습니다` | ✅ 완벽 |
| `그러므 로형제자매여러분우리는` | `그러므로 형제 자매 여러분 우리는` | ✅ 완벽 |
| `주님 께서말씀 하시기를 사랑 하라 하셨 습니다` | `주님께서 말씀하시기를 사랑하라 하셨습니다` | ✅ 완벽 |

- 성능: 첫 호출은 모델 로드(~2s), 이후 문장당 ms 단위. → **`Kiwi` 인스턴스는 프로세스당 싱글턴**으로 1회 로드.
- 주의: `space()`가 성경 인용을 `삼 장 십 육 절`로 분해 → **`normalizer`의 성경표기 정규화를 Kiwi `space()` 이전에 실행**(순서 고정)하거나 숫자 병합 후처리 추가.

**Tier 2 — LLM 재구성 (Kiwi로 안 되는 실제 전사 오류·구두점·가독성)**
- 이미 존재하는 멀티-프로바이더 라우터 **재사용**: `services/llm/fallback.py::chat_with_fallback` (DeepSeek 우선 → Gemini/Claude/OpenAI/Tencent 폴백).
- Kiwi 복원 후에도 `broken_word_ratio`/문장무결성이 임계 초과인 청크에만 **선택적·캐시**로 호출 → 비용 최소.
- 프롬프트 원칙: "의미·신학 내용 절대 변경 금지, 띄어쓰기·구두점·명백한 오탈자만 교정".

> 정리: **Kiwi(1차, 전량) → 잔여 오염만 LLM(2차, 선택)**. Kiwi 단독으로 broken-word율 대부분 해소, LLM은 마지막 안전망.

## 0. 증명된 3대 결함 (현황)
1. **문장 shredding (최악)** — `chunker.py:89` `_SENT_SPLIT_RE` 단일문자 lookbehind `(?<=[다까…다요])\s*`. '다'가 세트에 2번, 어중(보다/다는)에서도 강제분리. 실측: 1문장→7조각.
2. **ASR 공백 파괴 + 정규화 방치 (근본)** — 원고가 구어체 전사본(`했습니 다`, `하나 님`). `normalizer._normalize_whitespace`는 "다중공백→1"만, **단어병합 없음** → 67/67 청크 오염.
3. **품질게이트 사각지대** — `quality_gate.py`는 빈/중복/사이즈/신학위반만 검사. **깨진 단어·문장파편은 통과** → 조용한 오염.

> 구조: 파이프라인 A(`ingest_pipeline.py` Stage1-7)와 B(`enhanced_rag/*`)가 **둘 다 같은 `chunk_text`를 공유** → 한 곳만 고쳐도 양쪽 적용. 이미 `restructurer`/`contextualizer`/`quality_gate` 존재.

## 1. 타겟 레이어맵
```
[0] 소스/ASR 위생 → [1] 정규화+띄어쓰기복원 ★ → [2] 구조화(LLM, 프론트매터분리)★
→ [3] 문장분리(수정)★ → [4] 청킹(의미경계+Parent-Child)★ → [5] 컨텍스트(LLM)
→ [6] 메타추출 → [7] 품질게이트 v2(Debris 검출)★ → [8] 임베딩(bge_m3+sparse)/하이브리드
→ [9] Ingestion Eval Harness ★
```

## 2. 핵심 개선
- **★ Spacing Restoration** (`services/spacing.py`, `normalizer` 최선단): **Kiwi `space()` 전량** → 잔여 오염만 LLM 폴백.
- **문장분리 수정**: `chunker.py:89` 단일문자 lookbehind 제거 → **Kiwi `split_into_sents()` 우선**, 정규식 폴백.
- **의미 기반 청킹 + Parent-Child**: 문장임베딩 유사도 급락 지점을 경계로 추가. Child(~256tok, 검색용)+Parent(~1024tok, 생성용) 저장.
- **품질게이트 v2 Debris Detector**: `broken_word_ratio`(한글 사이 공백 비율) 임계 초과 → spacing 재적용/격리. 문장 무결성(종결어미로 끝나는지) 검사 추가.
- **임베더 재검토**: `kure`→`bge_m3`(다국어+sparse) 기본 후보 벤치. 하이브리드(dense+sparse) + 중국어 청중 dual-vector(`dense_ko`/`dense_zh`) 활성화 검토.
- **단일 청킹 코어**: 두 파이프라인이 같은 수정된 `chunk_text`만 쓰도록 정리.
- **Ingestion Eval Harness**: broken-word율 / 문장무결성 / recall@k 를 수정 전후 동일 세트로 비교(숫자 증명).

## 3. 로드맵
| 우선 | 항목 | 의존 | 효과 |
|------|------|------|------|
| P0 | 문장분리 정규식 수정 (`chunker.py:89`) | 없음 | shredding 즉시 해결 (A/B 양쪽) |
| P0 | 프론트매터/본문 분리 | 없음 | chunk0 메타 오염 제거 |
| P0 | Spacing Restoration (`services/spacing.py`) | Kiwi/rule | 근본 원인 해결 |
| P1 | Quality Gate v2 debris | 없음 | 조용한 오염 차단 |
| P1 | 의미경계+Parent-Child 청킹 | 임베더 | 정밀도+맥락 |
| P2 | 임베더 bge_m3+하이브리드 | 모델 | 다국어/어휘 검색 |
| P2 | Eval Harness | — | before/after 수치 |

## 4. Kiwi 설치 (해결됨)
- 올바른 패키지명 **`kiwipiepy`** (이전 `kiwipiepie`는 오타→404). `pip install kiwipiepy` **성공**(cp312 win64 wheel). `requirements.txt`에 `kiwipiepy` 추가 필요.

## 5. 기대 효과 (가설)
- broken-word율 100%→≈0%, shredding 0건, 검색 recall@k +상승, LLM 응답 인용 정확도 개선.
- 상류(spacing)만 고쳐도 restructurer/contextualizer 입력이 깨끗해져 LLM 비용 대비 품질이 가장 크게 상승.
