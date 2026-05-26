# 🚀 배포 가이드

<!--
=============================================================================
🔧 AI-AGENT-WORK
Agent: Claude (Cowork)
Timestamp: 2026-05-25 00:00
Task: deploy.md 갱신 — (1) 삭제된 ingest_all.py 참조 → ingest_documents.py 로 교체,
      (2) 현재 1순위 배포 전략(Cloudflare Tunnel) 옵션 A 로 추가,
      (3) 옛 HF Spaces/Render/VPS 옵션은 Tier 2 진입 시 참고용으로 유지
Reason: 5/10 작성 후 시스템 변경 누적 (scripts/ingest_all.py 삭제 #42, M-1 Cloudflare Tunnel 완료 5/21)
Related: ORDERS M-1, 사용자 정리 요청 2026-05-25
Status: COMPLETED
=============================================================================
-->

이 시스템은 두 개의 프로세스(FastAPI + Streamlit)와 한 개의 인프라(Qdrant)로 구성됩니다.

> **현재 1순위 배포 전략 = Cloudflare Tunnel (옵션 A).** HF Spaces / Render / VPS 는 Tier 2 진입(유료 인프라 단계) 시 참고용.

## 옵션 A. Cloudflare Tunnel (권장 · Tier 0.5 · $0) ⭐ 현재 사용 중

운영자 PC 가 그대로 호스트, 외부 친구·시범 사용자가 진짜 도메인 URL 로 접근.

**준비물**: Cloudflare 계정 (무료)

**단계**:
1. `scripts/install_cloudflared.bat` 실행 → cloudflared 설치
2. `cloudflared tunnel login` (브라우저 1회 인증)
3. `cloudflared tunnel create gospel-ai`
4. 루트 `config.yml` 의 `credentials-file` 경로를 자기 PC 의 UUID 파일로 교체
5. `STEP4_TUNNEL.bat` 더블클릭 → 터널 가동
6. **베타 초대 코드**: Admin UI → 초대 코드 페이지에서 발급 → 사용자에게 배포

**상세 가이드**: `docs/TUNNEL_GUIDE.md` (6단계 친절 설명)

**장점**: 트래픽 100% 무료, 운영자 PC 끄면 자연스러운 점검 페이지, Cloudflare Access 로 Admin 보호 가능.

## 옵션 B. Hugging Face Spaces (Tier 1.5 진입 시 · 무료/유료 혼합)

가장 빠릅니다. 다만 무료 Space는 컨테이너 1개라 **API 또는 Admin UI 중 하나**만 띄울 수 있습니다.

추천 분리:
- **Space 1**: Streamlit Admin UI (사용자 접속용)
- **Space 2** (옵션): FastAPI API (Dify 등 외부 시스템 연결용)
- **Qdrant**: Qdrant Cloud 무료 1GB (https://cloud.qdrant.io)

### 단계
1. https://cloud.qdrant.io 가입 → 무료 cluster 생성 → URL/API key 받음
2. https://huggingface.co/new-space → SDK: Docker (또는 Streamlit)
3. 본 폴더 그대로 push (`git remote add hf …` → `git push hf main`)
4. Space Settings → Variables and secrets:
   - `QDRANT_URL` (Cloud URL)
   - `QDRANT_API_KEY`
   - `GOOGLE_API_KEY`
   - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (옵션)
   - `ADMIN_API_KEY`, `DIFY_API_KEY`
   - `APP_PASSWORD` (Admin 잠금)
5. Space가 빌드되면 `python scripts/ingest_documents.py` 를 한 번 실행 (HF는 startup hook 또는 admin UI에서 트리거)

## 옵션 C. Render / Fly.io / Railway (Tier 2 진입 시)

Docker 기반 배포. `Dockerfile` 추가 필요(아래 템플릿).

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Streamlit 따로 띄우려면 두 번째 service:
```dockerfile
CMD ["streamlit", "run", "admin/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
```

## 옵션 D. 본인 VPS (AWS/네이버클라우드/카페24 클라우드 · Tier 2+)

```bash
# 1) Docker compose 통째로 (Qdrant + API + Admin)
docker compose up -d
# (compose 에 api, admin 서비스 추가 필요 — Dockerfile 작성 후)
```

또는 systemd:
```ini
# /etc/systemd/system/gospel-api.service
[Service]
WorkingDirectory=/opt/korean-gospel-ai
ExecStart=/opt/korean-gospel-ai/venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/opt/korean-gospel-ai/.env
```

Nginx로 https + 도메인:
```nginx
server {
  listen 443 ssl http2;
  server_name your.domain.com;
  ssl_certificate ...; ssl_certificate_key ...;
  location /api/  { proxy_pass http://127.0.0.1:8000/; }
  location /     { proxy_pass http://127.0.0.1:8501; }
}
```

## 운영 체크리스트

- [ ] `.env` 의 모든 키가 실제 값으로 채워졌는가
- [ ] `ADMIN_API_KEY`, `DIFY_API_KEY` 가 강한 랜덤값인가
- [ ] Qdrant 가 외부에 노출되지 않는가 (포트 6333은 내부망만)
- [ ] Langfuse 가 활성화되어 추적이 들어오는가
- [ ] `/admin/health` 가 200 OK
- [ ] 첫 인덱싱 (`scripts/ingest_documents.py`) 한 번 돌렸는가
