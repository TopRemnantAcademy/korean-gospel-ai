# 설계안: Gemini 스트리밍 실측(usage_metadata) 도입 평가

- **문서 유형**: 독립 평가 기획서 (구현 전 검토용)
- **작성일**: 2026-08-03
- **관련 요청**: "② gemini 스트리밍 실측 필요 시 usage_metadata 스트리밍 가용성 확인 (독립 평가)"
- **상태**: `PROPOSED` — 본 문서는 설계·리스크·검증 계획만 정의하며, 코드 변경은 승인 후 별도 작업으로 분리

---

## 1. 배경과 문제 정의

### 1.1 현재 원가 정밀도 상태
- 스트리밍 경로의 토큰 비용은 공급자가 usage 를 반환하지 않으면 **추정(estimate)** 으로 기록된다 (가용성 우선, fail-open).
- OpenAI 호환 공급자(nvidia, tencent)는 `stream_options={"include_usage": True}` 로 최종 청크 usage 를 실측 캡처하여 정밀 원가를 기록한다 (`base.py: capture_stream_usage`, `chat.py` finalize).
- **Gemini** 는 현재 스트리밍에서 usage 를 캡처하지 않아, gemini 폴백 구간에서 발생하는 비용은 추정값으로 남는다.

### 1.2 근본 원인 (코드 증거)
`backend/app/services/llm/gemini.py` 의 `stream()` (72–101행) 은:

```python
async for chunk in response_stream:
    text = getattr(chunk, "text", None)
    if text:
        yield text
```

- `chunk.usage_metadata` 를 **읽지도 않고 버린다**.
- 비-streaming `chat()` (57–59행) 은 이미 `resp.usage_metadata.prompt_token_count / candidates_token_count` 를 정상 읽는다. 즉 SDK 가 usage 필드를 제공함은 확정.
- `google-genai` SDK 는 스트리밍 마지막 청크에 `usage_metadata` 를 포함해 전송하는 것이 공식 스펙이다 (OpenAI 호환의 `include_usage` 와 동일한 의도, 단 플래그 불필요).

### 1.3 평가 질문
> Gemini 스트리밍에서 `usage_metadata` 가 안정적으로 획득 가능한가? 가능하다면 기존 nvidia/tencent 와 동일한 정밀 원가 경로에 편입시킬 수 있는가?

---

## 2. 가설과 검증 방법

### 2.1 가설
`H1`: Gemini `generate_content_stream` 의 **최종 청크**에 `usage_metadata`(prompt/candidates token count)가 포함되며, 이를 캡처해 `last_stream_usage` 에 주입하면 nvidia/tencent 와 동일하게 **정밀 원가 기록** 이 가능하다.

### 2.2 검증 절차 (독립 평가 단계)
실제 구현 전, 코드 변경 없이 **탐색 스크립트**로 가설을 검증한다.

1. **샌드박스 스크립트** `scripts/_probe_gemini_stream_usage.py` (임시, 평가 후 삭제) 작성
   - 실제 `GeminiLLM.stream()` 과 동일 호출(`aio.models.generate_content_stream`) 수행
   - `async for chunk` 루프에서 **매 청크** `hasattr(chunk, "usage_metadata")` 및 값 로깅
   - 마지막 청크에서 `usage_metadata.prompt_token_count` / `candidates_token_count` 확인
2. **판정 기준**
   - ✅ 최종 청크에 non-null `usage_metadata` 가 존재 → `H1` 채택, 구현 진행
   - ⚠️ 일부 모델/설정에서만 존재(예: `thinking`/extensions 켜진 경우 누락 가능) → 조건부 채택, 폴백 추정 유지
   - ❌ 스트리밍에서 완전히 미제공 → `H1` 기각, gemini 는 추정 경로 유지 (별도 작업 없음)

### 2.3 경계 조건 (리스크)
| 리스크 | 설명 | 대응 |
|---|---|---|
| 모델별 차이 | 일부 gemini 모델은 스트리밍 usage 미제공 가능 | 모델 화이트리스트 또는 런타임 감지 후 폴백 |
| thinking/tool_use | 중간 청크에만 토큰 합산 불완전 | 최종 청크 기준, 누락 시 추정 |
| 캡처 누락 시 silent | usage 못 읽으면 비용 0 기록 위험 | `capture_stream_usage` None-safe + chat.py 추정 폴백 이미 존재 → 안전 |

---

## 3. 제안 설계 (H1 채택 시)

기존 nvidia/tencent 패턴(`base.py`, `tencent.py`, `nvidia.py`)과 **완전히 동일한 아키텍처**를 따른다 (새 인터페이스 금지 원칙).

### 3.1 `gemini.py` 수정
```python
async def stream(self, messages, *, temperature=0.3, max_tokens=1500, system=None):
    from google.genai import types
    ...
    self.last_stream_usage = None  # fallback.py 에서도 리셋하지만 방어적
    async for chunk in response_stream:
        text = getattr(chunk, "text", None)
        if text:
            yield text
        # 최종 청크 usage_metadata 캡처 (nvidia/tencent 와 동일 계약)
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            self.capture_stream_usage(um)  # base.py 공용 헬퍼 재사용
```
- `capture_stream_usage` 는 OpenAI `usage` 객체를 가정 → gemini `usage_metadata` 는 필드명이 다르므로 **어댑터** 필요:
  - `usage_metadata.prompt_token_count` → `prompt_tokens`
  - `usage_metadata.candidates_token_count` → `completion_tokens`
  - `usage_metadata.total_token_count` → `total_tokens`(없으면 합산)

### 3.2 `base.py` 확장 (최소)
`capture_stream_usage` 가 공급자별 usage 객체 형태를 수용하도록 **프로바이더 판별 또는 매핑 인자** 추가 — 단, nvidia/tencent 는 OpenAI 객체이므로 기존 경로 보존, gemini 용 분기만 추가. (기존 시그니처 훼손 금지)

### 3.3 `chat.py` finalize
변경 불필요. 이미 `llm.last_stream_usage` 우선 → 없으면 추정. gemini 가 `capture_stream_usage` 채우면 자동 정밀 기록.

### 3.4 데이터 흐름 (정합성)
```
GeminiLLM.stream()
  └─ chunk.usage_metadata → capture_stream_usage → self.last_stream_usage
chat_with_fallback() → stream_with_fallback() → (llm.last_stream_usage 유지)
chat.py finalize → save_interaction_and_finalize_tokens(prompt_tokens, completion_tokens)
  └─ rate_service.calculate_cost() → cost_krw 정밀 기록 (추정 아님)
```

---

## 4. 테스트 계획
- `tests/test_gemini_stream_usage.py` (신규)
  1. 더미 `usage_metadata` 객체(최종 청크) 주입 → `capture_stream_usage` 가 `LLMResponse` 로 변환되는지
  2. `stream()` 이 usage 가 없는 청크를 지나 마지막에 usage 가 있을 때 `last_stream_usage` 가 세팅되는지 (fake async iterator)
  3. `usage_metadata` 가 아예 없는 경우 `last_stream_usage` 가 None 으로 남아 chat.py 추정 폴백이 작동하는지
- 기존 `test_stream_usage_capture.py` (nvidia/tencent) 와 동일 패턴, pytest `asyncio.run()` 래핑 (pytest-asyncio 미설치)

---

## 5. 배포/운영 고려
- `KRAI_PUBLIC_MODE`, 환경변수 변경 없음 — 순수 내부 정밀도 개선.
- 기존 추정 경로는 폴백으로 잔존 → 가용성 우선 원칙 유지.
- `scripts/seed_ccp_rates.py` 로 등록된 gemini 단가가 있다면 즉시 정밀 원가로 반영됨 (① 작업과 시너지).

---

## 6. 결론 및 권고
- **기술적 가용성**: `google-genai` SDK 가 스트리밍 최종 청크에 `usage_metadata` 를 실어 보내므로, **H1 채택 가능성 높음**. 단 2.2 탐색 스크립트로 실제 응답을 1회 확인 후 구현 돌입 권고.
- **구현 범위**: `gemini.py` + `base.py` 최소 변경, `chat.py` 변경 없음. 기존 아키텍처 100% 재사용.
- **독립성**: 본 평가는 ① 원가 단가 UI 등록과 별개 작업. 단가가 등록되어야 정밀 원가가 의미 있으므로 ① 완료 후 연계 권고.
- **다음 단계**: 사용자 승인 → 2.2 탐색 스크립트 실행 → 결과에 따라 3.x 구현.
