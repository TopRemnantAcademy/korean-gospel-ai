# 미디어(찬양/설교) 업로드 → 폰 PUSH 동기화 설계 (정밀 기획)

> 날짜: 2026-07-29
> 상태: 코드 구현 완료 + 치명적 버그 4건 수정 완료
> 대상: 관리자(8502) 업로드 → 교우 폰 앱(모바일 PWA) 알림

---

## 1. 핵심 원칙: 이중 레이어 (Push = 알림 ping, Data = 열 때 pull)

| 레이어 | 역할 | 데이터 이동? | 실패 시 |
|--------|------|-------------|---------|
| **Push (Web Push)** | "새 찬양/설교가 올라왔어요" 알림만 | ❌ (본문/오디오 아님) | 괜찮음 — 아래 안전망 |
| **Pull (앱 열 때 GET)** | 실제 카탈로그/오디오 다운로드 | ✅ | 없음 |

- **알림을 받지 못해도**, 앱을 열면 최신 카탈로그를 항상 pull → **데이터 유실 없음**(안전망).
- 알림은 "다시 들어오세요"라는 재방문 유도일 뿐, 데이터 전달 채널이 아님.

## 2. 데이터 모델 (`MediaAsset`)

| 컬럼 | 타입 | 의미 | 누가 씀 |
|------|------|------|---------|
| `active` | bool | 앱에 공개되는지 (False면 카탈로그 비노출) | 업로드/스케줄러 |
| `publish_at` | datetime(UTC, naive) | 예약 발행 시각. 도래 시 `active=True`로 자동 전환 | 업로드/스케줄러 |
| `notify_at` | datetime(UTC, naive) | 알림 발송 예정 시각 | 업로드/스케줄러 |
| `notified_at` | datetime(UTC, naive) | 알림 발송 완료 시각. **중복 발송 방지 키** | 스케줄러 |

> ⚠️ 모든 시각은 **UTC(naive)** 로 저장. SQLite 비교 정합성을 위해 tz 정보는 저장 전 제거(`astimezone(UTC).replace(tzinfo=None)`).
> KST = UTC+9. 관리자 입력은 KST로 받고 백엔드에서 UTC로 변환.

## 3. 업로드 플로우 (관리자 8502)

```
관리자 폼
 ├─ 파일(찬양/설교 오디오)
 ├─ 제목 / 아티스트 / 성경구절
 ├─ [앱에 공개] 체크박스      ← 즉시 공개 여부
 ├─ [예약 발행] date + time   ← 비우면 즉시
 └─ 알림 모드 (radio 3택1)
      ① 즉시  : 업로드/발행 직후 ~60초 내 1회
      ② 저녁 배치 : 다음 21:00 KST 에 여러 건을 한 번에 묶어 1회
      ③ 안 보냄 : 알림 없음(공개만)
        │
        ▼
 MediaService.save_upload(...)
   ├─ publish_at 해석 (KST→UTC)
   ├─ is_scheduled = publish_at > now
   ├─ effective_active = False if is_scheduled else active  ← 예약이면 숨김
   ├─ notify_at 결정 (아래 표)
   └─ tz 제거 후 저장
        │
        ▼
  스케줄러(60초 tick)가 publish_at/notify_at 도래를 감지
```

### 알림 시각 결정 로직 (수정 완료)

| 상황 | 알림 모드 | `notify_at` | 비고 |
|------|-----------|-------------|------|
| 즉시 공개 | immediate | `now` | ~60초 내 발송 |
| 즉시 공개 | batch | 다음 21:00 KST | 오늘 21시 지났으면 내일 |
| 즉시 공개 | none | `None` | 알림 없음 |
| **예약 발행** | immediate | `publish_at` | 발행 시각에 알림 |
| **예약 발행** | batch | `다음 21:00 KST (publish_at 기준)` | **발행 이후 저녁** (수정 핵심) |
| **예약 발행** | none | `None` | 알림 없음 |
| 비활성 드래프트(예약无) | 모두 | `None` | 알림 없음 |

> 🐞 **수정 버그**: 기존엔 예약+배치 시 `notify_at = 다음 21:00 KST(현재 기준)` 으로,
> 발행(내일 10시)보다 **이전** 저녁에 알림이 가 콘텐츠가 아직 비활성인데 "새 콘텐츠" 알림이 감.
> → `notify_at = _next_kst_evening(publish_at)` 으로 **발행 이후 저녁** 보장.

## 4. 스케줄러 (`media_publisher.py`, 60초 tick)

```text
tick():
  _publish_due()   # publish_at <= now 이고 active=False → active=True (+updated_at 갱신)
  _notify_due()    # notify_at <= now 이고 notified_at=None 이고 active=True
                  #   → broadcast_media_update(items)
                  #   → 발송 성공 후에만 notified_at 기록
```

보장 사항:
- **active 가드**: 발행 전 콘텐츠는 절대 알림 안 감.
- **발송 후 기록**: 알림 발송이 실패하면 `notified_at`을 안 찍어 → 다음 tick에 재시도(유실 방지).
- **묶음 발송**: 한 tick에 여러 건이 due 면 1건의 한국어 요약 알림으로 통합(스팸 방지).
- **멱등**: `notified_at`이 있으면 재발송 안 함.

## 5. 모바일 구독 플로우 (앱 설치 시 1회)

```
앱 최초 실행 (PushService.setup)
  1. navigator.serviceWorker.register('./sw.js')
  2. Notification.permission 요청 (거부 시 조용히 패스 → pull로만 동작)
  3. GET /mobile/push/vapid  → { public_key }   ← 🐞 수정: 기존 vapidPublicKey 오타
  4. pushManager.subscribe(applicationServerKey = public_key, userVisibleOnly:true)
  5. POST /mobile/push/subscribe { sub_id, token }
       - sub_id = 로그인ID 또는 기기별 guestId(localStorage UUID, 설치마다 고유)
       - 인증 불필요(게스트도 교우 폰 알림 수신해야 하므로)
```

> 🐞 **치명적 버그 수정**: 백엔드가 `public_key` 필드를 주는데 모바일이 `d.vapidPublicKey`를
> 읽어 항상 빈 값 → 구독이 **영원히 등록되지 않아 푸시가 1건도 안 감**. 이게 "문제 있다"의 근본 원인.

## 6. 알림 수신 → 갱신

```
폰에 Push 도착 (sw.js 'push')
  → showNotification("새 찬양/설교가 추가되었어요", tag="new_media" 중복방지)
사용자가 탭 → notificationclick
  → 포그라운드 클라이언트에 postMessage({type:"new_media"})
앱: MediaService.invalidate() → 버전 체크 → 변경 시 전체 카탈로그 pull 재조회
(앱이 이미 열려있어도 visibilitychange 복귀 시 동일 갱신)
```

## 7. 경량 갱신 감지 (`/mobile/media/version`)

- 풀 전체 다운로드 전, `version = "활성개수:최근수정시각"`만 조회.
- 버전이 안 바뀌면 다운로드 스킵(데이터 절약). 바뀌면 해당 카테고리 재조회.
- 오류 시 안전하게 전체 다운로드로 폴백.

## 8. 엣지 케이스 대응표

| 케이스 | 동작 |
|--------|------|
| 알림 권한 거부 | 푸시 안 감. 앱 열 때 pull로 최신 노출(정상) |
| 폰 꺼짐/오프라인 | 벤더 푸시 서비스가 ~4주 보관 후 전달. 그전에 앱 열면 pull로 즉시 반영 |
| 예약 발행 미래 시각 | 발행 전까지 비활성, 도래 시 자동 공개 + 알림 |
| 배치 여러 건 | 21:00 KST 에 1건 요약 알림으로 통합 |
| 발송 실패(VAPID 누락 등) | notified_at 미기록 → 다음 tick 재시도 |
| 게스트(미로그인) 다기기 | 기기별 guestId 로 각각 구독 → 모두 알림 수신 |
| iOS | PWA를 홈화면에 추가(16.4+)해야 웹푸시 동작. 미추가 시 pull만 |

## 9. 환경 전제조건 (실제 폰에서 푸시가 가려면 필수)

1. **HTTPS**: 서비스워커+웹푸시는 `localhost` 또는 HTTPS 에서만 동작. `python -m http.server`(http)는 PC 테스트/개발만 가능, 폰 불가.
2. **API 도달 가능**: 모바일 앱의 `API_BASE`가 폰에서 접근 가능한 공인 HTTPS URL 이어야 함(127.0.0.1 아님).
3. **CORS**: API가 앱 오리진을 허용(이미 `cors_origins` 설정됨).
4. **VAPID 자동생성**: 최초 푸시 호출 시 `.vapid_keys` 자동 생성(.gitignore 포함). `VAPID_SUBJECT` 설정 권장.
5. **스케줄러 기동**: `main.py` lifespan 에서 `media_publisher.start_scheduler()` + `ensure_media_schema()` 호출(이미 배선).
6. **의존성**: `pywebpush`, `apscheduler` venv 설치 필요.

## 10. 검증 계획

- [x] 정적: `node --check`(services/index.js), `py_compile`(media_service, media_publisher) 통과
- [x] 로직: 배치 타이밍 단위 검증 (예약+배치 → 발행 이후 저녁) 통과
- [ ] 통합(런타임): 백엔드 기동 → 즉시 업로드 → 60초 내 알림 발송 로그 확인
- [ ] E2E(실폰): HTTPS 배포 → 앱 설치/권한허용 → 관리자 업로드 → 폰 알림 수신 → 탭 시 갱신
- [ ] 예약: 미래 publish_at + 배치 → 해당 시간에만 알림(발행 전 알림 없음) 확인

## 11. 미해결/추후 (범위 외)

- 알림 카테고리별 구독 선택(찬양만/설교만) — 현재는 전체 브로드캐스트.
- 관리자 화면에 "예약/알림 대기" 상태 표시(현재 미표시).
- iOS 웹푸시는 홈화면 추가 필수 — 앱 내 안내 배너 권장.
