# 로컬 전용 배포 (클라우드 의존성 0)

완전 오프라인으로 동작하는 로컬 프리셋. 클라우드 키 없이 바로 기동.

## 사전 준비 (1회)
1. **Ollama 설치** → https://ollama.com
2. 모델 받기:
   ```bash
   ollama pull qwen2.5:7b      # 권장 (약 4.4GB). GPU 없으면 3b 도 가능
   ```
3. Ollama 가 외부에서 접근 가능하도록(`host.docker.internal` 로 매핑):
   - Windows/Mac: Ollama 기본으로 localhost 바인딩 → `OLLAMA_HOST=http://host.docker.internal:11434` 사용.
   - Linux: `ollama serve` 가 `0.0.0.0:11434` 을 리스닝하도록
     `OLLAMA_HOST=0.0.0.0:11434 ollama serve` 또는 systemd Environment 추가.

## 기동 (1줄)
```bash
cp .env.local.template .env.local
docker compose -f docker-compose.local.yml --env-file .env.local up -d --build
```

## 접속
- UI: http://localhost:8501
- API: http://localhost:8000/health

## 클라우드 ↔ 로컬 전환
| 목적 | 명령 |
|------|------|
| 운영(클라우드/컨테이너 Qdrant) | `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build` |
| 로컬(embedded Qdrant, 오프라인) | `docker compose -f docker-compose.local.yml --env-file .env.local up -d --build` |

`.env.local` 은 `.gitignore` 에서 무시됨(시크릿 유출 방지). 템플릿 `.env.local.template` 만 커밋.

## 특징
- LLM: Ollama 로컬(`LLM_FALLBACK_ENABLED=false` 로 외부 폴백 차단 → 완전 오프라인)
- Embedder: kure/bge_m3 로컬 모델(오프라인)
- Qdrant: embedded(`local:./.qdrant_local`, 컨테이너 불필요)
- 결제/구독/푸시/Langfuse/RateLimit: 전부 비활성(자동降级 stub)
- Caddy 없음 → 8501 직접 노출
