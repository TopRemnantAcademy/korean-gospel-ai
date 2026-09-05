---
title: 한국어
emoji: ✝️
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.41.1
app_file: app.py
pinned: false
license: mit
---

# ✝️ 한국어 (v2 · 2026 Architecture)

한국어 RAG 시스템. **임베딩·청킹·재순위·정책** 4가지 모두 한국어 최적화.

## 🧱 아키텍처

| 레이어 | 도구 | 교체 가능? |
|---|---|---|
| LLM | **Gemini 2.5 Flash** (`.env.example` 기본값, 운영은 `tencent→nvidia→gemini` 폴백 체인) | ✅ OpenAI/Claude/Ollama/Tencent/NVIDIA 어댑터 포함 |
| 임베딩 | **KURE-v1** (한국어 SOTA, default) | ✅ bge-m3, multilingual-e5 |
| 벡터 DB | **Qdrant** (hybrid: dense + BM42 sparse) | - |
| Reranker | **bge-reranker-v2-m3** | ✅ Cohere/None |
| 청킹 | **kss** (한국어 문장 분리) | - |
| 검색 | dense + sparse → **RRF 융합** → rerank | - |
| 추적 | **Langfuse** (`@observe` 자동 기록) | - |
| 정책 | **입력 룰북 + 출력 LLM-judge** | YAML 편집 |
| API | **FastAPI** (chat, retrieval, ingest, eval, admin) | - |
| 운영 UI | **Streamlit Admin** (최소) | - |
| 외부 통합 | **Dify External Knowledge API 호환 `/retrieval`** | - |

## 🚀 배포 (Deployment)

### Docker Compose (추천)

```bash
# 1. 프로덕션 환경 설정
cp .env.production.template .env.production
nano .env.production # 모든 비밀키 설정

# 2. 배포 스크립트 실행
chmod +x deploy.sh
./deploy.sh production

# 3. 서비스 확인
curl http://localhost:8000/health
```

**배포 가이드**: `DEPLOYMENT_GUIDE.md` 참조
**모니터링 가이드**: `MONITORING_GUIDE.md` 참조

### Railway (가장 쉬움)

1. [Railway](https://railway.app) 가입
2. "New Project" → "Deploy from GitHub repo"
3. `TopRemnantAcademy/korean-gospel-ai` 선택
4. Environment Variables에 `.env.production` 내용 입력
5. "Deploy" 클릭

### Fly.io

```bash
# Fly CLI 설치
curl -L https://fly.io/install.sh | sh

# 배포
fly launch
fly secrets set ADMIN_API_KEY=<key>
fly deploy
```

---

## 💻 로컬 개발

```bash
# 1) 의존성 설치
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# 2) 환경변수
copy .env.example .env
# .env 열어서 GOOGLE_API_KEY, ADMIN_API_KEY 등 채우기

# 3) Qdrant 시작
docker compose -f docker-compose.prod.yml up -d qdrant

# 4) API 실행
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000

# 5) Admin UI 실행
.\venv\Scripts\python.exe -m streamlit run admin/app.py
```

접속:
- API Swagger: http://localhost:8000/docs
- User 통합앱 UI: http://localhost:8501
- Admin Hub UI: http://localhost:8502
- Qdrant Dashboard: http://localhost:6333/dashboard

## 📚 주요 엔드포인트

### POST `/chat`
```json
{
  "query": "죄란 무엇인가요?",
  "history": [],
  "llm_provider": "gemini",
  "embedder": "kure"
}
```
응답: `answer`, `sources[]`, `policy{}`, `llm_model`, `embedder`, `elapsed_ms`, `trace_id`.

### POST `/retrieval` (Dify External Knowledge API 호환)
```bash
curl -X POST http://localhost:8000/retrieval \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_id": "kure",
    "query": "거듭난다는 것은?",
    "retrieval_setting": { "top_k": 5, "score_threshold": 0.0 }
  }'
```
응답:
```json
{
  "records": [
    {"content": "...", "score": 0.91, "title": "01_요한복음_3장.txt", "metadata": {...}}
  ]
}
```

### POST `/documents/upload` (admin token 필요)
```bash
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -F "file=@path/to/sermon.pdf" \
  -F "doc_type=sermon"
```

### POST `/documents/ingest-text` (admin token 필요)
```bash
curl -X POST http://localhost:8000/documents/ingest-text \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -F "title=요한복음 3장" \
  -F "content=본문 내용" \
  -F "doc_type=sermon"
```

## 🛡 정책/톤 검증

`data/eval/policy_rules.yaml` 편집:
```yaml
input_blocklist:
  HARM_SUICIDE: "(자살\\s*방법|...)"
output_must_avoid:
  - "당신은 구원받지 못합니다"
```
- 입력: 정규식 매칭 차단/경고
- 출력: LLM-judge가 `{pass, score, notes}` 반환 (`POLICY_LLM_JUDGE=true`일 때)

## 🌐 서버 배포

운영 배포는 `docker-compose.prod.yml`과 `deploy.sh`를 기준으로 합니다.

## 📁 폴더 구조

```
korean-gospel-ai/
├── .env / .env.example
├── docker-compose.prod.yml
├── requirements.txt / requirements-deploy.txt
├── README.md / deploy.sh
├── app.py # 통합 Streamlit UI
├── backend/app/
│ ├── main.py · config.py
│ ├── api/ chat · retrieval · documents · admin · mobile
│ ├── services/
│ │ ├── llm/ base · gemini · openai · tencent · nvidia · factory
│ │ ├── embedding/ base · kure · bge · e5 · hash_embedder · factory
│ │ ├── vector_store · chunker · reranker · retriever · policy · addiction_care
│ ├── models/schemas.py
│ └── prompts/system.py
├── admin/app.py # Streamlit 관리자 UI
├── user/ # (archived) 기존 사용자 UI — 루트 app.py로 통합
├── tests/ # pytest (중독 케어 등)
├── data/
│ ├── documents/ # 업로드/인덱싱 자료
│ └── eval/ # 정책 룰북·회귀 평가셋 (데이터)
└── scripts/
    ├── index_sermons.py
    ├── run_benchmark.py
    └── monitor_cache.py
```

## 📊 모니터링 (Monitoring)

### Langfuse (추천)

```bash
# .env.production
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

- **대시보드**: https://cloud.langfuse.com
- **기능**: LLM 추적, 지연 시간, 토큰 사용량, 사용자 피드백
- **가이드**: `MONITORING_GUIDE.md` 참조

### Qdrant Cloud

- **대시보드**: https://cloud.qdrant.tech
- **기능**: 컬렉션 상태, 메모리 사용량, 쿼리 성능

---

## 🔒 보안 체크리스트

- `.env` 절대 커밋 금지 (`.gitignore` 처리됨)
- Bearer 토큰 분리: `ADMIN_API_KEY`(/ingest, /eval, /admin) · `DIFY_API_KEY`(/retrieval)
- `APP_PASSWORD` 비우면 admin UI 잠금 OFF
- `AUTH_SECRET` 미설정 시 ADMIN_API_KEY 변경마다 모든 사용자 강제 로그아웃 — 강한 랜덤값 필수

## 📚 문서 지도

| 분류 | 문서 | 용도 |
|---|---|---|
| 진입 | `README.md` (본 파일) | 빌드/실행/운영 |
| 비전·신학 | `PROJECT_VISION.md` | 7가지 신학 상수, 미션 |
| 시스템 흐름 | `PROCESS_MAP.md` | 모듈/라우트/책임 지도 |
| 변경 이력 | `CHANGELOG.md` | 라운드별 변경 누적 |
| 운영 가이드 | `DEPLOYMENT_GUIDE.md`, `MONITORING_GUIDE.md`, `docs/TUNNEL_GUIDE.md`, `docs/FREE_TIER_GUIDE.md` | 배포/네트워킹/운영 |
| 설계 노트 | `docs/ENGINE_V2_DESIGN.md`, `docs/INGEST_PIPELINE_DESIGN.md` | 엔진/파이프라인 설계 |
| 아카이브 | `_archive/` | 폐기/대체된 자료 (협업 가이드·작업 큐·HANDOFF 포함, 참조용) |

## 🧭 다음 확장 포인트

- [x] LLM provider 자동 fallback (rate limit 감지 → 다음 provider, `LLM_FALLBACK_*`)
- [ ] Eval API / A/B 스크립트 재도입 (`data/eval/*.jsonl` 회귀 게이트)
- [ ] MultiVector / ColPali 기반 멀티모달 PDF 어댑터
- [x] 사용자 피드백(👍/👎) → Langfuse score (`POST /feedback`, user UI)
