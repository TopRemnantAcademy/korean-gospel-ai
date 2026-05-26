@echo off
chcp 65001 > nul
REM ============================================================
REM STEP4_TUNNEL.bat — Cloudflare Tunnel 시작 스크립트
REM ============================================================
REM
REM 용도: gospel-ai Cloudflare Tunnel 을 실행하고 관리
REM 사용: 
REM   - STEP4_TUNNEL.bat run     (터널 시작)
REM   - STEP4_TUNNEL.bat stop    (터널 종료, 별도 CMD 필요)
REM   - STEP4_TUNNEL.bat status  (터널 상태 확인)
REM

setlocal enabledelayedexpansion

if "%1"=="" (
    call :show_menu
    exit /b 0
)

if /i "%1"=="run" (
    call :run_tunnel
) else if /i "%1"=="stop" (
    call :stop_tunnel
) else if /i "%1"=="status" (
    call :check_status
) else (
    echo 알 수 없는 명령: %1
    call :show_menu
    exit /b 1
)
exit /b 0

REM ============================================================
REM 함수들
REM ============================================================

:show_menu
echo.
echo ===================================================
echo  Cloudflare Tunnel 관리
echo ===================================================
echo.
echo 사용법:
echo   STEP4_TUNNEL.bat run      - Tunnel 시작 (Ctrl+C 로 종료)
echo   STEP4_TUNNEL.bat stop     - Tunnel 종료 (별도 CMD 필요)
echo   STEP4_TUNNEL.bat status   - 상태 확인
echo.
echo 예시:
echo   1. CMD 를 열고 이 파일 실행: STEP4_TUNNEL.bat run
echo   2. 다른 CMD 를 열고: STEP4_TUNNEL.bat status
echo   3. Tunnel 종료: Ctrl+C 누르거나 STEP4_TUNNEL.bat stop
echo.
echo 💡 팁:
echo   - Tunnel 이 실행 중이면 user/app.py, admin/app.py 시작 가능
echo   - gospel-ai.trycloudflare.com 으로 접속 가능
echo   - 로그: TUNNEL_LOGS.txt
echo.
pause
exit /b 0

:run_tunnel
echo.
echo ===================================================
echo  Tunnel 시작 중...
echo ===================================================
echo.
echo 1️⃣  credentials-file 경로 확인...
set "CREDS_DIR=%USERPROFILE%\.cloudflared"
if not exist "!CREDS_DIR!" (
    echo ❌ 오류: !CREDS_DIR! 폴더를 찾을 수 없습니다.
    echo    먼저 scripts/install_cloudflared.bat 실행하세요.
    pause
    exit /b 1
)

echo 2️⃣  Cloudflared 버전 확인...
cloudflared --version
if %ERRORLEVEL% NEQ 0 (
    echo ❌ 오류: cloudflared 를 찾을 수 없습니다.
    echo    먼저 scripts/install_cloudflared.bat 실행하세요.
    pause
    exit /b 1
)

echo.
echo 3️⃣  Tunnel 실행 중... (Ctrl+C 로 종료)
echo.
echo ⏱️  로그는 콘솔과 TUNNEL_LOGS.txt 에 저장됩니다.
echo.
echo ✅ Tunnel 이 실행 중이면 다음 URL 로 접속 가능:
echo    - User  : https://gospel-ai.trycloudflare.com
echo    - Admin : https://admin-gospel-ai.trycloudflare.com
echo.
echo 📋 Streamlit 앱도 실행해야 합니다:
echo    - python -m streamlit run user/app.py --server.port 8502
echo    - python -m streamlit run admin/app.py --server.port 8501 (선택)
echo.
echo ============================================================
echo.

REM Run tunnel with logging
cloudflared tunnel --config config.yml run gospel-ai > TUNNEL_LOGS.txt 2>&1

if %ERRORLEVEL% EQU 0 (
    echo ✅ Tunnel 종료
) else (
    echo ❌ Tunnel 오류 발생 (로그 확인: TUNNEL_LOGS.txt)
)
exit /b %ERRORLEVEL%

:stop_tunnel
echo.
echo Tunnel 프로세스 종료 중...
tasklist /FI "IMAGENAME eq cloudflared.exe" > nul
if %ERRORLEVEL% EQU 0 (
    taskkill /IM cloudflared.exe /F
    echo ✅ Tunnel 종료됨
) else (
    echo ℹ️  실행 중인 Tunnel 을 찾을 수 없습니다.
)
exit /b 0

:check_status
echo.
echo Tunnel 상태 확인 중...
tasklist /FI "IMAGENAME eq cloudflared.exe" > nul
if %ERRORLEVEL% EQU 0 (
    echo ✅ Tunnel 이 실행 중입니다.
    tasklist /V /FI "IMAGENAME eq cloudflared.exe"
) else (
    echo ❌ Tunnel 이 실행 중이 아닙니다.
)
exit /b 0
