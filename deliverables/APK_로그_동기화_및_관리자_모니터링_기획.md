# APK 로그 서버 동기화 & 관리자 모니터링 — 구현 기획서

> 작성일: 2026-08-14
> 상태: **기획(미구현)** — 현 코드베이스에는 클라이언트 활동 로깅/수신/관리자 모니터링이 전혀 없음.
> 목적: APK(및 모바일 PWA)에서 발생하는 사용자 활동(시청·검색·annotate·클릭·세션·에러)을 서버로 동기화하고, 관리자 UI에서 "유저가 뭘 봤고 뭘 했는지" 모니터링하는 파이프라인을 구축한다.

---

## 0. 현황 체크 (구현 여부)

| 계층 | 항목 | 상태 | 증거 |
|---|---|---|---|
| 클라이언트 | 활동 이벤트 캡처 | ❌ 없음 | `mobile/` grep: `analytics|trackEvent|logEvent|telemetry|beacon|activity_log|session start` → 전부 false positive (`player.js`의 `emit('track')`는 UI pub/sub, 네트워크 미전송) |
| 클라이언트 | 오프라인 이벤트 큐 | ❌ 없음 | `IndexedDB`(`offline.js`)는 오디오 blob 캐시만, `localStorage`는 prefs만. 로그용 buffer 0 |
| 클라이언트 | 이벤트 전송 엔드포인트 호출 | ❌ 없음 | `/events|/logs|/activity|/telemetry|/traces` 호출 0건 |
| 백엔드 | 이벤트 수신 라우터 | ❌ 없음 | `backend/app/api/`에 `events.py`/`analytics.py`/`activity.py` 없음. 유일한 POST는 `/feedback`(챗 평가) |
| 백엔드 | 활동 이벤트 ORM 모델 | ❌ 없음 | `orm.py`에 `ActivityEvent` 등 부재. 존재: `Interaction`(챗), `AuditLog`(관리자 감사), `AppErrorLog`(서버 에러) |
| 백엔드 | 트레이스 싱크 | △ 부분 | `services/tracing.py`의 `_LocalTraceClient`가 `logs/traces.jsonl`에 JSONL 기록 — **단, 서버 LLM 트레이스 전용**, 클라이언트와 무관, admin도 안 읽음 |
| 관리자 UI | 활동/시청 모니터링 페이지 | ❌ 없음 | `admin/pages/` 중 해당 페이지 0. (챗기록 `5_💭_대화기록.py`, 유저관리 `9_👥_유저관리.py`, 서버에러 `4_📊_Status.py`, 챗파생 `20_📊_백데이터분석.py`만 존재) |
| 인증 | 사용자/관리자 구분 | ✅ 있음 | `get_current_user`(HMAC 토큰, 사용자) / `check_admin`(공유 `ADMIN_API_KEY`, 관리자) — 신규 엔드포인트 보호에 재사용 |

**결론: 4계층(캡처→전송→수신/저장→관리자 시각화) 전부 신규 구축 필요.**

---

## 1. 목표 & 범위

### In Scope (v1)
1. 모바일(APK/PWA)에서 사용자 활동 이벤트 캡처.
2. 오프라인 내성 큐 + 배치 동기화(서버 전송).
3. 백엔드 수신 엔드포인트 + `ActivityEvent` 저장.
4. 관리자 페이지에서 시청/활동 집계·필터·타임라인 조회.

### Out of Scope (v2+)
- 네이티브 Crashlytics/ANR 리포트 (APK Java 레이어).
- 실시간 라이브 대시보드(WebSocket push).
- A/B 테스트/훅 분석.
- GDPR 삭제 API(데이터 주권 요청 처리) — §7 참고.

---

## 2. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│  APK / Mobile PWA (vanilla JS)                               │
│                                                              │
│  EventService (mobile/services/index.js)                     │
│    ├─ capture(eventType, payload)  → in-memory ring buffer   │
│    ├─ persist → IndexedDB store "gospel_events" (offline)    │
│    └─ flush策略:                                             │
│         • 타이머(30s) • 버퍼≥20건 • visibilitychange(hidden)  │
│         • navigator.sendBeacon (unload 최종 플러시)           │
│              │  POST /mobile/events/batch  (Bearer token)    │
└──────────────┬──────────────────────────────────────────────┘
               │  HTTPS (GOSPEL_API_BASE)
               ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI backend                                             │
│  POST /mobile/events/batch  (get_current_user, optional)     │
│     → asyncio.to_thread(bulk_insert ActivityEvent[])         │
│     → 202 Accepted (즉시 반환, 비동기 저장)                   │
│  GET  /admin/activity/*      (check_admin)                   │
│     → 집계/조회 (ActivityEvent 기반)                         │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
        ┌──────────────┐        ┌──────────────────────────┐
        │ SQLite/PG    │        │ admin UI (Streamlit)       │
        │ activity_    │◄───────│ 21_📡_활동모니터링.py       │
        │ event 테이블 │        │  집계차트 + 이벤트 테이블   │
        └──────────────┘        └──────────────────────────┘
```

---

## 3. 이벤트 분류(Taxonomy) & 스키마

### 3.1 event_type 목록
| 타입 | 의미 | payload 주요 필드 | 우선순위 |
|---|---|---|---|
| `session_start` | 앱 실행/포그라운드 진입 | `screen`, `app_version`, `platform` | P0 |
| `session_end` | 백그라운드/종료 | `duration_sec` | P0 |
| `page_view` | 화면 이동 | `screen`(home/sermon/bible/hymn/chat/mypage/…) | P0 |
| `media_play_start` | 설교/찬양 재생 시작 | `media_id`, `media_type`(sermon/hymn/devotion), `category` | P0 |
| `media_play_progress` | 재생 진행(25/50/75%) | `media_id`, `position_sec`, `duration_sec`, `progress_pct` | P1 |
| `media_play_complete` | 재생 완료(≥90%) | `media_id`, `duration_sec` | P0 |
| `search` | 검색 실행 | `query`, `facet`(bible/sermon), `result_count` | P0 |
| `verse_annotation_create/update/delete` | 성경 avoir | `book`, `chapter`, `verse`, `kind`(highlight/bookmark/note) | P1 |
| `share` | 공유 | `content_type`, `content_id`, `channel` | P1 |
| `chat_send` | 챗 전송(타임라인 통합용) | `interaction_id`(참조) | P2(선택) |
| `js_error` | 클라이언트 에러 비콘 | `message`, `stack`, `screen`, `app_version` | P1 |
| `button_click` | 주요 CTA 클릭(노이즈 주의) | `screen`, `element_id` | P2(선택/제한적) |

> "유저가 뭘 봤는지" = `media_play_*` + `page_view`(sermon 화면).
> "뭘 했는지" = `search` + `verse_annotation_*` + `share` + `chat_send`.

### 3.2 공통 envelope(클라이언트→서버)
```json
{
  "device_id": "uuid (익명/게스트 식별)",
  "subscriber_id": "sub_xxx (로그인 시만, 미로그인은 null)",
  "session_id": "uuid (앱 세션 고유)",
  "platform": "android | web | ios",
  "app_version": "1.4.2",
  "events": [
    {
      "event_type": "media_play_complete",
      "ts": 1723600000.123,
      "payload": { "media_id": "sermon_123", "media_type": "sermon", "category": "主日讲道", "duration_sec": 1840 }
    }
  ]
}
```
- 서버에서 `event_id`(uuid)·`created_at`(UTC) 자동 부여.
- `event_type`은 서버 allowlist 검증 → 미지정/알수없음은 silently drop(보안/용량).
- 단건 payload 크기 ≤ 4KB, 배치 ≤ 200건 초과 시 413.

---

## 4. 클라이언트 구현 (mobile)

### 4.1 EventService 추가 (`mobile/services/index.js`)
기존 패턴 재사용: `API_BASE`, `AppState.authHeaders()`, `fetch(POST)` (AnnotationService.save 모방).

```js
const EVENT_BUFFER = [];          // in-memory ring
const EVENT_FLUSH_MS = 30000;
const EVENT_FLUSH_COUNT = 20;
let _eventTimer = null;

const EventService = {
  _deviceId() {
    // 기존 guest uuid 재사용 (state.js: gospel_guest_uuid)
    let id = AppState.get('guest_uuid');
    if (!id) { id = crypto.randomUUID(); AppState.set('guest_uuid', id); }
    return id;
  },
  capture(event_type, payload = {}) {
    EVENT_BUFFER.push({
      event_type,
      ts: Date.now() / 1000,
      payload,
    });
    if (EVENT_BUFFER.length >= EVENT_FLUSH_COUNT) this.flush();
    else this._ensureTimer();
  },
  _ensureTimer() {
    if (_eventTimer) return;
    _eventTimer = setTimeout(() => this.flush(), EVENT_FLUSH_MS);
  },
  async flush() {
    if (_eventTimer) { clearTimeout(_eventTimer); _eventTimer = null; }
    if (!EVENT_BUFFER.length) return;
    const batch = EVENT_BUFFER.splice(0, 200);
    const body = {
      device_id: this._deviceId(),
      subscriber_id: AppState.get('subscriber_id') || null,
      session_id: AppState.get('session_id'),
      platform: window.CAPACITOR ? 'android' : 'web',
      app_version: window.APP_VERSION || 'unknown',
      events: batch,
    };
    try {
      await fetch(`${API_BASE}/mobile/events/batch`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, AppState.authHeaders()),
        body: JSON.stringify(body),
        keepalive: true,           // unload 시에도 전송 보장
      });
    } catch (e) {
      // 실패 시 버퍼 복원(뒤에 재시도) - IndexedDB 영속 권장(§4.3)
      EVENT_BUFFER.unshift(...batch);
    }
  },
};
```

### 4.2 캡처 지점(instrumentation) — `mobile/screens/*.js` & `app.js`
- **세션**: `app.js` 부팅 시 `EventService.capture('session_start', {screen})`; `document visibilitychange`(hidden) → `session_end` + `flush()`.
- **화면 이동**: `renderScreen(tabId)` 라우터 훅에서 `page_view`(현재는 `app.js:323` SCREENS 맵).
- **미디어**: `player.js`의 `emit('track'/'play')` 구독 → `media_play_start/progress/complete` 매핑(`progress`는 25/50/75% 임계 시 1회).
- **검색**: `mobile/screens/bible.js` 검색 핸들러에서 `search`(query, facet, result_count).
- **annotate**: `screens/index.js` verse sheet 저장/삭제에서 `verse_annotation_*`.
- **공유**: share 핸들러에서 `share`.
- **에러**: `window.addEventListener('error'/'unhandledrejection')` → `js_error`(1회/세션 throttle).

### 4.3 오프라인 내성(IndexedDB) — `utils/offline.js` 확장
오디오 blob 캐시와 동일한 `gospel_offline` DB에 `events` store 추가:
- `flush()` 전송 직전까지 IndexedDB에 pending 저장 → 네트워크 단절/앱 크래시에도 유실 방지.
- 전송 성공 시 해당 레코드 삭제. (v1에서는 in-memory + `keepalive`로 시작, IndexedDB는 v1.1 권장.)

### 4.4 익명/게스트 → 로그인 병합
- 모든 이벤트는 `device_id` 포함. 로그인 시 `subscriber_id` 채워 재전송.
- 로그인 직후 `EventService.capture('identify', {device_id, subscriber_id})` 1회 → 서버가 미로그인 이벤트를 해당 subscriber로 백필(optional). 기존 history/annotation pull-merge(`services/index.js:1004`)와 동일 철학.

---

## 5. 백엔드 구현

### 5.1 ORM 모델 — `backend/app/models/orm.py` 추가
기존 `_uuid()`/`_now()` 헬퍼(`orm.py:39-44`)와 `Interaction` 패턴(`orm.py:354`) 준수.

```python
class ActivityEvent(Base):
    __tablename__ = "activity_event"

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    subscriber_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True)          # 미로그인은 null + device_id
    device_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    platform: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    __table_args__ = (
        Index("ix_activity_sub_type", "subscriber_id", "event_type"),
        Index("ix_activity_created_type", "created_at", "event_type"),
    )
```

### 5.2 라우터 — `backend/app/api/events.py` (신규 파일)
두 라우터를 한 파일에: 클라이언트 수신(`/mobile/events`) + 관리자 조회(`/admin/activity`).

```python
from fastapi import APIRouter, Depends, Body, Query, HTTPException
from pydantic import BaseModel, Field
from .auth import get_current_user, _check_admin
from ..db import get_session
from ..models.orm import ActivityEvent
import asyncio, uuid, time

ALLOWED_TYPES = {
    "session_start","session_end","page_view","media_play_start",
    "media_play_progress","media_play_complete","search",
    "verse_annotation_create","verse_annotation_update","verse_annotation_delete",
    "share","chat_send","js_error","button_click","identify",
}

mobile_router = APIRouter(prefix="/mobile/events", tags=["mobile-events"])

class ClientEvent(BaseModel):
    event_type: str
    ts: float
    payload: dict = Field(default_factory=dict)

class EventBatchIn(BaseModel):
    device_id: str | None = None
    subscriber_id: str | None = None
    session_id: str | None = None
    platform: str | None = None
    app_version: str | None = None
    events: list[ClientEvent] = Field(..., max_length=200)

@mobile_router.post("/batch")
async def ingest_events(
    batch: EventBatchIn,
    sub_id: str | None = Depends(get_current_user),   # 선택적(게스트 허용)
):
    # 서버 신뢰 식별자로 덮어쓰기(스푸핑 방지)
    owner = sub_id or batch.subscriber_id
    rows = []
    for ev in batch.events:
        if ev.event_type not in ALLOWED_TYPES:
            continue
        rows.append(ActivityEvent(
            subscriber_id=owner,
            device_id=batch.device_id,
            session_id=batch.session_id,
            event_type=ev.event_type,
            platform=batch.platform,
            app_version=batch.app_version,
            payload=ev.payload,
        ))
    if not rows:
        return {"accepted": 0}
    # 비동기 저장 → 즉시 202 반환(로깅이 메인 플로우 지연 금지)
    await asyncio.to_thread(_bulk_insert, rows)
    return {"accepted": len(rows)}

def _bulk_insert(rows):
    with get_session() as s:
        s.bulk_save_objects(rows)
        # get_session() 컨텍스트 종료 시 auto-commit
```

> 성능 핵심: `asyncio.to_thread`로 동기 DB write를 이벤트 루프 밖으로 빼내 채팅/스트리밍 지연 차단 방지. (SYSTEM.md §15.5 성능 하드닝 방침과 일치.)

### 5.3 관리자 조회 — 동일 파일 `admin_router`
```python
admin_router = APIRouter(prefix="/admin/activity", dependencies=[Depends(_check_admin)])

@admin_router.get("/summary")
def activity_summary(days: int = 30):
    # DAU/WAU/MAU, event_type별 건수, top media(시청수·완료율), top search query
    ...

@admin_router.get("/events")
def list_events(
    event_type: str | None = None,
    subscriber_id: str | None = None,
    media_id: str | None = None,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = 100, offset: int = 0,
):
    ...

@admin_router.get("/user/{subscriber_id}")
def user_timeline(subscriber_id: str, limit: int = 200):
    # 해당 유저의 시청/활동 타임라인(챗은 Interaction 조인)
    ...
```

### 5.4 등록 — `backend/app/main.py`
`mobile_router`, `admin_router`를 `app.include_router(...)`에 추가 (±`admin.py` 등록부 근처, `main.py:324-347`).

### 5.5 마이그레이션 (Alembic)
- 신규 단일 테이블 추가이므로 드리프트 리스크 최소. `alembic revision --autogenerate -m "add activity_event"` → `alembic upgrade head`.
- 운영 DB는 `alembic stamp head`로 정렬 후 upgrade(working memory의 Alembic 드리프트 권고 준수). `create_all` 폴백(`db.py:190`)도 신규 테이블은 안전하게 생성.

### 5.6 보관/정리(Retention)
- `activity_event`는 누적량 큼 → 보관 90~180일 후 배치 삭제 스케줄러(기존 `trending_scheduler.py` 패턴 재사용) 권장. SQLite 기본이므로 월별 파티션은 v2(Postgres 전환 시).

---

## 6. 관리자 모니터링 UI

### 6.1 신규 페이지 — `admin/pages/21_📡_활동모니터링.py`
기존 `20_📊_백데이터분석.py` 패턴 모방(Streamlit + `api_client` 호출).
- **상단 KPI**: DAU/WAU/MAU, 총 이벤트, 활성 세션.
- **차트**: event_type별 건수(bar), 일별 활성 유저(line).
- **시청 섹션**: media_type별 시청수·완료율, Top 20 콘텐츠(media_id·제목·시청수·완료율).
- **검색 섹션**: 인기 검색어 Top N.
- **이벤트 테이블**: 필터(기간/event_type/subscriber_id/media_id) + 페이지네이션.
- **유저 타임라인**: subscriber_id 입력 → 해당 유저 시청/활동 내역.

### 6.2 api_client 함수 — `admin/lib/api_client.py` 추가
```python
@safe_api_call
def get_activity_summary(days: int = 30) -> dict:
    r = httpx.get(f"{API_BASE}/admin/activity/summary?days={days}",
                  headers=_headers(admin=True), timeout=30)
    return r.json() if r.status_code == 200 else None

@safe_api_call
def get_activity_events(**params) -> list:
    r = httpx.get(f"{API_BASE}/admin/activity/events",
                  params=params, headers=_headers(admin=True), timeout=30)
    return r.json() if r.status_code == 200 else []
```

---

## 7. 프라이버시 / 컴플라이언스
- 수집은 **행동 메타데이터**만(화면·미디어ID·검색어·에러). 채팅 본문은 `Interaction`에 이미 있음 — `chat_send`는 참조 ID만.
- 쿠키/개인정보 처리방침(`/mobile/legal` 존재)에 "이용 통계 수집" 항목 추가 고지.
- `device_id`는 익명 UUID(PII 아님) — 단, 로그인 시 subscriber와 연결되므로 주권 요청 시 함께 삭제하는 v2 API 필요(§1 Out of Scope).
- 서버 식별자(`subscriber_id`)는 클라이언트 값을 신뢰하지 않고 `get_current_user`로 재검증(§5.2).

---

## 8. APK / Capacitor 특이사항
- APK는 PWA를 WebView로 감싼 것 → JS `EventService`가 그대로 동작(네이티브 추가 코드 불필요).
- API 도메인은 빌드 시 `window.GOSPEL_API_BASE`(index.html `?api=` 제거됨, SSRF 방지)로 베이크 → 이벤트도 동일 base로 전송. `.env.mobile`의 APK 도메인만 맞추면 됨(현재 `127.0.0.1:8000` 하드코딩 — 배포 전 도메인 교체 필요, 별개 blocker).
- 오프라인: WebView도 IndexedDB/`keepalive` 사용 가능 → §4.3 큐로 커버.
- 네이티브 크래시 리포트는 v2(Java `MediaPlaybackService` 레이어에 Sentry/Crashlytics 추가) 권장.

---

## 9. 구현 단계 (체크리스트)

**Phase A — 백엔드 기반 (≈1일)**
- [ ] `orm.py`에 `ActivityEvent` 모델 추가
- [ ] Alembic revision 생성 + `upgrade head`(운영은 stamp 후 upgrade)
- [ ] `api/events.py` 작성(수신 + 관리자 조회)
- [ ] `main.py` 라우터 등록
- [ ] curl/Postman로 `POST /mobile/events/batch` + `GET /admin/activity/summary` 검증

**Phase B — 클라이언트 캡처 (≈1일)**
- [ ] `services/index.js`에 `EventService` 추가
- [ ] `app.js`(세션/화면이동), `player.js`(미디어), `bible.js`(검색), `screens/index.js`(annotate/share), 전역 에러 리스너 계측
- [ ] `node --check` + 정적 서버(:4174)에서 실제 이벤트 전송 확인
- [ ] IndexedDB pending 큐(§4.3, v1.1)

**Phase C — 관리자 UI (≈0.5일)**
- [ ] `api_client.py` 함수 2개 추가
- [ ] `21_📡_활동모니터링.py` 페이지 작성
- [ ] Streamlit(8501)에서 KPI/차트/테이블/타임라인 동작 확인

**Phase D — 통합 & 문서 (≈0.5일)**
- [ ] E2E: APK(또는 PWA) → 이벤트 전송 → DB 저장 → 관리자 페이지 노출 확인
- [ ] Retention 스케줄러(선택)
- [ ] `SYSTEM.md` §5(서비스), §9(모델), §10(엔드포인트), §11(모바일/관리자) 신규 섹션 반영
- [ ] `.env.mobile` APK 도메인 blocker 정리 안내

---

## 10. SYSTEM.md 반영 위치 (구현 시)
- §5 서비스 목록: `events.py`(EventService 백엔드) 추가
- §9.3 ORM 모델: `ActivityEvent` 추가(~26개 모델로 갱신)
- §10 API: `POST /mobile/events/batch`, `GET /admin/activity/{summary,events,user/{id}}` 추가
- §11.3 모바일: `EventService`, 캡처 지점, 오프라인 큐 기술
- §11 관리자: `21_📡_활동모니터링.py` 페이지 기술
- §15.5 성능: 비동기 이벤트 수신(`asyncio.to_thread`) 항목 추가

---

## 11. 리스크 & 고려사항
| 리스크 | 대응 |
|---|---|
| 이벤트 볼륨 폭증 → DB 부하 | 배치 수신 + 비동기 저장 + 인덱스 + retention |
| 클라이언트 스푸핑(가짜 이벤트) | 서버 식별자 재검증, `event_type` allowlist, payload 크기/배치 캡 |
| 게스트→로그인 귀속 누락 | `device_id` + `identify` 이벤트 백필 |
| APK 도메인 하드코딩(별개 blocker) | `.env.mobile` 배포 도메인 교체 필요(이 기획과 무관, 선행 권장) |
| SQLite 동시쓰기 | 현재 단일 프로세스 embedded Qdrant 락 규칙과 유사하게, 이벤트 write는 가벼워 영향 미미 |
