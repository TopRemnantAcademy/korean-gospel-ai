# APK 푸시 + 데이터 보호 상세 기획서
**대상**: 홍콩 서버 / 중국 본토 + 글로벌 화교 이용자
**작성일**: 2026-08-16
**전제 가정**: 이용자 = 중국 본토 + 해외 화교. 서버 = 홍콩. 목표 = 브로드캐스트(전체발송) 푸시 + 전송/저장 암호화 + 중국 관할 노출 최소화.

---

## 0. 기존 코드 실태 (검증됨 — 환각 아님)

| 파일 | 현재 상태 | 문제 |
|------|-----------|------|
| `mobile/services/index.js` `PushService` (L91–153) | Web Push API (`navigator.serviceWorker` + `PushManager.subscribe` + VAPID) | **Capacitor Android WebView는 service worker 미지원** → APK에선 `setup()`이 조용히 return. 죽은 코드. |
| `android/app/src/main/AndroidManifest.xml` | `POST_NOTIFICATIONS`, `FOREGROUND_SERVICE`(미디어용)만 존재. 푸시 SDK 0개 | 네이티브 푸시 수신 불가. |
| `capacitor.config.json` | push plugin 미등록, `androidScheme: https` | — |
| `package.json` | `android:config:cn/hk/global/play` 마켓 분기 존재 (`scripts/build-config.js`) | **마켓별 푸시 주입 가능 구조 이미 갖춤** — 활용. |
| `mobile/services/index.js` `API_BASE` (L6) | 기본값 `http://127.0.0.1:8000` | 운영에선 **반드시 HTTPS**로 주입 (`window.GOSPEL_API_BASE`). |

**결론**: 현재 APK는 중국 본토 이용자에게 푸시를 줄 수 없는 상태. 전면 재설계 필요.

---

## 1. 푸시 아키텍처 (중국 본토 대응) — ★FCM 오답 정정

이전 답변에서 "FCM 쓰면 된다"고 했으나 **FCM(Google)은 중국 본토에서 차단**되어 본토 이용자에게 도달하지 않음. 정정.

### 권장: 2-track 하이브리드 (마켓 분기 활용)

```
market=cn  → 시스템 예약 로컬 알림(LocalNotifications) + 주기 동기화   [제3자 0, GFW 무관] ★본토 주력
market=hk/global → FCM 실시간 푸시 (@capacitor/push-notifications)     [중국 외]
market=play → FCM (Google Play 채널)
```

### 1-A. 중국 본토 주력: "시스템 예약 로컬 알림 + HK 폴링"
**핵심 인사이트**: 정기기도/매일 말씀은 **실시간이 아니라 예약 broadcast**. 따라서 제3자 푸시·영속 소켓·GFW 우회가 **전혀 필요 없음**.

동작:
1. 앱이 열릴 때(또는 포그라운드 전환 시) HK 서버 `/mobile/schedule?lang=zh`를 HTTPS로 폴링 → 예약 항목(시각, 제목, 본문, lang) 수신.
2. 수신한 항목을 **`@capacitor/local-notifications`의 `schedule()`로 기기 OS에 등록**.
3. OS가 예약 시각에 **앱이 꺼져 있어도** 시스템 알림 표시 (안드로이드 AlarmManager/WorkManager 기반 — 중국 ROM의 백그라운드 킬 대상 아님).
4. 알림 탭 → 앱 열림 → 해당 콘텐츠 렌더.

장점:
- 제3자 푸시 사업자 개입 0 → **감시 노출 최소화에 가장 유리** (C장 제약과 직결).
- GFW/중국 네트워크 차단과 무관 (단순 HTTPS 폴링).
- 중국 OEM ROM의 백그라운드 킬 영향 안 받음 (OS가 알림 발화).

단점/한계:
- 앱이 한 번도 안 열렸으면 그 주의 예약을 못 받음 → 최초 1회 오픈 필요 (설치 후 첫 실행 시 동기화로 해결).
- 서버에서 **새 broadcast를 발송한 직후** 이용자에게 즉시 알리고 싶으면, 앱 재오픈 때까지 지연 (본토에선 수용). 실시간이 진짜 필요하면 1-B.

### 1-B. 본토 실시간이 필요할 때 (선택) — 중국 푸시 사업자
- **极光(JPush) / 个推(Getui) / 腾讯云推送(TPNS)** 또는 **제조사 푸시(小米/华为HMS/OPPO/vivo)**.
- 본토에서 확실히 도달. **단 이들은 중국 법인·중국 법률 적용 사업자** → "감시 회피" 목표와 **정면 충돌**. 신중 판단 필요.
- 도입 시 `android:config:cn` 빌드에서만 SDK 활성화, FCM 비활성화.

### 1-C. 글로벌 화교 / HK — FCM
- `@capacitor/push-notifications` + 서버 `pyfcm` 발송. 중국 외 지역 + 홍콩에서 정상 동작.
- `android:config:global` / `:hk` / `:play` 빌드에서만 활성화.

---

## 2. 필요 의존성 (git/npm/pip)

### 모바일 (npm)
```bash
npm i @capacitor/local-notifications   # 1-A 본토 주력 (시스템 예약 알림)
npm i @capacitor/push-notifications    # 1-C 글로벌/HK FCM (cn 빌드선 비활성)
# 선택: npm i mqtt   # 1-B 실시간 자체 WebSocket/MQTT 롱커넥션 고도화 시
```
- `capacitor.config.json`의 `plugins`에 market별로 등록 (cn빌드는 push 비활성, local-notifications 활성).

### 백엔드 (pip, venv)
```bash
pip install cryptography      # 앱레벨/필드 암호화
pip install apscheduler       # 정기 broadcast 발송 스케줄러 (또는 celery)
pip install pyfcm             # 글로벌/HK FCM 발송
pip install pysqlcipher3      # 저장 암호화 (또는 서버 디스크 암호화)
```

### 인증서
- HK 서버 도메인용 Let's Encrypt(무료) 또는 상용 DV. HSTS + OCSP 스테이플링.

---

## 3. 데이터 암호화 설계

### 3-1. 전송 중 (in transit) — 필수
- HK 서버 nginx에서 **TLS 1.3** 종료. HTTP/2.
- `API_BASE`를 **HTTPS로만** 주입 (`window.GOSPEL_API_BASE = 'https://api.xxx.hk'`). 현재 L6 기본값 HTTP → 운영 빌드에서 덮어쓰기.
- **인증서 핀닝(Certificate Pinning)**: 안드로이드 `network_security_config.xml` + OkHttp pin, 또는 Capacitor 커스텀. 중국 네트워크에서 가능한 가짜 인증서/MITM 방어.
- HSTS 헤더.

### 3-2. 저장 중 (at rest)
- 서버: SQLite → **SQLCipher** (`pysqlcipher3`), 또는 인스턴스 디스크 LUKS. 키는 본토 외부 시크릿 매니저.
- 모바일: `@capacitor/local-notifications` 일정 외 로컬 민감 저장은 **EncryptedSharedPreferences / Capacitor Secure Storage**(키스토어/Keychain).

### 3-3. 앱 레벨 (제한적)
- 채팅 질의는 **LLM이 평문 필요 → 서버가 봄**. 클라이언트↔서버 E2E는 구조적 불가(이전 설명 유지).
- 민감 메타데이터(이름 등)만 선택적 앱레벨 암호화.

### 3-4. 인증 토큰
- 메모리 전용, 갱신 주기 단축. (이미 P0-14로 128비트 서명 적용됨)

---

## 4. 홍콩 서버 아키텍처

```
[중국 본토 클라이언트] --TLS 1.3--> [HK: nginx(TLS) → FastAPI → DB(SQLCipher)]
                                                    │
                                    [HK: 자체 호스팅 LLM(비중국 오픈모델)]
```
- **DB는 본토 미사용**, 전부 HK.
- **LLM 라우팅**: 클라(본토) → TLS → HK 서버 → (HK가 LLM 호출).
  - LLM을 **비중국 오픈모델 자체 호스팅(HK)** 으로 전환 → 질의 내용이 중국 네트워크/중국 사업자에 **노출되지 않음**.
  - 현재 `LLM_PROVIDER=tencent` 사용 중 → **중국 유출 최대 지점**. 전환 권장 (P4).
  - 단, 본토 클라→HK 구간만 중국 네트워크가 봄. **내용은 암호화**, 메타데이터(IP·접속시각·트래픽량)는 관찰 가능.
- **CDN**: 본토 CDN 사용 자제(법인/감시). HK 또는 글로벌 CDN.

---

## 5. "중국 감시 회피" — 정직한 한계 (★중요, 환각 금지)

### 암호화·자체 아키텍처로 **할 수 있는 것**
- 네트워크 중간자 내용 차단 ✅
- 저장 데이터 유출 방지 ✅
- **제3자 푸시 사업자 개입 제거** (1-A 방식) ✅ → 본토 이용자 데이터가 중국 사업자에 안 감.
- 로그 무민감화·데이터 최소화 ✅

### **못 하는 것** (기술적 한계, 솔직히)
- 본토 이용자가 **중국 네트워크/기기를 쓰는 한**, *누가 언제 HK 서버에 접속하는지(메타데이터)* 는 중국 관찰자에게 보임. 암호화로 가릴 수 없음.
- **홍콩 서버도 「홍콩 국가안보법(NSL)」 적용 대상** → 완전한 회피 아님. 본토보다 관할 노출은 낮지만 0은 아님.
- 중국 법인/본토 인프라를 쓰면 **강제 접근** 가능.
- **GFW 우회(프록시/VPN) 제공은 하지 않음** (법적 위험 + 제공 불가).

### 법적 현실 (기술 밖, 팩트만)
- 중국 내 종교 콘텐츠 온라인 배포는 「互联网宗教信息服务管理办法」(2022 시행) 따라 **허가(许可证) 필요**. 기술로 우회 불가.
- 본 기획은 기술 아키텍처일 뿐, **법적 합규는 별도 법률 자문 대상** (판단 불가).

---

## 6. 속도 영향
| 항목 | 오버헤드 |
|------|----------|
| TLS 1.3 | ~1–3% (무시) |
| 저장 암호화(SQLCipher) | DB 작업 ~5–15% |
| 로컬 알림 예약(1-A) | 오버헤드 미미 (OS가 발화) |
| FCM(1-C) | 즉시성↑, 오버헤드 무시 |
| **LLM 생성** | 지배적 (~78s) — 암호화 영향 0에 가까움 |

→ 사용자 체감 속도는 암호화보다 LLM 응답이 지배. 무시해도 됨.

---

## 7. 구현 단계 (Phase)

**P1. HK 서버 + TLS**
- nginx TLS 1.3 + HSTS, FastAPI 배포, DB SQLCipher 전환.
- `API_BASE` 운영 HTTPS 주입 (build-config.js market별).

**P2. 본토 주력 푸시 (1-A)**
- `@capacitor/local-notifications` 추가, `capacitor.config.json` cn빌드 plugin 등록.
- 백엔드 `/mobile/schedule` 엔드포인트 + broadcast 스케줄 테이블 + `apscheduler` 발송 로직.
- `mobile/services/index.js`: 기존 죽은 `PushService`(Web Push) 제거/치환 → `ScheduleService`(폴링+로컬예약) + `LocalNotifyService`.
- 안드로이드 `AndroidManifest.xml`: `RECEIVE_BOOT_COMPLETED`(재부팅 후 예약 복원) 추가.

**P3. 글로벌/HK FCM (1-C)**
- `@capacitor/push-notifications` + `pyfcm`. global/hk/play 빌드에서만 활성.

**P4. LLM 자체 호스팅 전환**
- tencent → HK 자체 호스팅 비중국 오픈모델. 질의 중국 노출 차단.

**P5. 강화**
- 인증서 핀닝, 데이터 최소화, 로그 무민감화(PII 마스킹), 법률 자문.

---

## 8. 요약 판정
- **전체발송 브로드캐스트**: 1-A(시스템 예약 로컬 알림 + HK 폴링)로 본토 포함 전 시장 커버 가능. 실시간 불필요한 정기 콘텐츠에 최적.
- **암호화**: TLS 1.3 + 저장 암호화 + 인증서 핀닝으로 표준 수준 달성. 속도 영향 무시.
- **감시 회피**: 제3자 푸시 안 쓰는 1-A 구조 + HK 자체 LLM으로 **중국 사업자 노출은 실질적으로 차단** 가능. 단 메타데이터·NSL·법적 허가는 기술로 해결 안 됨 — 한계를 인지하고 운영.
- **기존 FCM 조언는 중국 대상 오답이었음을 정정**.
