---
title: 한국어 복음 AI
emoji: ✝️
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.41.1
app_file: user/app.py
pinned: false
license: mit
---

# ✝️ 한국어 복음 AI (v2 · 2026 Architecture)

한국어 RAG 시스템. **임베딩·청킹·재순위·정책** 4가지 모두 한국어 최적화.

## 🧱 아키텍처

| 레이어 | 도구 | 교체 가능? |
|---|---|---|
| LLM | **Gemini 2.5 Flash** (default) | ✅ OpenAI/Claude/Ollama 어댑터 포함 |
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
nano .env.production  # 모든 비밀키 설정

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

## 📊 모니터링 (Monitoring)

```bash
# 1) 의존성 설치
python -m venv venv
venv\Scripts\activate            # Windows / source venv/bin/activate (mac)
pip install -r requirements.txt

# 2) 환경변수
copy .env.example .env           # Windows / cp .env.example .env
# .env 열어서 GOOGLE_API_KEY 등 채우기

# 3) Qdrant 시작
docker compose up -d qdrant

# 4) 문서 인덱싱 (data/documents/* → kure 와 bge_m3 컬렉션 동시)
python scripts/ingest_all.py --embedders kure,bge_m3

# 5) API + Admin UI 띄우기
scripts\start_local.bat          # Windows (두 개 창)
# 또는
uvicorn backend.app.main:app --reload --port 8000
streamlit run admin/app.py
```

접속:
- API Swagger: http://localhost:8000/docs
- Admin UI: http://localhost:8501
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

### POST `/ingest/file` (admin token 필요)
```bash
curl -X POST http://localhost:8000/ingest/file \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -F "file=@path/to/sermon.pdf" \
  -F "embedders=kure,bge_m3"
```

### POST `/eval/ab` (admin)
```bash
curl -X POST http://localhost:8000/eval/ab \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -d '{"queries":["죄란?","구원?"], "embedders":["kure","bge_m3"], "top_k":5}'
```

## 🆎 임베딩 A/B 자동 평가

```bash
python scripts/ab_test.py --embedders kure,bge_m3,e5
```
출력 예:
```
=== kure ===
  평균 latency : 0.21s
  평균 top1    : 0.812
  Hit@5        : 5/5  (100.0%)

=== bge_m3 ===
  평균 latency : 0.27s
  ...
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

## 🌐 서버 배포 (Hugging Face Spaces, Render, Fly.io 모두 가능)

자세한 가이드: `deploy.md`

## 📁 폴더 구조

```
korean-gospel-ai/
├── .env / .env.example
├── docker-compose.yml
├── requirements.txt
├── README.md / deploy.md
├── backend/app/
│   ├── main.py · config.py
│   ├── api/        chat · retrieval · ingest · eval · admin
│   ├── services/
│   │   ├── llm/    base · gemini · openai · claude · ollama · factory
│   │   ├── embedding/  base · kure · bge · e5 · factory
│   │   ├── vector_store · chunker · reranker · retriever · policy · tracing
│   ├── models/schemas.py
│   └── prompts/system.py
├── admin/app.py             # Streamlit 관리자 UI
├── data/
│   ├── documents/           # 인덱싱 대상
│   └── eval/                # 평가 셋, 정책 룰북
└── scripts/
    ├── ingest_all.py
    ├── ab_test.py
    └── start_local.bat / .sh
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

## 🧭 다음 확장 포인트

- [x] LLM provider 자동 fallback (rate limit 감지 → 다음 provider, `LLM_FALLBACK_*`)
- [x] 평가 셋 자동 생성 (`POST /eval/generate-questions`, `scripts/generate_eval_set.py`)
- [x] hybrid 가중치 자동 튜닝 (`POST /eval/tune-weights`, `scripts/tune_hybrid_weights.py`)
- [x] MultiVector / ColPali (멀티모달 PDF) 어댑터 (`pdf_vision/`, `PDF_VISION_PROVIDER`, `scripts/ingest_documents.py`)
- [x] 사용자 피드백(👍/👎) → Langfuse score (`POST /feedback`, user UI)
