# Langfuse OFF + 셀프 관측 강화 + 조언 항목 전문가 결정

> 요청: "Langfuse off + 셀프 강화(기업수준) + 조언 항목은 전문가 입장에서 객관적으로 전부 해결"
> 결과: Langfuse 완전 비활성, 외부 SaaS 없이도 동작하는 셀프호스팅 트레이싱 구축, 조언 항목은 전문가 판단으로 결정·반영.

---

## 1. Langfuse 완전 OFF (dev + prod)

| 파일 | 변경 |
|------|------|
| `.env`(dev) | `LANGFUSE_ENABLED=false` (키는 이전 턴 제거) |
| `.env.production` | `LANGFUSE_ENABLED=true`→`false`, 키 3줄 제거 |

**Langfuse 판단 근거(객관)**: LLM 관측 도구일 뿐 핵심 기능 아님. `cloud.langfuse.com`은 미국 호스팅이라 중국대륙(타깃 시장) 접근 불안정 — Google 의존을 제거했던 것과 동일 사유. 자체 `trace.event()` 인프라가 이미 존재.

---

## 2. 셀프호스팅 트레이싱 (기업 수준)

`app/services/tracing.py` 전면 재작성 — **Langfuse 없이도 동일 인터페이스로 동작**:

- `_LocalTraceClient` / `_LocalTrace` / `_LocalGeneration` 구현 (Langfuse Client/Trace/Generation 과 동일 메서드 시그니처: `trace()`, `.event()`, `.update()`, `.generation()`, `.end()`, `.score()`, `.id`).
- `get_client()` 가 Langfuse 비활성 시 `None` 대신 **로컬 클라이언트** 반환 → 기존 `chat.py`/`chat_pipeline.py` 의 `trace.event(...)` 호출이 **이제 전부 실제 기록**됨(기존엔 조용히 폐기).
- 구조화 JSONL 출력: `logs/traces.jsonl` (RotatingFileHandler 10MB×5) — trace_id 로 전 이벤트 상관관계, latency_ms, usage 기록.
- **시크릿 마스킹**: `logging_setup.scrub_secrets` 재사용 (API 키/토큰/비밀번호 `[REDACTED]`).

**검증 출력 예시** (실제 기록):
```json
{"ts":..., "trace_id":"d36f...", "trace_name":"chat", "type":"trace_start", "input":{"query":"구원이란 무엇인가요"}, "user_id":"anon_test"}
{"ts":..., "trace_id":"d36f...", "type":"event", "name":"input_policy", ...}
{"ts":..., "trace_id":"d36f...", "type":"generation", "name":"answer", "model":"nemotron", "usage":{"input":100,"output":200}, "latency_ms":0.0}
```
```text
api_key=mysecret123 → api_key=[REDACTED]   ✅ 마스킹 확인
```

---

## 3. 조언 항목 — 전문가 결정·반영

| 항목 | 전문가 결정 | 반영 |
|------|-------------|------|
| **LLM primary** | nvidia 우선(실측 TTFT 0.48s). reasoning(tencent, ~78s)은 폴백 전용 — 채팅 UX 에 78s 는 부적합 | `.env`·`.env.production` 모두 `LLM_PROVIDER=nvidia` + `LLM_FALLBACK_CHAIN=nvidia,tencent,gemini` |
| **PORTONE_WEBHOOK_SECRET** | `secrets.token_urlsafe(48)` 랜덤 생성 | `.env`·`.env.production` 설정 (+ `.env.production` 에 PortOne 섹션 신설) |
| **PORTONE_CHANNEL_KEY** | 위조 불가 → 기동 시 조기 경고로 가시화 | `main.py` 시작 검증 추가(채널키/웹훅시크릿 누락 시 WARNING) |
| **DOCS_ENABLED** | 운영은 false | `.env.production` `DOCS_ENABLED=false` (이전 턴) |
| **APK API 도메인** | 빌드 시 localhost 가드 경고 | `build-config.js` (이전 턴) |

---

## 검증 요약

- `py_compile` · `pytest` · `import app.main` 통과.
- prod env 시뮬레이션: `langfuse=False · docs=False · llm=nvidia · webhook_secret=True`.
- 트레이스 JSONL 기록 + 시크릿 마스킹 실제 확인.

---

## 잔여 (외부 값/자산이 필수 — 위조 불가)

1. **`PORTONE_CHANNEL_KEY`** — PortOne 콘솔에서 결제 채널키 발급 필수. 받으시면 `.env`·`.env.production`에 넣어드립니다.
2. **`PORTONE_WEBHOOK_SECRET` 등록** — 방금 생성한 시크릿(`mOcfoFJ-HNMu8iWB_2k_iN5ocIX30C1tV5t7Gy28UWVb3dV069zsSkTadCL0yXWT`)을 **PortOne 콘솔 웹훅 설정**에 동일하게 등록해야 서명 검증이 동작합니다.
3. **APK API 도메인** — 실제 백엔드 HTTPS 도메인 필요.
4. **런처 아이콘** — 512×512 PNG 브랜드 이미지.
