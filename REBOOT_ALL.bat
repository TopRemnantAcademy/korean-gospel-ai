@echo off
chcp 65001 > nul
REM ===================================================================
REM REBOOT_ALL.bat - GOSPEL AI 전체 재부팅, ONE-CLICK
REM
REM STEP1_INSTALL + STEP2_INDEX + STEP3_START + STEP4_TUNNEL 을
REM 한 번의 클릭으로 순서대로 실행합니다.
REM
REM 재부팅 모드 최적화:
REM   - venv 가 있으면 패키지 설치 생략 - STEP1
REM   - .gospel.db 가 있으면 파괴적 인덱싱 --reset 생략 - STEP2
REM   -> 매번 벡터스토어가 날아가거나 pip 재설치되지 않습니다.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================================================
echo  GOSPEL AI - 전체 재부팅, ONE-CLICK
echo  단계: 0-프로세스정리 1-설치 2-초기화 3-서비스시작 4-터널시작
echo ===================================================================
echo.

REM ---------------------------------------------------------------
REM [0/4] 기존 프로세스 정리 - 진짜 재부팅을 위해
REM ---------------------------------------------------------------
echo [0/4] 기존 프로세스 정리 중...
taskkill /FI "WINDOWTITLE eq Gospel API*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Gospel App*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Gospel Admin*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Gospel Mobile*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Gospel Tunnel*" /F >nul 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 :8501 :8502 :4174 :6333" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>nul
taskkill /IM cloudflared.exe /F >nul 2>nul
REM --- 강화: 창 제목과 무관하게 모든 백엔드(uvicorn) 프로세스 강제 종료 ---
REM (수동 실행/이전 버전으로 남은 시스템 Python 백엔드가 포트 8000·Qdrant 락을
REM  점유해 "API 미기동"이 반복되는 것을 막음)
for /f "skip=1 tokens=1" %%p in ('wmic process where "commandline like '%%backend.app.main%%'" get processid 2^>nul ^| findstr [0-9]') do taskkill /PID %%p /F >nul 2>nul
REM --- 강화: 죽은 프로세스가 남긴 stale Qdrant 임베디드 락 제거 ---
if exist ".qdrant_local\.kggateway_embedded.lock" del /q ".qdrant_local\.kggateway_embedded.lock" >nul 2>nul
if exist ".qdrant_local\.kggateway_embedded.pid"  del /q ".qdrant_local\.kggateway_embedded.pid"  >nul 2>nul
if exist ".qdrant_local\.lock" del /q ".qdrant_local\.lock" >nul 2>nul
timeout /t 3 /nobreak >nul
echo [OK] 정리 완료.
echo.

REM ---------------------------------------------------------------
REM [1/4] 설치 / 업데이트 - venv 없으면 풀설치, 있으면 생략
REM ---------------------------------------------------------------
echo [1/4] Python / venv 확인 ...
if exist "venv\Scripts\activate.bat" (
    REM 재부팅 모드 - 이미 만들어진 venv 를 그대로 사용. 시스템 Python 버전은 무관.
    echo [INFO] 기존 venv 감지 - 패키지 설치 생략, 재부팅 모드
    call "venv\Scripts\activate.bat"
    echo [OK] 기존 환경 사용.
) else (
    REM 신규 설치 시에만 시스템 Python 버전 검사 - torch 2.5.1 은 3.10~3.13 권장
    where python >nul 2>nul
    if errorlevel 1 ( echo [ERROR] Python 이 없습니다 - PATH 에 추가하세요 & pause & exit /b 1 )
    python -c "import sys; v=sys.version_info[:2]; sys.exit(0 if (3,10) <= v <= (3,13) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [WARN] Python python --version - 3.10~3.13 권장. 다른 버전이면 torch 설치 실패 가능.
    ) else (
        python --version
    )
    echo [INFO] venv 없음 - 신규 생성 및 풀설치 ...
    python -m venv venv
    if errorlevel 1 ( echo [ERROR] venv 생성 실패 & pause & exit /b 1 )
    call "venv\Scripts\activate.bat"
    echo [INFO] pip 업그레이드 ...
    python -m pip install --upgrade pip setuptools wheel
    echo [INFO] PyTorch CPU 설치 ~250MB ...
    pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
    if errorlevel 1 pip install torch==2.5.1
    echo [INFO] requirements 설치 ...
    pip install -r requirements.txt
    if errorlevel 1 ( echo [ERROR] pip install 실패 & pause & exit /b 1 )
)
echo [OK] 환경 준비 완료.
echo.

REM ---------------------------------------------------------------
REM [2/4] 초기화 / DB / 인덱싱 - 최초 실행 시에만 전체 인덱싱
REM ---------------------------------------------------------------
echo [2/4] 초기화 중 ...
if not exist "venv\Scripts\activate.bat" ( echo [ERROR] venv 없음. 재실행 필요. & pause & exit /b 1 )
call "venv\Scripts\activate.bat"
if not exist ".env" ( echo [ERROR] .env 파일이 없습니다. & pause & exit /b 1 )

python -c "import sqlalchemy, fastapi, qdrant_client, streamlit" 2>nul
if errorlevel 1 (
    echo [INFO] 일부 패키지 누락 - requirements 재설치 ...
    pip install -r requirements.txt
)

REM 최초 실행 여부 판정 - init_db 가 .gospel.db 를 만듦
set "FIRST_RUN=0"
if not exist ".gospel.db" set "FIRST_RUN=1"

REM 레거시 / 호환성 깨진 데이터 정리
if not exist ".gospel.db" (
    if exist ".qdrant_local" rmdir /s /q ".qdrant_local" 2>nul
)
if exist "_legacy" rmdir /s /q "_legacy" 2>nul
if exist "backend\app\api\ingest.py" del /q "backend\app\api\ingest.py" 2>nul
if exist "src" rmdir /s /q "src" 2>nul
if exist "chroma_db" rmdir /s /q "chroma_db" 2>nul

if not exist "data" mkdir "data"
if not exist "data\documents" mkdir "data\documents"
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\eval" mkdir "data\eval"

echo [INFO] DB 초기화 ...
python scripts\init_db.py
if errorlevel 1 ( echo [ERROR] DB init 실패. DIAGNOSE.bat 확인. & pause & exit /b 1 )

if "!FIRST_RUN!"=="1" (
    echo [INFO] 최초 실행 - 문서 인덱싱 --reset ...
    python scripts\ingest_documents.py --reset
    if errorlevel 1 echo [WARN] 인덱싱 실패. 수동: python scripts\ingest_documents.py --reset
) else (
    echo [SKIP] 이미 초기화됨 - 인덱싱 생략, 재부팅
)
echo [OK] 초기화 완료.
echo.

REM ---------------------------------------------------------------
REM [3/4] 서비스 시작 - API 8000 + 통합앱 8501 + 관리자 8502 + 모바일 4174
REM ---------------------------------------------------------------
echo [3/4] 서비스 시작 ...
set "PYTHONPATH=%~dp0"
venv\Scripts\python.exe -c "from backend.app.main import app; print(' [OK] backend app loaded')"
if errorlevel 1 ( echo [ERROR] API 로드 실패. DIAGNOSE.bat 확인. & pause & exit /b 1 )

echo [INFO] API 서버 시작 - 127.0.0.1:8000 ...
start "Gospel API (do not close)" cmd /k "cd /d %~dp0 && call run_api.bat" <nul

echo [INFO] API 기동 대기 - 최대 80s (콜드 스타트 모델 웜업 포함) ...
set /a TRIES=0
:WAIT_LOOP
set /a TRIES+=1
timeout /t 2 /nobreak >nul
venv\Scripts\python.exe -c "import httpx,sys; httpx.get('http://127.0.0.1:8000/admin/health', timeout=2); sys.exit(0)" >nul 2>nul
if not errorlevel 1 goto :API_READY
if %TRIES% LSS 40 goto :WAIT_LOOP
echo [ERROR] API 미기동. 'Gospel API' 창의 오류를 확인하세요.
pause
exit /b 1
:API_READY
echo [OK] API 준비됨.

echo [INFO] 통합앱 시작 - 127.0.0.1:8501 ...
start "Gospel App (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && set PATH=%~dp0venv\Scripts;%PATH% && venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false" <nul
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8501"
echo [OK] 통합앱 8501 기동.

echo [INFO] 관리자 허브 시작 - 127.0.0.1:8502 ...
start "Gospel Admin (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && set PATH=%~dp0venv\Scripts;%PATH% && venv\Scripts\streamlit.exe run admin/app.py --server.port 8502 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false" <nul
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8502"
echo [OK] 관리자 허브 8502 기동.

echo [INFO] 모바일 PWA 시작 - 127.0.0.1:4174 ...
echo [INFO] 모바일 PWA 빌드 (web 자산 생성) ...
node scripts\build-config.js web --api=http://127.0.0.1:8000
if errorlevel 1 echo [WARN] web 빌드 실패 - dist/web 없으면 fallback 으로 mobile 서빙
echo [INFO] 모바일 PWA 시작 - 127.0.0.1:4174 ...
if exist "%~dp0mobile\dist\web" (
  start "Gospel Mobile (do not close)" cmd /k "cd /d %~dp0 && set PATH=%~dp0venv\Scripts;%PATH% && venv\Scripts\python.exe -m http.server 4174 -d mobile\dist\web" <nul
) else (
  start "Gospel Mobile (do not close)" cmd /k "cd /d %~dp0 && set PATH=%~dp0venv\Scripts;%PATH% && venv\Scripts\python.exe -m http.server 4174 -d mobile" <nul
)
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:4174"
echo [OK] 모바일 PWA 4174 기동.

echo [OK] 서비스 시작 완료 - 8501 / 8502 / 4174.
echo.

REM ---------------------------------------------------------------
REM [4/4] Cloudflare Tunnel 시작 - 백그라운드 창
REM ---------------------------------------------------------------
echo [4/4] Cloudflare Tunnel 시작 ...
set "CREDS_DIR=%USERPROFILE%\.cloudflared"
if not exist "!CREDS_DIR!" (
    echo [WARN] !CREDS_DIR! 없음 - 터널 생략, scripts/install_cloudflared.bat 먼저 실행
    goto :DONE
)
cloudflared --version >nul 2>nul
if errorlevel 1 (
    echo [WARN] cloudflared 없음 - 터널 생략, scripts/install_cloudflared.bat 먼저 실행
    goto :DONE
)
echo [INFO] Tunnel 실행 - 백그라운드 창 ...
start "Gospel Tunnel (do not close)" cmd /k "cd /d %~dp0 && cloudflared tunnel --config config.yml run gospel-ai > TUNNEL_LOGS.txt 2>&1" <nul
echo [OK] Tunnel 시작 요청됨.
:DONE
echo.

echo ===================================================================
echo [RUNNING]
echo  통합 앱   : http://127.0.0.1:8501   - 채팅 및 관리 콘솔
echo  관리자 허브 : http://127.0.0.1:8502   - 운영자 콘솔
echo  모바일 PWA : http://127.0.0.1:4174   - 스마트폰 웹앱
echo  API docs  : http://127.0.0.1:8000/docs
echo  Qdrant    : http://127.0.0.1:6333/dashboard
echo  Tunnel    : https://gospel-ai.trycloudflare.com   - 설정된 경우
echo.
echo  종료: 'Gospel API' / 'Gospel App' / 'Gospel Admin' / 'Gospel Mobile' / 'Gospel Tunnel' 창을 닫으세요.
echo ===================================================================
echo.
pause
endlocal
