#!/bin/bash
# =========================================================
# Korean Gospel AI - Production Deployment Script
# =========================================================
# Usage:
#   ./deploy.sh [staging|production]
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

# ---- Pull latest code ----
log "📥 Pulling latest code..."
git pull origin main

# ---- Build Docker images ----
log "🏗️  Building Docker images..."
docker compose -f docker-compose.prod.yml build

# ---- Stop existing containers ----
log "🛑 Stopping existing containers..."
docker compose -f docker-compose.prod.yml --env-file .env.$ENV down || true

# ---- Start new containers ----
log "▶️  Starting new containers..."
docker compose -f docker-compose.prod.yml --env-file .env.$ENV up -d

# ---- Wait for health checks ----
log "⏱️  Waiting for services to be healthy..."
sleep 10

# Check backend health
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f http://localhost:8000/health &>/dev/null; then
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

# ---- Run migrations (if any) ----
log "🗄  Running database migrations..."
# Add migration commands here if needed
# docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# ---- Cleanup old backups (keep last 7) ----
log "🧹 Cleaning up old backups..."
ls -t "$BACKUP_DIR"/gospel_*.db 2>/dev/null | tail -n +8 | xargs -r rm
ls -t "$BACKUP_DIR"/documents_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm

# ---- Summary ----
log "✅ Deployment completed successfully!"
log ""
log "📊 Deployment Summary:"
log "  Environment: $ENV"
log "  Timestamp: $TIMESTAMP"
log "  Backup: $BACKUP_DIR/"
log "  Log: $LOG_FILE"
log ""
log "🌐 Services:"
log "  Backend API:  http://localhost:8000"
log "  API Docs:    http://localhost:8000/docs"
log "  User UI:     http://localhost:8501"
log "  Admin UI:    http://localhost:8502"
log "  Qdrant:      http://localhost:6333/dashboard"
log ""
log "📋 Next steps:"
log "  1. Check logs: docker compose -f docker-compose.prod.yml logs -f"
log "  2. Monitor:   https://cloud.langfuse.com"
log "  3. Test API:   curl http://localhost:8000/health"
