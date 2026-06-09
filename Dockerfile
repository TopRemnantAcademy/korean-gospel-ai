# ─── Korean Gospel RAG — Production Dockerfile ──────────────────────────────
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
COPY app.py .
COPY admin ./admin
COPY user ./user
COPY data ./data
COPY alembic.ini .

# ── 데이터 디렉토리 (Railway Volume 마운트 대상: /data) ────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data/documents \
    DB_PATH=/data/gospel.db

RUN mkdir -p /data/documents /data/uploads

EXPOSE 8000

# uvicorn: workers=1 (Railway 단일 인스턴스 기본)
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
