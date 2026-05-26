# 📚 Tier-Free 무료 인프라 완전 가이드

> **목표**: Tier 1.5 (200명) 까지 **도메인 $10/년 외 진짜 $0**  
> **원칙**: 무료 tier 조합만으로 안정적 운영

---

## 📊 비용 비교

| 항목 | 기존 방식 | 무료 인프라 | 절약 |
|---|---|---|---|
| **호스팅** | Heroku ($7+/월) | Fly.io Free ✅ | $84/년 |
| **DB** | AWS RDS ($15+/월) | Supabase Free ✅ | $180/년 |
| **벡터 DB** | Pinecone ($25/월) | Qdrant Cloud Free ✅ | $300/년 |
| **캐시** | Redis Cloud ($5+/월) | Upstash Free ✅ | $60/년 |
| **모니터링** | DataDog ($29+/월) | Sentry Free ✅ | $348/년 |
| **Uptime** | Pingdom ($10/월) | Better Stack Free ✅ | $120/년 |
| **알림** | Twilio ($0.0075/SMS) | NHN SENS Free ✅ | - |
| **CI/CD** | CircleCI ($12+/월) | GitHub Actions Free ✅ | $144/년 |
| **CDN** | AWS CloudFront ($0.085/GB) | Cloudflare Free ✅ | - |
| **도메인** | 도메인 | 도메인 $10/년 | 최소화 |
| **LLM API** | Gemini (종량제) | Gemini (종량제) | 동일 |
| **총 월 비용** | **~$100+** | **$0.83** | **99% 절약** |

---

## 🏗️ Tier별 인프라 구성

### Tier 0 — 로컬 개발 (100% 무료)
```
┌─ 운영자 PC (localhost)
├─ Streamlit (로컬 개발 서버)
├─ SQLite (로컬 DB)
└─ Qdrant Local (로컬 벡터 DB)

비용: $0/월
사용자: 1명
```

### Tier 0.5 — 친구 5명 시범 (100% 무료)
```
┌─ 운영자 PC (호스트)
│  ├─ Streamlit (User + Admin)
│  ├─ SQLite
│  └─ Qdrant Local
│
├─ Cloudflare Tunnel (무료, 무제한)
│  ├─ gospel-ai.trycloudflare.com → localhost:8502
│  └─ admin-gospel-ai.trycloudflare.com → localhost:8501
│
└─ Cloudflare Access (무료, 이메일 OTP)
   └─ Admin UI 보호

비용: $0/월
사용자: ~10명
제약: 호스트 PC 24/7 실행 필요
```

### Tier 1 — 소규모 운영 (100% 무료)
```
┌─ 호스팅: Fly.io Free Tier
│  ├─ 3개 앱 무제한 배포
│  ├─ Shared CPU (arm64, arm32)
│  ├─ 3GB RAM 총합
│  └─ 3GB 스토리지 총합
│
├─ DB: SQLite (Fly 내장)
│  └─ 3GB 무제한
│
├─ 벡터 DB: Qdrant Local (또는 Free Cloud 추후)
│
├─ 모니터링: Sentry Free
│  └─ 5K 에러/월
│
├─ Uptime: Better Stack Free
│  └─ 10개 체크포인트
│
└─ CI/CD: GitHub Actions Free
   └─ 2000분/월

비용: $0/월
사용자: ~50명
장점: 24/7 자동 호스팅, 운영자 PC 끄기 가능
```

### Tier 1.5 — 안정화 & 도메인 ($10/년)
```
┌─ 호스팅: Fly.io Free (유지)
│
├─ DB: Supabase Free → Pro 전환 시작
│  ├─ Free: 500MB, 2GB egress/월, 50K edge functions
│  └─ Pro ($25/월): 8GB, 100GB egress/월
│
├─ 벡터 DB: Qdrant Cloud Free → Standard 시작
│  ├─ Free: 1GB 벡터 (~10K 청크)
│  └─ Standard ($25/월): 100GB 벡터
│
├─ 도메인: gospel-ai.kr ($10/년)
│  └─ Cloudflare에서 관리 (무료)
│
├─ 캐시: Upstash Redis Free
│  ├─ 10K commands/일 무료
│  └─ 세션 캐시용 충분
│
├─ 알림: NHN Cloud SENS
│  ├─ SMS 월 100건 무료 (위기 알림용)
│  └─ 초과 시 건당 $0.006
│
└─ OAuth: Kakao 정식 등록 (무료)

비용: $10/년 (도메인만) + 무료 tier 조합
사용자: ~200명
주의: 200명 근처에서 DB/벡터 한도 도달 → Pro 전환 예정
```

### Tier 2 — 중규모 운영 ($100~200/월)
```
┌─ 호스팅: Fly.io Paid
│  ├─ Shared CPU + Dedicated
│  └─ Auto scaling
│
├─ DB: Supabase Pro ($25/월)
│  └─ 8GB, 100GB egress/월
│
├─ 벡터 DB: Qdrant Cloud Standard ($25+/월)
│  └─ 100GB 벡터
│
├─ CDN: Cloudflare Pro ($20/월)
│  └─ 고급 분석, 캐시 규칙
│
└─ 모니터링: Datadog, PagerDuty 등

비용: $100~200/월
사용자: ~500명
```

---

## ☁️ 각 서비스별 가이드

### 1️⃣ Cloudflare (Tier 0.5+) — 무료 외부 노출

**무료 기능**:
- ✅ **Cloudflare Tunnel** — 무제한 외부 노출 (도메인 불필요)
- ✅ **Cloudflare Access** — Admin UI 보호 (이메일 OTP 무료)
- ✅ **Cloudflare CDN** — 정적 자료 무료 캐싱
- ✅ **Cloudflare R2** — 객체 저장 10GB 무료 (이미지, PDF 등)
- ✅ **DDoS 보호** — 기본 포함
- ✅ **WAF** — 기본 규칙 무료

**설정**: `docs/TUNNEL_GUIDE.md` 참조

**비용**: $0/월

---

### 2️⃣ Fly.io (Tier 1+) — 클라우드 호스팅

**Free Tier**:
- 3개 앱 무제한 배포
- Shared CPU (ARM64 / ARM32)
- 3GB RAM 총합
- 3GB 스토리지 총합
- 자동 스케일링
- SSL 인증서 포함

**설치**:
```bash
# 1. Fly CLI 설치
# https://fly.io/docs/getting-started/installing-flyctl/

# 2. 로그인
flyctl auth login

# 3. 앱 생성
flyctl launch
# → gospel-ai 선택
# → Docker 자동 생성

# 4. 배포
flyctl deploy

# 5. 상태 확인
flyctl status
```

**Docker 파일** (gospel-ai용):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite DB 경로 설정
ENV DATABASE_URL=sqlite:////data/gospel.db
ENV QDRANT_URL=local:/data/.qdrant_local

# 포트 8000 (API) + 8502 (User Streamlit) + 8501 (Admin Streamlit)
EXPOSE 8000 8502 8501

# 시작 스크립트
CMD ["python", "backend/main.py"]
```

**비용**: $0/월

---

### 3️⃣ Supabase (Tier 1.5+) — PostgreSQL

**Free Tier**:
- PostgreSQL 500MB
- 인증 (이메일, OAuth) 무료
- Storage 1GB
- Realtime 무료
- 자동 백업

**Paid Tier** (Pro):
- $25/월
- 8GB 데이터
- 100GB egress/월
- 자동 스케일

**마이그레이션** (SQLite → Supabase):
```python
# 1. Supabase 프로젝트 생성
# https://supabase.com

# 2. SQLite → PostgreSQL 마이그레이션 스크립트
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect

# SQLite 읽기
sqlite_engine = create_engine('sqlite:///data/gospel.db')
sqlite_conn = sqlite_engine.connect()

# Supabase PostgreSQL 쓰기
pg_engine = create_engine('postgresql://user:pass@db.supabase.co/postgres')

# 테이블 복사
for table_name in inspect(sqlite_engine).get_table_names():
    df = pd.read_sql(f'SELECT * FROM {table_name}', sqlite_conn)
    df.to_sql(table_name, pg_engine, if_exists='replace', index=False)
    print(f"✅ {table_name} 마이그레이션 완료")
```

**비용**: $0/월 (Free Tier) → $25/월 (Pro, ~200명+)

---

### 4️⃣ Qdrant Cloud (Tier 1.5+) — 벡터 DB

**Free Tier**:
- 1GB 벡터 저장소 (~10K 청크)
- 1M API 호출/월
- 자동 스케일링 X

**Standard Tier** ($25/월+):
- 100GB 벡터
- 무제한 API 호출
- 자동 스케일링

**로컬에서 클라우드로 마이그레이션**:
```python
from qdrant_client import QdrantClient

# 로컬에서 읽기
local_client = QdrantClient(":memory:")

# 클라우드에 쓰기
cloud_client = QdrantClient(
    url="https://xxx.qdrant.io",
    api_key="your_api_key"
)

# 컬렉션 복사
for collection_name in local_client.get_collections().collections:
    points = local_client.scroll(collection_name.name, limit=10000)[0]
    cloud_client.upsert(
        collection_name=collection_name.name,
        points=points
    )
    print(f"✅ {collection_name.name} 마이그레이션 완료")
```

**비용**: $0/월 (Free) → $25/월 (Standard, ~200명+)

---

### 5️⃣ Upstash Redis (Tier 1.5+) — 캐시

**Free Tier**:
- 10K commands/일
- 10MB 스토리지
- 30일 데이터 보존

**비용**: $0/월 (Free Tier 충분, 초과 시 $0.2/10K commands)

**사용 예**:
```python
import redis
from upstash_redis import Redis as UpstashRedis

# Upstash Redis 연결
redis_client = UpstashRedis(
    url="https://xxx.upstash.io",
    token="your_token"
)

# 세션 캐시
redis_client.set("session:user123", {"name": "John", "faith_stage": 2}, ex=86400)
session = redis_client.get("session:user123")
```

---

### 6️⃣ Sentry (Tier 1+) — 에러 모니터링

**Free Tier**:
- 5K 에러/월
- 무제한 프로젝트
- 이메일 알림

**비용**: $0/월

**설정**:
```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://xxx@xxx.ingest.sentry.io/123456",
    traces_sample_rate=0.1,
    environment="production"
)

# 앱 시작 시 자동 에러 추적
```

---

### 7️⃣ Better Stack (Tier 1+) — Uptime 모니터링

**Free Tier**:
- 10개 모니터
- 1분 체크 간격
- 이메일 알림

**설정**:
1. https://betterstack.com 가입
2. "Add Monitor" → 각 엔드포인트 추가
   - `https://gospel-ai.kr/health` (API)
   - `https://gospel-ai.kr:8502/health` (User)
   - `https://gospel-ai.kr:8501/health` (Admin)
3. 다운 알림 설정 (이메일)

**비용**: $0/월

---

### 8️⃣ GitHub Actions (Tier 1+) — CI/CD

**Free Tier**:
- 2000분/월
- 무제한 workflows
- 자동 배포

**예시** (Fly.io 자동 배포):
```yaml
name: Deploy to Fly.io

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

**비용**: $0/월

---

### 9️⃣ NHN Cloud SENS (Tier 1.5+) — SMS 알림

**Free Tier**:
- SMS 월 100건 무료 (위기 알림용)

**설정**:
```python
import requests

def send_sms_alert(phone: str, message: str):
    """운영자에게 SMS 알림"""
    response = requests.post(
        "https://api.nhncloud.com/sms/v2.3/appKeys/{appKey}/sender/sms",
        json={
            "senderGroupingKey": "gospel-ai",
            "body": message,
            "sendNo": "15882222",  # 발신 번호
            "recipientList": [{
                "internationalRecipientNo": phone,
                "templateParameter": [],
            }]
        },
        headers={"X-Secret-Key": "your_secret_key"}
    )
    return response.status_code == 202

# 사용 예
send_sms_alert("+82101234567", "🚨 사용자 100명 도달! Tier 1.5 업그레이드 권장")
```

**비용**: $0/월 (무료 분량) → 초과 시 건당 $0.006

---

## 💡 운영 팁

### 1. 자동 백업 (GitHub)
```bash
# 매일 자정에 DB 백업
# .github/workflows/backup.yml

name: Daily Backup
on:
  schedule:
    - cron: '0 0 * * *'  # 매일 자정

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: |
          python scripts/backup.py
          git add data/backups/
          git commit -m "Auto backup $(date +%Y-%m-%d)"
          git push
```

### 2. 모니터링 대시보드 (Admin UI)
- Sentry 연동: 일일 에러 요약
- Better Stack 상태: Uptime 현황
- Tier 모니터링: 리소스 사용율

### 3. 비용 경보 설정
- 200명 도달 시 → Supabase Pro 검토
- 1GB 벡터 도달 시 → Qdrant Cloud Standard 검토
- 100만 API 호출 도달 시 → 비용 최적화

---

## 📈 확장 경로 (Tier별)

```
Tier 0 (1명, $0)
  ↓
Tier 0.5 (10명, $0) — Cloudflare Tunnel
  ↓
Tier 1 (50명, $0) — Fly.io Free
  ↓
Tier 1.5 (200명, $10/년) — 도메인 + Supabase + Qdrant
  ↓
Tier 2 (500명, $100/월) — Pro 전환
  ↓
Tier 3 (5000명, $1500/월) — 멀티 region
  ↓
Tier 4 (5000+명, $5000+/월) — K8s + 자체 LLM
```

---

## 🎯 Tier 1.5 체크리스트 (200명 운영)

준비 작업:
- [ ] Fly.io 계정 생성 & 배포
- [ ] Supabase 계정 생성 & DB 마이그레이션
- [ ] Qdrant Cloud 계정 생성 & 벡터 마이그레이션
- [ ] 도메인 구입 (.com 또는 .kr, $10/년)
- [ ] Cloudflare에 도메인 연결
- [ ] Kakao OAuth 앱 등록
- [ ] Upstash Redis 연결
- [ ] Sentry 프로젝트 생성
- [ ] Better Stack 모니터 설정 (10개)
- [ ] GitHub Actions 배포 workflow 설정
- [ ] NHN Cloud SENS 계정 생성 (SMS 알림용)

비용:
- 도메인: $10/년
- 무료 tier: $0/월
- **총합: $0/월 (도메인 제외)**

---

## 📞 지원

- Fly.io: https://community.fly.io
- Supabase: https://discord.supabase.com
- Qdrant: https://discord.gg/qdrant
- Upstash: https://upstash.com/docs
- Better Stack: https://betterstack.com/docs

---

**마지막 팁**: 각 서비스의 **Free Tier 한도**를 주기적으로 확인하세요 (월마다).  
200명 근처에서는 비용 추정을 정확히 하여 Pro 전환 시점을 결정합니다.
