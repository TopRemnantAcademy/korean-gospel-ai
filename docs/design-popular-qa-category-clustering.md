# 인기 질문 "주제 분류·군집" 업그레이드 기술 설계서

> **요약**: 현재 인기 질문 패널은 *질문 1건당 1개 키워드 라벨* + *flat 랭킹 리스트* 구조다.
> 사용자가 원하는 것은 **"비슷한 질문을 한 덩어리(주제)로 묶어, 주제별로 인기 순위를 보여주는 것"**
> (예: 마약/음주/포르노 관련 질문은 모두 '중독 회복' 한 카테고리로 묶임).
> 본 문서는 백엔드 분류기를 **규칙 기반 → AI/의미 군집** 으로 격상하고,
> 프론트를 **flat 리스트 → 카테고리 탭/아코디언** 으로 재구성하는 상세 설계를 다룬다.

---

## 0. 현황 진단 (바꾸는 이유)

### 0.1 백엔드에 이미 있는 것 (재사용 가능)
- `backend/app/services/trending_service.py`
  - `classify_question(q)` → 규칙(키워드) 분류. 라벨: `중독회복/신앙성장/관계회복/정서치유/정체성/소명사명/기타`
  - `normalize_question(q)` → 소문자/공백/조사 제거 + 띄어쓰기 정규화 (동일 질문 병합용)
  - `get_top_questions(limit, lang, category)` → `category` 필터 파라미터 지원, 응답에 `category` 포함
  - `get_realtime_question_ranking(...)` → 실시간 집계, `category` 포함, `normalize` 로 중복 질문 `set` 병합
- `backend/app/models/qatrend.py` → `QATrendSnapshot` (질문 원문, `normalized_question`, `category`, `count`, `lang`, `period` 등)
- `backend/app/api/ranking.py` → `GET /ranking/questions` 가 이미 `category` 반환 + `category` 쿼리 필터 존재
- 시드 JSON (`data/popular_questions_ko.json`, `popular_questions_zh.json`) → 각 질문에 `category` 필드 존재

### 0.2 부족한 것 (이번에 만들 것)
| 항목 | 현재 | 목표 |
|------|------|------|
| 분류 방식 | 규칙 키워드 (신조어·유사표현 → `기타` 로 유실) | **AI 의미 군집** (유사 질문 자동 동일 주제로) |
| 노출 구조 | flat 리스트 (질문 나열) | **주제별 그룹 + 그룹 내 인기 순위** |
| 그룹 대표 질문 | 없음 (개별 질문만) | **주제별 대표 질문 + 해당 주제 총 질문 수** |
| 프론트 UI | 단일 컬럼 리스트 | **카테고리 탭/아코디언 + 그룹 랭킹** |
| 다국어 | ko/zh 카테고리명 분리 유지 | 동일 (라벨만 i18n) |

---

## 1. 핵심 질문에 대한 답: "AI가 모든 유사 질문을 한 곳에 묶을 수 있는가?"

**답: 가능하다. 두 단계로 구현한다.**

1. **정규화(Normalize)** — 표면형 차이 제거
   - "마약 중독怎么会?" / "도박 안 끊어져요" / "술 못 끊겠어요" 는 표면이 다르지만
     `normalize_question` + **임베딩 유사도** 로 "중독" 의미군으로 수렴.
2. **군집(Cluster)** — 의미 거리 기반 그룹핑
   - 질문을 벡터화(embedding) → 코사인 유사도 → 임계값(예 0.78) 이상이면 동일 클러스터
   - 클러스터 = "주제". 대표 질문(가장 자주 묻거나 가장 짧은 것)을 그룹 라벨로.

> 규칙 분류(`classify_question`)는 **1차 안전망**으로 남긴다.
> AI 군집이 실패/지연 시 규칙 라벨로 폴백 → `기타` 로 빠지지 않게.

---

## 2. 백엔드 설계

### 2.1 새로운 서비스: `backend/app/services/question_clusterer.py`

```python
# 의사코드
class QuestionClusterer:
    def __init__(self, embed_fn, cache):
        self.embed = embed_fn          # 기존 AI 레지스트리의 embedding 어댑터 재사용
        self.cache = cache             # Redis: normalized_question -> cluster_id

    def embed_questions(self, questions: list[str]) -> list[list[float]]:
        # 배치 임베딩 (비용 절감). 동일 normalize 문장은 캐시 hit
        ...

    def cluster(self, questions: list[str], threshold=0.78) -> list[Cluster]:
        # 1) embed  2) 상호 코사인 유사도  3) Union-Find 로 연결요소 = 클러스터
        # 4) 각 클러스터 대표 질문 선정 (count 최대 or 길이 최소)
        ...

    def assign_category(self, cluster_repr: str) -> str:
        # 1순위: 규칙 classify_question (즉시, 무료)
        # 2순위: 임베딩 유사도로 기존 클러스터 매핑 (신규 질문이 기존 주제와 같은지)
        ...
```

**클러스터 저장**: `QATrendSnapshot` 에 필드 추가
- `cluster_id: str` (예 `"addiction-마약"`) — 동일 주제 질문 공유
- `cluster_repr: str` — 그룹 대표 질문
- `cluster_size: int` — 이 주제에 속한 질문 수 (집계 시 `count` 합산)

### 2.2 집계 파이프라인 변경 (`trending_service.py`)

```
질문 수집 (실시간 interaction 로그)
   ↓
normalize_question(q)              # 표면 병합
   ↓
embed + cluster()                  # 신규 주제 발견 / 기존 주제 병합
   ↓
assign_category(cluster_repr)      # 규칙 폴백
   ↓
QATrendSnapshot.upsert (cluster_id 기준)
   ↓
get_category_ranking(lang)         # 신규 API: 주제별 그룹 + 그룹 내 랭킹
```

### 2.3 신규/변경 API

`GET /ranking/questions` 확장 (기존 호환):
```
params 추가:
  group=true   → 응답을 카테고리별 그룹 구조로 반환
  flat(false)  → 기존 동작 유지 (모바일 하위 호환)
```

신규 응답 스키마 (`group=true`):
```json
{
  "categories": [
    {
      "category": "중독회복",
      "total_count": 1280,
      "questions": [
        { "cluster_id": "addiction-마약", "cluster_repr": "마약 중독에서 벗어나려면?",
          "count": 540, "normalized": [...] },
        { "cluster_id": "addiction-도박", "cluster_repr": "도박 중독 극복 방법?",
          "count": 410, "normalized": [...] },
        { "cluster_id": "addiction-술",  "cluster_repr": "술 못 끊겠어요",
          "count": 330, "normalized": [...] }
      ]
    },
    { "category": "신앙성장", "total_count": 980, "questions": [ ... ] },
    ...
  ]
}
```

> **중독 회복 카테고리 안에 마약/도박/술이 각각 클러스터로** 들어가는 것이
> 사용자가 말한 "마약은 마약끼리, AI가 비슷한 걸 한 덩어리로" 에 정확히 부합.

### 2.4 비용/성능 통제
- 임베딩은 **배치 + 24h Redis 캐시** (normalize 문장 단위) → 신규 질문만 임베딩
- 군집은 **주기적 배치**(예 10분)로 돌리고 스냅샷 보관, 실시간 요청은 캐시된 스냅샷 서빙
- 규칙 `classify_question` 은 임베딩 0원, 폴백으로 항상 작동

---

## 3. 프론트 설계 (`app.py` 인기 질문 패널)

### 3.1 데이터 페치 변경
```python
def _popular_questions(lang, group=True):
    r = cli.get(f"{API_BASE}/ranking/questions",
                params={"lang": lang, "group": "true", "period": "7d"})
    return r.json().get("categories", [])
```

### 3.2 UI 구조 (우측 패널)
```
┌─ 🔥 인기 질문 (우측 패널) ───────────┐
│ [한국어|中文] 언어 토글               │
│                                        │
│ ▸ 중독회복  (1,280)        ← 아코디언 │
│    #1 마약 중독에서 벗어나려면? (540) │
│    #2 도박 중독 극복 방법?     (410)  │
│    #3 술 못 끊겠어요          (330)   │
│ ▸ 신앙성장    (980)          ← 접힘   │
│ ▸ 정서치유    (760)          ← 접힘   │
│ ...                                  │
└──────────────────────────────────────┘
```
- **아코디언**(expander) 으로 카테고리 펼침/접힘 → 좁은 우측 패널에 다 들어감
- 카테고리 헤더에 `total_count` 배지 → "이 주제가 얼마나 뜨거운지" 직관 표시
- 그룹 내 질문 클릭 → 기존처럼 `st.session_state["_pending_q"]` 에 대표 질문 주입

### 3.3 다국어
- 카테고리명 매핑 테이블 유지 (ko↔zh)
  - `중독회복↔成瘾恢复`, `신앙성장↔信仰成长`, `정서치유↔情绪治愈`, ...
- 클러스터 대표 질문(`cluster_repr`)은 해당 `lang` 스냅샷에서 가져옴 (ko/zh 각각 집계)

---

## 4. 구현 단계 (권장 순서)

| 단계 | 작업 | 산출물 | 리스크 |
|------|------|--------|--------|
| 1 | `QATrendSnapshot` 에 `cluster_id/cluster_repr/cluster_size` 컬럼 추가 + 마이그레이션 | 스키마 | 낮 |
| 2 | `question_clusterer.py` 신규 (embed+Union-Find+규칙 폴백) | 서비스 | 중(임베딩 비용) |
| 3 | `trending_service` 집계 파이프라인에 cluster 통합 | 파이프라인 | 중 |
| 4 | `/ranking/questions?group=true` 응답 스키마 추가 (flat 하위 호환) | API | 낮 |
| 5 | 프론트 `_popular_questions(group=True)` + 아코디언 UI | UI | 낮 |
| 6 | 카테고리 i18n 매핑 보강 (zh 시드와 정렬) | i18n | 낮 |
| 7 | 캐시(24h) + 주기 배치 스케줄러 연결 | 성능 | 중 |

---

## 5. 열려있는 설계 결정 (확정 필요)

1. **임베딩 모델**: 기존 `ai-registry` 의 text-embedding 어댑터 재사용 vs 경량 한국어 특화 모델
2. **유사도 임계값 0.78** 적정치인지 — A/B 로 튜닝 필요 (낮추면 과도하게 뭉침, 높이면 쪼개짐)
3. **클러스터 대표 질문 선정 기준**: 빈도 최대(가장 "대표") vs 길이 최소(가장 "깔끔")
4. **신규 주제 자동 승인 vs 관리자 검수**: `기타` 비중이 낮아지면 자동, 높으면 어드민 승인
5. **모바일 동기화**: 동일 `/ranking/questions?group=true` 로 양쪽 일치 (기존 원칙 유지)

---

## 6. 결론

사용자의 요구("비슷한 질문을 AI가 한 곳으로")는 **규칙 분류기를 의미 군집(embedding+cluster)으로 보강** 하고
**노출을 flat→카테고리 그룹** 으로 바꾸는 것으로 달성 가능하다.
백엔드에 이미 `category` 필드·필터·시드가 있어 **증분 투자** 로 해결되며,
규칙 분류기를 폴백으로 두어 비용/안정성을 확보한다.
