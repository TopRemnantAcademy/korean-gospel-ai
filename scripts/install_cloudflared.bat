@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo.
echo ===================================================
echo Cloudflare Tunnel 설치 가이드 (gospel-ai)
echo ===================================================
echo.

REM Step 1: Download cloudflared.exe
echo [Step 1] Cloudflared 다운로드...
echo.
echo 👉 다음 링크에서 다운로드하세요:
echo https://github.com/cloudflare/cloudflared/releases/latest
echo.
echo 👉 파일명: cloudflared-windows-amd64.exe
echo 👉 저장 위치: C:\Program Files\cloudflared\ (권장)
echo 또는 PATH 에 추가된 경로
echo.
pause

REM Step 2: Verify installation
echo.
echo [Step 2] 설치 확인...
cloudflared --version
if %ERRORLEVEL% EQU 0 (
    echo ✅ Cloudflared 설치 완료!
) else (
    echo ❌ 오류: cloudflared 를 찾을 수 없습니다.
    echo    - C:\Program Files\cloudflared\cloudflared.exe 에 설치했는지 확인
    echo    - 또는 PATH 환경변수에 추가했는지 확인
    pause
    exit /b 1
)

REM Step 3: Login to Cloudflare
echo.
echo [Step 3] Cloudflare 계정 연결...
echo.
echo 👉 다음 명령을 실행하면 브라우저가 열립니다.
echo 👉 Cloudflare 계정으로 로그인하세요 (도메인이 없어도 됨).
echo 👉 권한을 허용하면 자동으로 완료됩니다.
echo.
pause
cloudflared tunnel login

REM Step 4: Create tunnel
echo.
echo [Step 4] Tunnel 생성...
cloudflared tunnel create gospel-ai
if %ERRORLEVEL% EQU 0 (
    echo ✅ Tunnel 생성 완료!
    echo.
    echo 💡 Tunnel 정보:
    echo    - 이름: gospel-ai
    echo    - Credentials 파일: %USERPROFILE%\.cloudflared\*.json
    echo.
) else (
    echo ❌ 오류: Tunnel 생성 실패.
    pause
    exit /b 1
)

REM Step 5: Create config.yml
echo.
echo [Step 5] config.yml 생성...
echo.

setlocal enabledelayedexpansion
set "CONFIG_DIR=%USERPROFILE%\.cloudflared"
set "CONFIG_FILE=%CONFIG_DIR%\config.yml"

REM Backup existing config if present
if exist "!CONFIG_FILE!" (
    echo 기존 config.yml 을 config.yml.bak 으로 백업합니다.
    copy "!CONFIG_FILE!" "!CONFIG_FILE!.bak" > nul
)

REM Create config.yml
(
    echo tunnel: gospel-ai
    echo credentials-file: %USERPROFILE%\.cloudflared\{TUNNEL_ID}.json
    echo.
    echo ingress:
    echo   - hostname: gospel-ai.trycloudflare.com
    echo     service: http://localhost:8501
    echo     # 통합 UI - 채팅 모드 (공개 접근)
    echo.
    echo   - hostname: admin-gospel-ai.trycloudflare.com
    echo     service: http://localhost:8501
    echo     # 통합 UI - 내부에서 관리자 모드 전환
    echo.
    echo   - service: http_status:404
    echo     # 기타 URL 은 404 반환
) > "!CONFIG_FILE!"

if exist "!CONFIG_FILE!" (
    echo ✅ config.yml 생성 완료!
    echo    위치: !CONFIG_FILE!
    echo.
) else (
    echo ❌ 오류: config.yml 생성 실패.
    pause
    exit /b 1
)

REM Step 6: Info
echo.
echo ===================================================
echo ✅ 설치 완료!
echo ===================================================
echo.
echo 다음 단계:
echo 1. STEP4_TUNNEL.bat 실행 → Tunnel 시작
echo 2. docs/TUNNEL_GUIDE.md 읽기 → 친구 초대 방법
echo 3. 통합 app.py 앱 시작 (포트 8501)
echo    python -m streamlit run app.py --server.port 8501
echo.
echo 💡 팁:
echo    - 초대 코드 발급: docs/TUNNEL_GUIDE.md 참조
echo    - Admin UI 보호: Cloudflare Access 설정 필요
echo    - 로그: TUNNEL_LOGS.txt (자동 생성)
echo.
pause
