@echo off
REM ===================================================================
REM  Korean Gospel RAG v3 - STEP 3 of 3 : START
REM  Local only (127.0.0.1). Both API and Admin UI inherit PYTHONPATH.
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
call "venv\Scripts\activate.bat"
set "PYTHONPATH=%~dp0"
python -c "from backend.app.main import app; print('  [OK] backend app loaded')"
if errorlevel 1 (
    echo.
    echo [ERROR] API cannot start. Run DIAGNOSE.bat to find the cause.
    pause
    exit /b 1
)
python -c "import sys, os; sys.path.insert(0, os.getcwd()); from admin.lib.api_client import get_health; print('  [OK] admin imports OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] Admin UI imports broken. Run DIAGNOSE.bat.
    pause
    exit /b 1
)

REM ---------- Start API ----------
echo.
echo [INFO] Launching API server  (127.0.0.1:8000) ...
start "Gospel API (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && call venv\Scripts\activate.bat && uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info"

echo [INFO] Waiting up to 30s for API ...
set /a TRIES=0
:WAIT_LOOP
set /a TRIES+=1
timeout /t 2 /nobreak >nul
python -c "import httpx,sys; httpx.get('http://127.0.0.1:8000/admin/health', timeout=2); sys.exit(0)" >nul 2>nul
if not errorlevel 1 goto :API_READY
if %TRIES% LSS 15 goto :WAIT_LOOP

echo [ERROR] API did not start. Check the 'Gospel API' window for the error.
pause
exit /b 1

:API_READY
echo [OK] API is up.

REM ---------- Start Admin UI ----------
echo.
echo [INFO] Launching Admin UI  (127.0.0.1:8501) ...
start "Gospel Admin (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && call venv\Scripts\activate.bat && streamlit run admin\app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false"

timeout /t 2 /nobreak >nul
echo [INFO] Launching User UI  (127.0.0.1:8502) ...
start "Gospel User (do not close)" cmd /k "cd /d %~dp0 && set PYTHONPATH=%~dp0 && call venv\Scripts\activate.bat && streamlit run user\app.py --server.port 8502 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false"

timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:8501"
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:8502"

echo.
echo ===================================================================
echo  [RUNNING]
echo    Admin UI : http://127.0.0.1:8501
echo    API docs : http://127.0.0.1:8000/docs
echo    User UI  : http://127.0.0.1:8502    ^(simple end-user view^)
echo.
echo  To stop  : close the three 'Gospel API', 'Gospel Admin', 'Gospel User' windows.
echo ===================================================================
echo.
pause
endlocal
