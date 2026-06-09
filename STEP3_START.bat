@echo off
REM ===================================================================
REM  Korean Gospel RAG v3 - STEP 3 of 3 : START
REM  통합 앱 — 채팅 + 관리 콘솔을 포트 하나(:8501)로 실행
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ===================================================================
echo   Korean Gospel RAG  -  STEP 3 / 3  : START
echo ===================================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Please run STEP1_INSTALL.bat first.
    pause
    exit /b 1
)

REM ---------- Pre-flight ----------
echo [PRE-CHECK] Verifying the app can load ...
set "PYTHONPATH=%~dp0"
venv\Scripts\python.exe -c "from backend.app.main import app; print('  [OK] backend app loaded')"
if errorlevel 1 (
    echo.
    echo [ERROR] API cannot start. Run DIAGNOSE.bat to find the cause.
    pause
    exit /b 1
)
venv\Scripts\python.exe -c "import sys, os; sys.path.insert(0, os.getcwd()); from admin.lib.api_client import get_health; print('  [OK] app imports OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] App imports broken. Run DIAGNOSE.bat.
    pause
    exit /b 1
)

REM ---------- Start API ----------
echo.
echo [INFO] Launching API server  (127.0.0.1:8000) ...
start "Gospel API (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info"

echo [INFO] Waiting up to 30s for API ...
set /a TRIES=0
:WAIT_LOOP
set /a TRIES+=1
timeout /t 2 /nobreak >nul
venv\Scripts\python.exe -c "import httpx,sys; httpx.get('http://127.0.0.1:8000/admin/health', timeout=2); sys.exit(0)" >nul 2>nul
if not errorlevel 1 goto :API_READY
if %TRIES% LSS 15 goto :WAIT_LOOP

echo [ERROR] API did not start. Check the 'Gospel API' window for the error.
pause
exit /b 1

:API_READY
echo [OK] API is up.

REM ---------- Start Unified App ----------
echo.
echo [INFO] Launching Unified App  (127.0.0.1:8501) ...
echo        [채팅] + [관리 콘솔] 통합 — 사이드바 하단 '관리자 모드' 버튼으로 전환
start "Gospel App (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && venv\Scripts\python.exe -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false"

timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8501"

echo.
echo ===================================================================
echo  [RUNNING]
echo    통합 앱   : http://127.0.0.1:8501  (채팅 + 관리 콘솔)
echo    API docs  : http://127.0.0.1:8000/docs
echo    Qdrant    : http://127.0.0.1:6333/dashboard
echo.
echo  관리자 모드: 사이드바 하단 '관리자 모드' 버튼 클릭
echo  종료하려면: 'Gospel API', 'Gospel App' 창을 닫으세요.
echo ===================================================================
echo.
pause
endlocal
