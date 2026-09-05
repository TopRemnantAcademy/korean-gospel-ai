# 로컬 ↔ 클라우드 전환 (随时切换线路)

목표: 운영(클라우드/컨테이너 Qdrant) 과 로컬(embedded, 오프라인) 을 **한 줄로 전환**하고,
전환 후 **자동 검증**으로 조용한降级를 막는다.

## 0. 사전 준비 (최초 1회)
```bash
cp .env.production.template .env.production   # 운영 키 채우기
cp .env.local.template .env.local             # 로컬: Ollama 모델 사전 pull 필요
# 전환 일관성 검증 (신규 env 누락 방지)
python scripts/check_env.py
```

## 1. 전환 명령
| 목적 | 명령 |
|------|------|
| 🌐 운영(클라우드) | `bash deploy.sh production`  ← 내부: `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build` |
| 💻 로컬(오프라인) | `docker compose -f docker-compose.local.yml --env-file .env.local up -d --build` |

## 2. 전환 후 자동 검증 (deploy.sh 가 수행)
- DB 백업: `gospel.db` + `data/documents` + **Qdrant 벡터 + 미디어**(신규)
- Alembic 마이그레이션 자동 적용
- Smoke test: `/health` → `/chat/stream` 왕복 → 컨텐츠 조회
- 모두 통과해야 "전환 완료" 로 간주

## 3. env 일관성 검증 (전환 전 필수)
```bash
python scripts/check_env.py            # .env.production ↔ .env.local BASELINE 30+키 일치
python scripts/check_env.py --strict   # 템플릿 기준 누락 키까지 경고
```
신규 기능 env 를 추가할 땐 **양쪽 프리셋에 모두 넣거나**, 의도적 차이면
`scripts/check_env.py` 의 `EXPECTED_DIFF` 에 등록한다.

## 4. 복구 (전환 실패 시)
백업 위치: `./backups/` (최근 7개 유지)
```bash
# DB 복원
cp backups/gospel_<TS>.db gospel.db
# Qdrant 복원 (운영)
docker compose -f docker-compose.prod.yml --env-file .env.production down
cat backups/qdrant_<TS>.tar.gz | docker compose -f docker-compose.prod.yml --env-file .env.production exec -T qdrant tar xzf - -C /
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

## 5. 주의
- 로컬 모드 LLM 은 Ollama 필요(`ollama pull qwen2.5:7b`). 모델 미설치 시 chat 왕복 실패.
- `QDRANT_URL` 값 차이(운영=http://qdrant:6333 / 로컬=local:./.qdrant_local)는 정상.
- `.env.local` 은 `.gitignore` 에서 무시됨(시크릿 유출 방지).
