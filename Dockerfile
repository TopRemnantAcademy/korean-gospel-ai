FROM python:3.11-slim

# libmagic1 은 문서 타입 파싱 시 활용될 수 있으므로 설치
RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements 의존성 캐시 활용 빌드
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사 (백엔드 및 Streamlit User App 공유 가능하게 복사)
COPY backend ./backend
COPY user ./user
COPY alembic.ini .

EXPOSE 8000

# uvicorn 실행 (0.0.0.0 바인딩 필수)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
