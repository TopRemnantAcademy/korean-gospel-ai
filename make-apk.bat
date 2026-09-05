@echo off
REM =====================================================================
REM  직접 배포용(direct /香港 노드) Android APK 빌드 + 배포 원스톱 스크립트
REM  - Google Play 채널은 포함하지 않음(android:config:play 별도)
REM  - JDK 17(Microsoft) / Android SDK 경로는 아래에서 맞춰주세요
REM  - 서명 키스토어 비밀번호는 android\local.properties 에 있음(반드시 교체)
REM =====================================================================
setlocal

set "JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"
set "ANDROID_SDK_ROOT=C:\Users\piaoy\AppData\Local\Android\Sdk"
set "PATH=%JAVA_HOME%\bin;%PATH%"

cd /d "%~dp0"

echo [0/4] 웹 빌드 (웹/앱 동기화 - 단일 소스 mobile/) ...
node scripts\build-config.js web --api=http://127.0.0.1:8000
if errorlevel 1 echo [WARN] web 빌드 실패 - 계속 진행

echo [1/4] direct 채널 설정 + web 자산 동기화(cap sync android) ...
call npm run android:sync
if errorlevel 1 goto :fail

echo [2/4] Gradle assembleRelease (서명 APK) ...
cd android
call gradlew.bat assembleRelease --no-daemon
if errorlevel 1 goto :fail
cd ..

echo [3/4] releases/flow-ai.apk 로 발행 ...
node scripts/publish-apk.js android\app\build\outputs\apk\release\app-release.apk
if errorlevel 1 goto :fail

echo [4/4] 완료. 루트 download.html → releases/flow-ai.apk 직접 배포 가능.
goto :eof

:fail
echo [make-apk] 빌드 실패. 위 로그를 확인하세요.
exit /b 1
