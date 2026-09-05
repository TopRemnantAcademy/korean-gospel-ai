# APK 버전 종합 점검 리포트

> 대상: `mobile/`(PWA) → Capacitor 6 → `android/`(APK/AAB) 파이프라인
> 점검 기준: 실제 소스 코드 정적 분석 (파일·라인 근거 기반). 실기기 런타임 테스트는 별도 필요.
> 심각도: 🔴 치명(Critical) · 🟠 높음(High) · 🟡 보통(Medium) · 🔵 낮음(Low)

---

## 요약 (심각도별 집계)

| 심각도 | 건수 | 핵심 |
|--------|-----|------|
| 🔴 치명 | 2 | APK API 주소가 `127.0.0.1`로 빌드됨 · CORS origin 불일치 |
| 🟠 높음 | 4 | 알림 권한 누락 · 로그인 상태 불일치 · 뒤로가기 미처리 · 네이티브 소스 드리프트 |
| 🟡 보통 | 6 | 런처 아이콘·브랜딩 · 상태바 대비 · Google버튼(중국) · 통화 하드코딩 · Android14 포그라운드 · 검색 상대경로 |
| 🔵 낮음 | 4 | 자동음질 미동작 · emoji 아이콘 · mixed-content · 키스토어 관리 |

---

## 1. UI 문제

### 1-1. 🟡 런처 아이콘이 기본 Capacitor 템플릿(placeholder) 그대로
- **위치**: `android/app/src/main/res/mipmap-*/ic_launcher*.png`, `ic_launcher_foreground.png` (모두 2~6KB, 2025-04-01 템플릿 생성일)
- **증상**: 홈 화면에 앱을 설치하면 복음 AI 브랜드가 아닌 Capacitor 기본 로봇 아이콘이 표시됨. `mobile/icons/`(PWA용 icon-192/512)은 별도로 존재하나 네이티브 런처에 반영 안 됨.
- **원인**: `cap add android` 시 생성된 기본 아이콘을 교체하지 않음.
- **심각도**: 보통(브랜드 신뢰도)

### 1-2. 🟡 상태바(StatusBar) 아이콘 대비 불량 + 색상 불일치
- **위치**: `capacitor.config.json` `StatusBar.style="DARK"` + `backgroundColor:"#12362f"`(짙은 녹색), `mobile/app.js:255` `StatusBar.setBackgroundColor({color:'#0C0A08'})`, `mobile/index.html:6` `theme-color #0C0A08`
- **증상**: "DARK" 스타일은 **밝은 배경용 어두운 아이콘**을 의미하므로, 짙은 녹색(#12362f) 배경 위에서 상태바 아이콘이 거의 보이지 않음. 또한 `#12362f`(녹색)와 `#0C0A08`(흑색)이 서로 달라 스플래시→앱 전환 시 상태바 색이 튐.
- **원인**: 스타일/배경색 매칭 오류 + 여러 곳에 하드코딩된 색상이 비동기화. (최근 요구된 "흑백 테마"와도 충돌)
- **심각도**: 보통

### 1-3. 🔵 플레이어/UI의 emoji 아이콘 — 기기별 렌더링 불일치
- **위치**: `mobile/player.js` (⏮ ⏭ 🔀 🔁 ⏲ 🎚 등), `mobile/screens/index.js`(🔒 등)
- **증상**: 구형 Android WebView / 일부 제조사 폰트에서 emoji가 흑백 또는 tofu(□)로 표시될 수 있음. iOS·최신 기기와 다른 외형.
- **원인**: 전문 아이콘 라이브러리(SVG) 대신 emoji 문자 사용 (하단 탭은 이미 SVG로 교체됨).
- **심각도**: 낮음(시각 일관성)

### 1-4. 🟡 상태바/스플래시 색이 "흑백 테마" 요구와 충돌
- **위치**: `capacitor.config.json`(SplashScreen/StatusBar `#12362f`), `mobile/index.html` `theme-color #0C0A08`
- **증상**: 앱 내부는 흑백 테마로 전환했으나, 네이티브 스플래시·상태바는 녹색 계열로 남아 첫인상이 불일치.
- **원인**: 최근 UI 테마 변경이 네이티브 레이어 설정에 미반영.
- **심각도**: 보통

---

## 2. 버튼 문제

### 2-1. 🟠 Android 하드웨어 뒤로가기 버튼 미처리 (앱 즉시 종료)
- **위치**: `@capacitor/app` 의존성은 있으나(`package.json`) `App.addListener('backButton', …)` 호출이 전무 (`mobile/` 전체 grep 결과 없음)
- **증상**: 플레이어 전체화면/설정 오버레이/액션시트가 열린 상태에서 뒤로가기를 누르면 **해당 시트가 닫히지 않고 앱이 곧바로 종료**됨. 탭 간 이동에도 뒤로가기로 이전 화면 복귀 불가.
- **원인**: SPA라 브라우저 history가 없고, Capacitor의 뒤로가기 이벤트를 구독하지 않음.
- **심각도**: 높음(핵심 UX 흐름)

### 2-2. 🟡 중국(CN) 빌드에서도 "Google 登录" 버튼 표시 (죽은 버튼)
- **위치**: `mobile/app.js:214` `_buildAuthSection()`에서 `btn-google` 버튼을 무조건 렌더링
- **증상**: `--market=cn` 빌드는 GIS SDK를 주입하지 않으므로(`build-config.js:212`) 버튼을 눌러도 항상 "无法使用 Google 登录（GIS 未加载）" 에러만 표시됨.
- **원인**: 시장별 조건부 렌더링 없음.
- **심각도**: 보통

### 2-3. 🟡 "去支付" 버튼 통화 단위 하드코딩
- **위치**: `mobile/screens/index.js:854` `Number(p.amount).toLocaleString() + '원 / ' + unit`
- **증상**: 중국/홍콩 시장(위챗/알리페이)에서도 가격이 **원(KRW)**으로 표시됨. 실제 결제 통화는 `data.currency`(백엔드)와 분리되어 있어 표시-결제 불일치 가능.
- **원인**: 통화 심볼 하드코딩.
- **심각도**: 보통(결제 신뢰도)

> 참고: `mobile/screens/index.js:819/858`의 소문자 `onclick:`은 `dom.js:15`의 `k.slice(2).toLowerCase()` 정규화로 **정상 동작**함(문제 아님 — 오탐 방지).

---

## 3. 프로세스(흐름) 문제

### 3-1. 🔴 APK에 `127.0.0.1:8000` API 주소가 빌드됨 (출시 차단)
- **위치**: `make-apk.bat:17`(web 스텝에만 `--api=http://127.0.0.1:8000`), `scripts/build-config.js:69-77`(`getApiBase` 폴백 `127.0.0.1:8000`), `.env.mobile` **부재**
- **증상**: `make-apk.bat`의 [1/4] 스텝(`npm run android:sync` → `build-config.js android --market=hk`)은 `--api`를 전달하지 않으므로 `GLOBAL_API_BASE`/`ANDROID_API_BASE`가 없으면 **APK에 `http://127.0.0.1:8000`이 박힘**. 실기기에서 `127.0.0.1`은 기기 자신이므로 백엔드 도달 불가 → 채팅/미디어/인증/결제 전부 실패.
- **원인**: ① 원스톱 스크립트가 안드로이드 스텝에 API 플래그 미전달 ② `.env.mobile`이 gitignore로 존재하지 않음(예시 `.env.mobile.example`만 있음).
- **심각도**: 치명(현재 `releases/flow-ai.apk`가 이 경로로 빌드됐다면 실제 배포판이 백엔드에 연결 불가)

### 3-2. 🔴 CORS origin 불일치 (`https://app.gospelai.local` 미등록)
- **위치**: `capacitor.config.json` `server.androidScheme="https"` + `hostname="app.gospelai.local"` ↔ 백엔드 `CORS_ORIGINS`(`.env`·`backend/app/config.py:191`)에 `capacitor://localhost,https://localhost`만 있고 `https://app.gospelai.local` **없음**
- **증상**: 커스텀 hostname 때문에 APK의 실제 origin은 `https://app.gospelai.local`. fetch의 `Origin` 헤더가 허용 목록에 없어 **모든 API 호출이 CORS로 차단**됨 (API 주소가 올바르더라도).
- **원인**: 문서(ANDROID_BUILD.md §6)는 `https://localhost` 기준인데 실제 설정은 커스텀 hostname 사용.
- **심각도**: 치명

### 3-3. 🟠 로그인 상태 불일치 (재시작 후 인증 소실)
- **위치**: `mobile/utils/state.js:33` `isLoggedIn: !!localStorage.getItem('gospel_sub_id')` / `state.js:202-217` `login()`은 토큰을 **메모리만** 저장, `subId`·`user`는 localStorage 저장
- **증상**: 앱 프로세스 종료 후 재시작하면 `isLoggedIn=true`(subId 잔존)로 **로그인된 것처럼 표시**되나 토큰이 없어 `authHeaders()`가 빈 값 → 결제·구독 쿼터·구독자 콘텐츠 요청이 **게스트로 강등**. UI와 실제 인증 상태가 어긋남(재로그인 유도 없음).
- **원인**: 보안상 토큰 미영속(의도된 트레이드오프)이나, `isLoggedIn` 판정을 subId 존재로 해서 상태가 분리됨.
- **심각도**: 높음

### 3-4. 🟡 Android 14(API 34) 포그라운드 서비스 시작 제약
- **위치**: `android/.../MediaPlaybackService.java:205` `ServiceCompat.startForeground(..., FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)`, `MediaSessionPlugin.java:38` `getContext().startService(i)`
- **증상**: Android 12+에서 백그라운드 중 `startService`는 `IllegalStateException` 위험, Android 14는 백그라운드에서 `mediaPlayback` 포그라운드 서비스 시작이 제한됨. 예외는 `startForeground`만 try/catch하므로 `startService` 단계 예외는 미처리 → 잠재적 크래시.
- **원인**: 서비스 시작 시점이 항상 포그라운드임을 보장하지 않음.
- **심각도**: 보통

### 3-5. 🟠 네이티브 플러그인 소스 드리프트 (재생성 시 기능/빌드 손실)
- **위치**: `mobile/integration/android/`에는 `FontKeyPlugin.java`·`MainActivity.java`(구버전, `registerPlugin` 없음)만 존재. 반면 실제 `android/`에는 `MediaSessionPlugin.java`·`MediaPlaybackService.java`·`registerPlugin` 포함 `MainActivity`·`AndroidManifest.xml`(서비스/수신자 등록)이 **수동 추가**되어 있음.
- **증상**: `npm run android:init`(`cap add android` + `copy-android-plugins`)을 재실행하면 `MediaSession*` 파일과 매니페스트 수정이 사라져 → 매니페스트가 `MediaPlaybackService`를 참조한 채 클래스가 없어 **빌드 실패**하거나, 백그라운드 재생 기능이 소실됨.
- **원인**: "단일 소스(mobile/)" 원칙 위반 — 신규 네이티브 파일이 integration/에 역동기화되지 않음.
- **심각도**: 높음(재빌드/유지보수 리스크)

### 3-6. 🔵 `navigator.connection` 미지원 (자동 음질 미동작)
- **위치**: `mobile/player.js:849-861` `autoQualityByNetwork()`
- **증상**: Android WebView에는 `navigator.connection`이 없어 항상 `'standard'`로 고정됨(의도된 자동 전환 무의미).
- **원인**: Chrome 전용 API 사용.
- **심각도**: 낮음

### 3-7. 🔵 Bible 전체검색 상대경로 (R4 절대경로 수정 누락)
- **위치**: `mobile/services/index.js:251` `searchLocal()`의 `fetch('./data/bible/${idx}.json')` — `_localMeta`(163)·`getPassage`(201)는 `new URL(..., location.href)` 절대경로로 수정됐으나 이곳만 상대경로 잔존
- **증상**: 특정 Capacitor origin 맥락에서 로컬 Bible 검색 fetch가 실패할 가능성(다른 경로는 이미 방어됨).
- **원인**: R4 수정의 부분 적용.
- **심각도**: 낮음

---

## 4. 기능 문제

### 4-1. 🟠 알림 권한(`POST_NOTIFICATIONS`) 누락 (Android 13+)
- **위치**: `android/app/src/main/AndroidManifest.xml` — `INTERNET`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK`만 존재. `POST_NOTIFICATIONS` 없음, 런타임 권한 요청 코드도 없음.
- **증상**: `targetSdkVersion=34`이므로 Android 13+에서 미디어 재생 포그라운드 알림(`MediaPlaybackService`의 재생 알림)이 **표시되지 않음**. 푸시 알림도 동일하게 차단.
- **원인**: Android 13 도입 권한 미반영.
- **심각도**: 높음

### 4-2. 🟠 APK에서 푸시 알림 실질 미동작 (Web Push 한계)
- **위치**: `mobile/services/index.js:91-153` `PushService`(Web Push/VAPID), `android/app/build.gradle:76` Firebase/FCM **제거** 명시
- **증상**: Web Push는 브라우저의 push service(GCM/FCM)가 필요한데 Capacitor WebView에는 없으므로 `PushManager`/`Notification`이 미지원 → `setup()`이 조용히 no-op. `ANDROID_BUILD.md`의 "Web Push + (선택)FCM" 중 FCM이 실제로는 미구현이라 **APK 알림 기능이 사실상 없음**.
- **원인**: Google 의존 제거(중국 배포 요구)와 푸시 구현의 공백.
- **심각도**: 높음(기능 공백; 오프라인 배포라면 허용 가능하나 명시 필요)

### 4-3. 🔴 mixed-content로 `http://` API 차단 (1번과 복합)
- **위치**: `capacitor.config.json` `androidScheme="https"` + `allowMixedContent=false` ↔ 폴백 API `http://127.0.0.1:8000`
- **증상**: WebView가 HTTPS 컨텍스트이므로 `http://` API 호출은 mixed content로 **추가 차단**. 즉 3-1의 `127.0.0.1` 폴백은 "localhost + http" 이중으로 실패.
- **원인**: HTTPS 스킴 + http 폴백의 조합.
- **심각도**: 치명(3-1과 동일 근본 원인)

### 4-4. 🔵 릴리스 서명 키 관리
- **위치**: `android/local.properties`(평문 `storePassword`/`keyPassword`), `android/app/release-key.keystore`
- **증상**: `.gitignore`(`android/`, `*.keystore`)로 저장소에는 안 들어가지만, 키스토어/비밀번호가 단일 로컬 머신에만 존재 → 분실 시 기존 설치본 업데이트 불가(서명키 불일치).
- **원인**: 키 백업/관리 절차 부재.
- **심각도**: 낮음(운영 리스크)

### 4-5. 🔵 앱 이름 브랜딩 불일치
- **위치**: `android/app/src/main/res/values/strings.xml` `app_name="FLOW AI"` ↔ `app.py`(Streamlit) 타이틀 "복음 AI", `mobile/index.html` `<title>FLOW</title>`
- **증상**: 런처 이름/웹 타이틀/내부 브랜드가 서로 달라 사용자 혼란.
- **원인**: 리브랜딩 미정리. (의도된 중국시장 "FLOW" 브랜드일 수도 있으나 통일 필요)
- **심각도**: 낮음

---

## 부록 — 확인 결과 "정상" 판정한 항목 (오탐 방지)

| 항목 | 판정 |
|------|------|
| `onclick:`(소문자) 이벤트 바인딩 | `dom.js:15`가 `slice(2).toLowerCase()`로 정규화 → **정상 동작** |
| 강제 업데이트 오버레이 `./download.html` | `build-config.js:191-198`이 dist에 복사 → 404 아님 |
| 볼륨키→폰트 브리지 | `MainActivity.onKeyDown` + `registerPlugin` 올바르게 등록 |
| Capacitor 네이티브 가드 | `utils/platform.js` `isNative()`/`callPlugin()` try/catch 안전 |

---

## 우선순위 권고 (조치 순서)

1. 🔴 **API 주소 주입 수정**: `make-apk.bat`의 `android:sync`에 `--api=<실제 HTTPS 도메인>` 전달 또는 `.env.mobile` 생성(`ANDROID_API_BASE`/`GLOBAL_API_BASE`). 폴백을 `http://127.0.0.1`에서 제거.
2. 🔴 **CORS 정합**: `CORS_ORIGINS`에 `https://app.gospelai.local` 추가 (또는 `capacitor.config.json`의 `hostname` 제거로 `https://localhost` 사용).
3. 🟠 **`POST_NOTIFICATIONS` 권한 + 런타임 요청** 추가 (Android 13+).
4. 🟠 **로그인 상태 정합**: `isLoggedIn`을 토큰 존재 여부로 판정하거나, 토큰 소실 시 재로그인 유도.
5. 🟠 **뒤로가기 처리**: `App.addListener('backButton')`으로 시트/오버레이 닫기 → 탭 이전 복귀 순서 구현.
6. 🟠 **네이티브 소스 동기화**: `MediaSessionPlugin`·`MediaPlaybackService`·`MainActivity`·매니페스트 수정을 `mobile/integration/android/`에 역백업.
7. 🟡 런처 아이콘 교체 · 상태바 스타일/색 정합 · CN 빌드 Google 버튼 숨김 · 통화 심볼 수정.
