# 모바일 배포 기획서 — 웹(PWA) + 안드로이드(APK) 동시 지원

> **핵심 원칙: 단일 소스(`mobile/`) = 웹 PWA + 안드로이드 APK 두 산출물**
> 코드 포크 금지. 플랫폼 차이는 런타임 분기(`Platform` 유틸)와 빌드 시 API 주입으로 처리.

---

## 1. 아키텍처 개요

```
mobile/                         ← 단일 소스 (웹 + APK 공유)
  ├─ index.html                 ← API 주소 + Google SDK 플레이스홀더 주입 대상(소스는 절대 수정 안 함)
  │                               (__GOSPEL_API_BASE__ / __GOSPEL_GOOGLE_SDK__ / __GOSPEL_PORTONE_SDK__ / __GOSPEL_PAYMENT_CHANNEL__)
  ├─ version.json               ← 단일 버전 소스 { versionName, versionCode } (빌드 시 dist + android/app/build.gradle 로 동기화)
  ├─ app.js                     ← window.Capacitor 가드로 네이티브 호출 분기 (웹은 no-op)
  ├─ services/index.js          ← API_BASE = window.GOSPEL_API_BASE (단일 진입)
  ├─ utils/platform.js          ← isNative() / getPlatform() / callPlugin() 런타임 분기
  ├─ sw.js                      ← Web Push + 오프라인 캐시 (PWA). Google 프레임워크 없으면 자동降级
  ├─ manifest.webmanifest       ← PWA 설치 메타
  ├─ icons/                     ← icon-192.png / icon-512.png / badge.png (푸시용)
  └─ integration/android/       ← APK 전용 네이티브 플러그인 (FontKeyPlugin 등)
  └─ dist/                      ← 빌드 산출물(자동생성, gitignore). dist/web(PWA) · dist/android(APK 자산)

download.html                   ← 루트. APK 다운로드 랜딩페이지(중문, Google Play 미경유). ./releases/flow-ai.apk 참조
releases/                       ← npm run publish:web 가 APK 복사(.apk/.aab 는 gitignore). 직링크 배포 디렉터리
_archive/legacy-web/            ← 구 데스크톱 웹 UI(아카이브, 빌드 대상 아님)

android/                        ← cap add android 로 자동생성 (gitignore 권장)
  ├─ app/src/main/java/com/gospelai/app/  ← FontKeyPlugin 복사본
  └─ app/build.gradle           ← versionCode/versionName 이 mobile/version.json 과 빌드 시 자동 동기화

scripts/
  ├─ build-config.js            ← 웹/안드로이드 빌드: 소스 보존 + mobile/dist/<target>/ 로 출력 + 채널별 appId 분리
  └─ copy-android-plugins.js    ← cap add android 후 네이티브 플러그인 자동 복사
```

### 플랫폼별 동작 매트릭스

| 기능 | 웹(PWA) | 안드로이드(APK) | 처리 방식 |
|------|---------|-----------------|-----------|
| API 호출 | `GOSPEL_API_BASE`=웹도메인 | `GOSPEL_API_BASE`=운영 HTTPS | 빌드 시 주입 (build-config.js) |
| 네이티브(볼륨키→폰트) | 미지원(no-op) | `FontKeyPlugin` 동작 | `Platform.callPlugin()` 가드 |
| 푸시 | Web Push(VAPID) | Web Push + (선택)FCM | `Platform.getPlatform()` 로 구독 분류 |
| 백그라운드 재생 | Media Session API | Media Session + (선택)Foreground | 동일 코드 |
| 오프라인 Bible | `./data/bible/*.json` | 절대경로 fetch (origin 안전) | `services/index.js` 수정됨 |
| 오프라인 캐시 | `sw.js` | `sw.js` (Capacitor 내장) | 동일 |

---

## 2. 사전 요구사항

1. **Node.js 18+**
2. **Android Studio** (Hedgehog 이상) + **JDK 17** (번들) + **Android SDK** Platform 34
3. 백엔드(8000)가 HTTPS 도메인에 배포되어 있어야 함 (APK는 `127.0.0.1` 불가)

---

## 3. 웹(PWA) 빌드/배포

```powershell
cd C:\Desktop\korean-gospel-ai
# API 주소 주입 → 산출물은 mobile/dist/web/ 로 출력(소스 mobile/index.html 은 변경 안 됨)
node scripts/build-config.js web --api=https://api.your-domain.com
# 정적 호스팅 (예: nginx / Cloudflare Pages / app.your-domain.com)
# mobile/dist/web/ 폴더 전체를 HTTPS 정적 호스팅. Service Worker 오프라인 캐시 자동 동작.
```

⚠️ **소스는 절대 수정되지 않음**: `build-config.js` 는 `mobile/index.html` 를 보존한 채
`mobile/dist/web/` 로만 치환본을 출력. 따라서 서버(8000)·PWA(4174)·APK 가 같은 소스를 공유해도
빌드 산출물이 소스를 덮어쓰지 않아 상호 간섭이 없음(混淆 根本消除).
개발 시에는 `npm run dev`(= `http-server mobile`) 로 소스 그대로 미리보기.

---

## 4. 안드로이드(APK) 빌드/배포

### 4-1. 최초 1회 초기화
```powershell
npm install
npm run android:init          # cap add android + FontKeyPlugin 자동 복사
```

### 4-2. API 주소 주입 + 동기화 + 빌드
```powershell
# 디버그 APK (빠른 테스트)
npm run build:apk-debug -- --api=https://api.your-domain.com
#   → android/app/build/outputs/apk/debug/app-debug.apk

# 릴리스 AAB (Play Store)
npm run build:aab-release -- --api=https://api.your-domain.com
#   → android/app/build/outputs/bundle/release/app-release.aab
```
`build:apk-debug` / `build:aab-release` 는 내부적으로
`android:sync` (= `android:config` API 주입 + `cap sync android`) 를 먼저 실행.

### 4-3. 서명 키 (릴리스만)
```powershell
keytool -genkey -v -keystore gospel-release.keystore -alias gospel -keyalg RSA -keysize 2048 -validity 10000
```
`android/app/build.gradle` 에 signingConfigs.release 추가 (기존 문서 참조).

---

### 4-4. 중국 시장(중국대륙/홍콩) 전용 설정 ⭐ (2026-07-31 결정)

**사용자 결정**:
- 결제 = **PortOne V2 + 微信支付/支付宝 channel** (PortOne 콘솔에서 channel 설정, 클라이언트 코드 변경 없음)
- 백엔드 = **홍콩 노드** 배포 (중국대륙에서 직접 접근 가능, ICP 비안 불필요, 저지연)
- 배포 = **자체 공식사이트 직링크 다운로드** (Google Play / 중국 앱스토어 비의존)

**코드 측 해결 완료 (CJK 시리즈)**:
| 항목 | 처리 | 파일 |
|------|------|------|
| C1-폰트 | Google Fonts(`fonts.googleapis.com`) 제거 → 시스템 폰트 스택 | `mobile/index.html`, `mobile/styles.css` |
| C1-Google로그인 | GIS SDK를 `__GOSPEL_GOOGLE_SDK__` 플레이스홀더로 조건주입. **중국 빌드(`--market=cn`)는 주입 안 함** → APK에 Google 의존 0 | `mobile/index.html`, `scripts/build-config.js` |
| C3-API address | `GOSPEL_API_BASE` 빌드 시 주입. 홍콩 도메인 지정 | `scripts/build-config.js`, `.env.mobile.example` |
| C5-푸시 | Web Push, Google 프레임워크 없으면 `PushService`가 자동降级(no-op) | `mobile/services/index.js` |
| 안드로이드 GMS | `google-services` classpath/플러그인 제거 → Firebase/FCM 0 의존 | `android/build.gradle`, `android/app/build.gradle` |

**시장별 빌드 스크립트** (기본=홍콩):
```powershell
npm run android:config          # --market=hk (홍콩/해외: GIS SDK 주입 + 홍콩 API)
npm run android:config:cn       # --market=cn (중국대륙 순수: Google 0, 시스템폰트만)
npm run android:config:global   # --market=global (해외 풀기능)
```
`.env.mobile`(예: `.env.mobile.example` 복사)에 `ANDROID_API_BASE=https://api.flowai.hk` 등 지정.

### 4-4.5 ⭐ Google Play 업로드 — 별도 패키지 필수 (결제 격리)

**질문: "구글 플레이에 올리려면 다른 버전을 만들어야 하나?" → 네, 반드시 별도 패키지입니다.**

Google Play 개발자 정책은 **앱 내 제3자 결제(위챗/알리페이 등)를 금지**합니다.
우리 `direct` 채널 APK 는 PortOne(PG사)을 통해 위챗/알리페이를 결제에 사용하므로,
이 패키지를 그대로 GP 에 올리면 **거절/삭제** 대상입니다. 따라서 두 개의 물리적으로
완전히 분리된 패키지를 만듭니다:

| 구분 | direct 패키지 | googleplay 패키지 |
|------|---------------|-------------------|
| package name | `com.gospelai.app` | `com.gospelai.app.play` |
| 빌드 명령 | `npm run android:config` (+ sync) | `npm run android:config:play` (+ sync) |
| PortOne SDK | ✅ 포함 (위챗/알리페이 채널) | ❌ 완전 제거 (런타임 `GOSPEL_PAYMENT_CHANNEL='googleplay'`) |
| 결제 동작 | PortOne 결제창 | GP 결제 placeholder 로 폴백(토스트 안내) — **실제 GP Billing 연동은 별도 구현 필요** |
| 배포 경로 | 자체 공식사이트 직링크 (`download.html`) | Google Play 스토어 전용 |
| AAB 출력 | `android/app/build/outputs/bundle/release/app-release.aab` | 동일 경로(동일 파일명이나 package name 이 다름) |

**빌드 시 자동 처리**: `build-config.js` 가 `--channel=googleplay` 이면
`capacitor.config.json` 의 `appId` 를 `com.gospelai.app.play` 로 자동 변경하고 PortOne 태그를
제거합니다(direct 는 `com.gospelai.app` 로 복원). → `cap sync` 시 네이티브 package name 이
올바르게 생성되어 두 패키지가 GP 콘솔에서 충돌하지 않습니다.

⚠️ **GP 결제 실제 연동은 아직 미구현**: 현재 `openPayment()` 는 googleplay 채널에서
"곧 오픈됩니다" 토스트만 띄웁니다. GP 상점에 출시하려면 GP Billing Client
(`@capacitor-community/google-play-billing` 또는 native `BillingClient`)를 붙여
`subscriber` 업그레이드를 처리해야 합니다(별도 작업). **결제 없이 먼저 출시(무료 앱)할 거면
지금 상태로도 GP 제출 가능** (제3자 결제 코드가 아예 없으므로 정책 위반 아님).

### 4-5. 공식사이트 직링크 배포 (Google Play 비의존) ⭐

1. **APK 빌드**:
   ```powershell
   npm run build:apk-release      # 릴리스 APK (서명 필요)
   # 또는 테스트: npm run build:apk-debug
   ```
2. **공식사이트 releases 폴더로 복사**:
   ```powershell
   npm run publish:web            # android/app/build/outputs/apk/* → releases/flow-ai.apk
   ```
3. **releases/ + download.html 을 홍콩 노드 정적 호스팅** (nginx/Cloudflare 등).
   사용자는 `https://<공식도메인>/download.html` 접속 → APK 다운로드.
4. **설치 안내** (`web/download.html` 에 이미 중문 포함):
   - 안드로이드 8+ 기본 차단 → "설정 → 이 출처 허용" 토글 후 설치.
   - Google Play 미경유이므로 업데이트도 공식사이트에서 직접.

> ⚠️ APK는 `capacitor://localhost` origin 으로 백엔드 호출 → 백엔드 CORS_ORIGINS 에
> `capacitor://localhost,https://localhost` 포함 필수 (섹션 6).

---

## 5. 환경변수 파일 (.env.mobile, gitignore)

빌드 시 `--api=` 플래그 대신 파일로 주입 가능:
```text
WEB_API_BASE=https://api.your-domain.com
ANDROID_API_BASE=https://api.your-domain.com
```
`scripts/build-config.js` 가 자동 로드.

---

## 6. CORS 설정 (웹 + APK 양쪽 origin 병기)

백엔드 `.env` / `.env.production`:
```text
CORS_ORIGINS=https://app.your-domain.com,capacitor://localhost,https://localhost,http://localhost:8501
```
- 웹 PWA: `https://app.your-domain.com`
- APK: `capacitor://localhost` + `https://localhost` (Capacitor 6 기본 scheme)

---

## 7. 해결된 리스크 (더블체크 결과)

| ID | 리스크 | 해결 |
|----|--------|------|
| R1 | API 주소 `index.html` 하드코딩 | 플레이스홀더 `__GOSPEL_API_BASE__` + build-config.js 주입 |
| R2 | 푸시 아이콘 누락(`.svg`만 존재) | `icon-192.png` / `icon-512.png` / `badge.png` 생성 |
| R3 | 푸시 `platform:'web'` 하드코딩 | `Platform.getPlatform()` 동적 분기 (android/web) |
| R4 | Bible fetch 상대경로(Capacitor origin 위험) | `new URL('./data/bible/', location.href)` 절대경로 |
| R5 | 런타임 분기 안전성 | `app.js:239` `if(window.Capacitor...)` 가드 확인됨 (양호) |
| R6 | APK CORS origin 누락 | `.env.production` 에 웹+APK origin 병기 가이드 |

---

## 8. 웹/APK 공유 유지보수 체크리스트

- [ ] `mobile/` 수정 후 **양쪽 모두** 재빌드 (`build:web` + `build:apk-debug`)
- [ ] 새로운 네이티브 기능 추가 시 `Platform.callPlugin()` 가드 필수 (웹 깨짐 방지)
- [ ] API 주소 변경 시 `.env.mobile` 또는 `--api=` 플래그로 양쪽 주입
- [ ] CORS 변경 시 웹 도메인 + `capacitor://localhost` + `https://localhost` 모두 포함
- [ ] 푸시 테스트 시 웹/APK 구독이 백엔드에서 `platform` 으로 정확히 분류되는지 확인

---

## 9. 문제 해결

| 문제 | 원인 | 해결 |
|------|------|------|
| APK CORS 에러 | origin 미등록 | `.env` CORS_ORIGINS 에 `capacitor://localhost,https://localhost` 추가 |
| 웹 API 주소 이상 | 플레이스홀더 미주입 | `node scripts/build-config.js web --api=...` 재실행 |
| APK white screen | sync 안됨 | `npm run android:sync` 후 재빌드 |
| 푸시 안 옴(APK) | platform 오인 | `Platform.getPlatform()` 가드 정상 동작 확인 |
| Bible 오프라인 안 됨(APK) | 상대경로 실패 | `services/index.js` 절대경로 적용 확인 |
