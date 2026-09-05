# ───  RAG — Production Dockerfile ──────────────────────────────
# 대상: Railway / Render / Fly.io
# 메모리 최적화: 로컬 ML 모델 없음 → EMBEDDER=hf_inference, RERANKER=none
# Qdrant: 클라우드 모드 (QDRANT_URL=https://xxx.qdrant.tech)
# SQLite:  /data 볼륨 마운트 (Railway: Volumes > /data)
#
# 통합 구조 (2026-06-09):
#   app.py + backend/ 만 복사 (admin/, user/ 는 app.py 가 import)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 의존성 레이어 (소스 변경과 분리해 캐시 활용) ─────────────────────────
COPY requirements-deploy.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── 소스코드 복사 (통합 구조) ────────────────────────────────────────────
COPY backend ./backend
COPY admin ./admin
COPY user ./user
COPY alembic.ini .

# ── 데이터 디렉토리 (compose 가 ./data:/app/data 바인드 마운트) ──────────
# P9-3 (P2): data/ 는 런타임에 볼륨 마운트되므로 이미지에 COPY 하지 않음.
#            (이전 COPY data ./data 는 마운트에 가려지고 이미지에 문서를
#             함께 배포하는 문제가 있어 제거)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data/documents \
    DB_PATH=/app/gospel.db

RUN mkdir -p /app/data/documents /app/data/uploads

EXPOSE 8000

# uvicorn: Caddy 뒤 proxy-headers 필수. workers=2 (4vCPU 박스 안전 상한).
# PORT 환경변수로 오버라이드 가능(Railway/Fly 호환).
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} --proxy-headers --forwarded-allow-ips '*'"]
