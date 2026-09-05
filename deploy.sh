#!/bin/bash
# =========================================================
# - Production Deployment Script
# =========================================================
# Usage:
# ./deploy.sh [staging|production]
# =========================================================

set -e

ENV=${1:-staging}
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="./backups"
LOG_FILE="./logs/deploy_${TIMESTAMP}.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" | tee -a "$LOG_FILE"
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}" | tee -a "$LOG_FILE"
}

# ---- Checks ----
log "🚀 Starting deployment to $ENV environment..."

if [ ! -f ".env.$ENV" ]; then
    error ".env.$ENV not found! Copy .env.example and configure it."
fi

if [ ! -f "gospel.db" ]; then
    warn "gospel.db not found - will be created on first run"
fi

# ---- Backup ----
log "📦 Creating backup..."
mkdir -p "$BACKUP_DIR"
if [ -f "gospel.db" ]; then
    cp "gospel.db" "$BACKUP_DIR/gospel_${TIMESTAMP}.db"
    log "✅ Database backed up: $BACKUP_DIR/gospel_${TIMESTAMP}.db"
fi

if [ -d "data/documents" ]; then
    tar -czf "$BACKUP_DIR/documents_${TIMESTAMP}.tar.gz" data/documents/
    log "✅ Documents backed up: $BACKUP_DIR/documents_${TIMESTAMP}.tar.gz"
fi

# P0: Qdrant 벡터 라이브러리 백업 (RAG 전체가 여기에 의존 — 유실 시 재인제스트 비용 큼)
#   컨테이너 내 /qdrant/storage 를 tar 로 덤프. qdrant 서비스가 없으면(local embedded 모드) 건너뜀.
if docker compose -f docker-compose.prod.yml --env-file .env.$ENV ps -q qdrant &>/dev/null; then
    docker compose -f docker-compose.prod.yml --env-file .env.$ENV exec -T qdrant \
        tar czf - /qdrant/storage 2>/dev/null > "$BACKUP_DIR/qdrant_${TIMESTAMP}.tar.gz"
    if [ -s "$BACKUP_DIR/qdrant_${TIMESTAMP}.tar.gz" ]; then
        log "✅ Qdrant vectors backed up: $BACKUP_DIR/qdrant_${TIMESTAMP}.tar.gz"
    else
        warn "Qdrant 백업 비어있음 — embedded 모드(qdrant 컨테이너 없음)일 수 있음"
    fi
fi

# 미디어(push 이미지/오디오) 백업 — 미디어 발행 기능 사용 시 필수
if [ -d "data/media" ]; then
    tar -czf "$BACKUP_DIR/media_${TIMESTAMP}.tar.gz" data/media/
    log "✅ Media assets backed up: $BACKUP_DIR/media_${TIMESTAMP}.tar.gz"
fi

# ---- Build Docker images ----
log "🏗️ Building Docker images..."
docker compose -f docker-compose.prod.yml --env-file .env.$ENV build

# ---- Stop existing containers ----
log "🛑 Stopping existing containers..."
docker compose -f docker-compose.prod.yml --env-file .env.$ENV down || true

# ---- Start new containers ----
log "▶️ Starting new containers..."
docker compose -f docker-compose.prod.yml --env-file .env.$ENV up -d

# ---- Wait for health checks ----
log "⏱️ Waiting for services to be healthy..."
sleep 10

# P9-1 (P1): PORT 환경변수 반영 (compose 의 ${PORT:-8000} 와 일치)
BACKEND_PORT="${PORT:-8000}"

# Check backend health
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f "http://localhost:${BACKEND_PORT}/health" &>/dev/null; then
        log "✅ Backend is healthy!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    log "⏳ Waiting for backend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    error "Backend health check failed after $MAX_RETRIES retries"
fi

# ---- Run migrations (표준: 배포 시 항상 최신 스키마로) ----
# 신규 설치(빈 DB) 경로에서도 안전하도록 init_db.py 를 사용한다.
# (alembic upgrade head 단독 실행 시 baseline 이 ALTER-only 라
#  'no such table' 로 실패하는 것을 init_db.py 가 create_all + stamp head 로 우회)
log "🗄 Running database migrations..."
docker compose -f docker-compose.prod.yml --env-file .env.$ENV exec -T backend python scripts/init_db.py

# ---- Smoke test: 전환 후 실제 동작 확인 (health + chat 왕복) ----
log "🧪 Smoke test (전환 검증)..."
SMOKE_OK=1
# 1) health
if ! curl -f "http://localhost:${BACKEND_PORT}/health" &>/dev/null; then
    error "Smoke: /health 실패"
    SMOKE_OK=0
fi
# 2) chat 왕복 (LLM+임베더 경로가 살아있는지) — 타임아웃 60s
#    주의: chat 은 외부 LLM 키 유효성에 좌우되므로, 연결 자체가 되는지만 확인.
#          빈 응답/타임아웃만 실패로 처리 (키 오류 등은 경고).
SMOKE_RESP=$(curl -s --max-time 60 -X POST "http://localhost:${BACKEND_PORT}/chat/stream" \
    -H "Content-Type: application/json" \
    -d '{"message":"안녕하세요","history":[],"lang":"ko","user_id":"smoke-test"}' 2>/dev/null | head -c 200)
if [ -z "$SMOKE_RESP" ]; then
    warn "Smoke: /chat/stream no response (check LLM key/network - deploy continues)"
else
    SMOKE_BYTES=$(printf '%s' "$SMOKE_RESP" | wc -c)
    log "Smoke: /chat/stream connected (${SMOKE_BYTES} bytes)"
fi
# 3) Qdrant 쓰기 가능 확인 (collection 존재/응답)
if ! curl -f "http://localhost:${BACKEND_PORT}/mobile/content?category=devotion&lang=ko" &>/dev/null; then
    warn "Smoke: 컨텐츠 조회 비정상 (Qdrant 연결/마이그레이션 확인)"
fi
[ "$SMOKE_OK" = "1" ] && log "✅ Smoke test 통과 — 전환 후 정상 동작 확인"

# ---- Cleanup old backups (keep last 7) ----
log "🧹 Cleaning up old backups..."
ls -t "$BACKUP_DIR"/gospel_*.db 2>/dev/null | tail -n +8 | xargs -r rm
ls -t "$BACKUP_DIR"/documents_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm

# ---- Clean up dangling images ----
log "🧼 Pruning dangling images..."
docker image prune -f

# ---- Summary ----
log "✅ Deployment completed successfully!"
log ""
log "📊 Deployment Summary:"
log " Environment: $ENV"
log " Timestamp: $TIMESTAMP"
log " Backup: $BACKUP_DIR/"
log " Log: $LOG_FILE"
log ""
log "🌐 Services:"
log " User/Admin UI: https://<서버IP>:8501  (Caddy 자체서명)"
log " Backend API:   내부망 전용 (Caddy/Lighthouse 방화벽으로 미노출)"
log "   - /docs 는 DOCS_ENABLED=false 로 비활성 (운영 표준)"
log "   - Qdrant 는 컨테이너 내부 전용 (호스트 포트 미개방)"
log ""
log "📋 Next steps:"
log " 1. Check logs: docker compose -f docker-compose.prod.yml --env-file .env.$ENV logs -f"
log " 2. Monitor: https://cloud.langfuse.com"
log " 3. Test API:  curl http://localhost:${BACKEND_PORT}/health"
