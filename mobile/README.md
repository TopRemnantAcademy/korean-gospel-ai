# Gospel AI Mobile

This directory contains a static mobile PWA client that can be wrapped as an Android APK.

## Build & local preview

> ⚠️ **소스(`mobile/index.html`)는 절대 직접 수정/서빙하지 마세요.**
> 빌드 스크립트(`scripts/build-config.js`)가 소스를 보존한 채
> `mobile/dist/<target>/` 로 플레이스홀더를 주입해 출력합니다.

```powershell
# PWA 빌드 → mobile/dist/web/ (API/채널 주입)
node scripts/build-config.js web --api=https://your-backend.com
# 로컬 미리보기 (빌드 산출물 서빙)
py -m http.server 4174 -d mobile/dist/web
```

Open `http://127.0.0.1:4174`.

APK 용 빌드는 `npm run android:config-release` (또는 `:debug`) 를 사용하세요.
산출물은 `mobile/dist/android/` 로 나가고, `capacitor.config.json` 의 `webDir` 이
이 경로를 가리킵니다.

## API

The app calls the existing FastAPI backend:

- `POST /chat` for counseling and Bible questions
- Local offline cards for quick Bible topics
- Built-in Web Audio meditation tracks for the praise tab

Set the API base URL inside the app settings. For an installed APK, this should be your deployed HTTPS backend URL, not `127.0.0.1`.

## APK route

The current workspace does not include Java, Gradle, or Android SDK, so the APK cannot be compiled on this machine yet.

Recommended release path:

1. Deploy the FastAPI backend from the repository.
2. Host `mobile/dist/web/` (빌드 산출물) on the same domain or a static host over HTTPS.
3. Wrap it with a Trusted Web Activity or Capacitor Android project.
4. Build a signed release APK/AAB from Android Studio.

Capacitor outline after Node and Android tooling are installed:

```powershell
npm create @capacitor/app gospel-ai-android -- --web-dir=../mobile/dist/android
cd gospel-ai-android
npm install @capacitor/android
npx cap add android
npx cap sync android
npx cap open android
```

Then use Android Studio: Build > Generate Signed Bundle / APK.
