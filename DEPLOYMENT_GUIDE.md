# 🚀 Deployment Guide -

## 📋 Pre-Deployment Checklist

- [ ] `.env.production` configured with all secrets
- [ ] `ADMIN_API_KEY` changed from default
- [ ] `APP_PASSWORD` set for admin UI
- [ ] Qdrant connected (compose `qdrant` 컨테이너 또는 Qdrant Cloud URL+key)
- [ ] Langfuse enabled and keys configured
- [ ] Token quota enabled (`TOKEN_QUOTA_ENABLED=true`)
- [ ] Rate limiting enabled (`RATE_LIMIT_ENABLED=true`)
- [ ] `DOCS_ENABLED=false` (공개 배포 시 /docs 노출 차단)
- [ ] `APP_ENV=prod` (운영 모드)
- [ ] `KRAI_PUBLIC_MODE=true` (8501 공개 모드 — 관리자 진입 차단)
- [ ] `UVICORN_WORKERS` set per CPU (4vCPU=2)
- [ ] Tested locally with production config
- [ ] Database backed up
- [ ] Documents backed up

---

## 🌐 Deployment Options

### Option 1: Docker Compose (Recommended)

#### 1. Prepare environment
```bash
# Copy production template
cp .env.production.template .env.production

# Edit with real secrets
nano .env.production
```

#### 2. Configure secrets
```bash
# ✅ REQUIRED: Change these!
ADMIN_API_KEY=<generate-strong-key>
APP_PASSWORD=<set-admin-password>
GOOGLE_API_KEY=<your-gemini-key>
DEEPSEEK_API_KEY=<your-deepseek-key>
QDRANT_API_KEY=<your-qdrant-key>
QDRANT_URL=https://your-cluster.qdrant.tech:6333

# ✅ RECOMMENDED: Enable monitoring
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# ✅ SECURITY: Enable rate limiting
TOKEN_QUOTA_ENABLED=true
RATE_LIMIT_ENABLED=true

# ✅ PERF: uvicorn 워커 수 (4vCPU 박스=2, 2vCPU 박스=1)
UVICORN_WORKERS=2

# ✅ SECURITY: 공개 배포 시 아래 적용
APP_ENV=prod
DOCS_ENABLED=false
KRAI_PUBLIC_MODE=true
# (공개 8501 와 관리자 허브 8502 는 별도 프로세스 — 8502 를 노출하지 않으면 관리자 차단됨)
```

#### 3. Deploy
```bash
# Make deploy script executable
chmod +x deploy.sh

# Deploy to production
./deploy.sh production

# Or manually:
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

#### 4. Verify
```bash
# Check health
curl http://localhost:8000/health

# Check containers
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f backend
```

---

### Option 2: Railway (Easiest)

#### 1. Connect GitHub repo
- Go to [Railway](https://railway.app)
- New Project → Deploy from GitHub repo
- Select `TopRemnantAcademy/korean-gospel-ai`

#### 2. Configure environment
- Add all variables from `.env.production.template`
- Set `QDRANT_URL` to Qdrant Cloud URL
- Add volume for `/data`

#### 3. Deploy
- Railway auto-deploys on push to `main`

---

### Option 3: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch
fly launch

# Set secrets
fly secrets set ADMIN_API_KEY=<key>
fly secrets set GOOGLE_API_KEY=<key>
fly secrets set DEEPSEEK_API_KEY=<key>
fly secrets set QDRANT_API_KEY=<key>

# Deploy
fly deploy
```

---

## 📊 Post-Deployment

### 1. Verify services
```bash
# Backend health
curl https://your-domain.com:8000/health

# Qdrant health
curl https://your-domain.com:6333/health

# User UI
open https://your-domain.com:8501

# Admin UI
open https://your-domain.com:8502
```

### 2. Setup monitoring
- **Langfuse**: https://cloud.langfuse.com
  - Check traces
  - Setup alerts
  - Monitor token usage

### 3. Test features
- [ ] Chat endpoint works
- [ ] Streaming works
- [ ] File upload works (test with <100MB file)
- [ ] Preview endpoint works
- [ ] Rate limiting works

---

## 🔧 Troubleshooting

### Backend won't start
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs backend

# Common issues:
# - ADMIN_API_KEY=change-me (must change!)
# - QDRANT_URL incorrect
# - Missing API keys
```

### Qdrant connection failed
```bash
# Test Qdrant connection
curl -H "api-key: <your-key>" https://your-cluster.qdrant.tech:6333/health

# Check collection
curl -H "api-key: <your-key>" \
  https://your-cluster.qdrant.tech:6333/collections
```

### Langfuse not receiving traces
```bash
# Check Langfuse config
echo $LANGFUSE_ENABLED # should be "true"
echo $LANGFUSE_PUBLIC_KEY # should start with "pk-lf-"

# Check backend logs for Langfuse errors
grep -i langfuse logs/backend.log
```

---

## 🔒 Security Checklist

- [ ] `ADMIN_API_KEY` is strong (32+ random chars)
- [ ] `APP_PASSWORD` is strong
- [ ] `DIFY_API_KEY` is strong
- [ ] All API keys are in Railway/Fly secrets (not in .env files)
- [ ] Rate limiting enabled
- [ ] Token quota enabled
- [ ] CORS origins restricted to your domains only
- [ ] Qdrant API key set (not using default)
- [ ] Langfuse enabled for audit trail

---

## 📈 Scaling

### Single instance (current — Lighthouse 4vCPU/8GB)
- `docker-compose.prod.yml` 는 cgroup CPU/mem limit 로 8GB 내에서 안정 동작:
  - backend 3G(res 2G, 2CPU) · uvicorn workers=2 (UVICORN_WORKERS)
  - qdrant 2G(res 1G, 1CPU) · on-disk 벡터 mmap 으로 RSS 억제
  - ui 1.5G(res 768M, 1CPU) · caddy 256M
- 동시 ~100~200 사용자 수용 (워커 2 + 스트리밍).
- SQLite(WAL) 메타 + Qdrant 컨테이너(서버 모드) 벡터.

### Scale up (future / 더 큰 박스)
- `UVICORN_WORKERS` 를 CPU 수에 맞춰 상향 (공식: 2×CPU+1, 안전 상한 2~4).
- Redis 로 답변 캐시 공유 (`REDIS_URL` 설정 시 다중 워커 일관성).
- PostgreSQL 전환: `DATABASE_URL=postgresql://...` 만 바꾸면 됨(db.py 가 매핑).
- Qdrant Cloud: `.env.production` 의 `QDRANT_URL` 채우면 compose qdrant 서비스 제거 가능.
- 다중 백엔드 인스턴스 앞에 Caddy/로드밸런서 추가.

---

## 🆘 Rollback

```bash
# List backups
ls -lh backups/

# Restore database
cp backups/gospel_YYYYMMDD_HHMMSS.db gospel.db

# Restore documents
tar -xzf backups/documents_YYYYMMDD_HHMMSS.tar.gz

# Redeploy previous version
git log --oneline | head -5
git checkout <previous-commit>
./deploy.sh production
```

---

## 📞 Support

- **Issues**: https://github.com/TopRemnantAcademy/korean-gospel-ai/issues
- **Docs**: https://github.com/TopRemnantAcademy/korean-gospel-ai/docs
- **Langfuse**: https://cloud.langfuse.com
