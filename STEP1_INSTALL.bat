@echo off
REM ===================================================================
REM  Korean Gospel RAG - STEP 1 of 3 : INSTALL / UPDATE PACKAGES
REM
REM  Smart mode:
REM   - If venv missing  -> create fresh + full install (15-25 min)
REM   - If venv exists   -> incremental install (1-5 min)
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ===================================================================
echo   Korean Gospel RAG  -  STEP 1 / 3  : INSTALL
echo ===================================================================
echo.

REM ---------- (1) Python check ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo         Install Python 3.10 / 3.11 / 3.12 from python.org
    echo         and tick "Add Python to PATH" during install.
    pause
    exit /b 1
)
python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)"
if errorlevel 1 (
    echo [ERROR] Python version must be 3.10 / 3.11 / 3.12.
    python --version
    pause
    exit /b 1
)
echo [OK] Python:
python --version

REM ---------- (2) venv decision ----------
echo.
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Existing venv detected. Using incremental mode.
    echo        ^(To force a clean reinstall, delete the venv folder first.^)
    call "venv\Scripts\activate.bat"
    set MODE=incremental
) else (
    echo [INFO] No venv. Creating fresh environment ...
    python -m venv venv
    if errorlevel 1 ( echo [ERROR] venv create failed & pause & exit /b 1 )
    call "venv\Scripts\activate.bat"
    set MODE=fresh
)

REM ---------- (3) pip upgrade ----------
echo.
echo [INFO] Upgrading pip ...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 ( echo [ERROR] pip upgrade failed & pause & exit /b 1 )

REM ---------- (4) Fresh-only: PyTorch CPU build ----------
if "%MODE%"=="fresh" (
    echo.
    echo [INFO] Installing PyTorch CPU-only build ~250 MB ...
    pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
    if errorlevel 1 (
        pip install torch==2.5.1
        if errorlevel 1 ( echo [ERROR] torch install failed & pause & exit /b 1 )
    )
)

REM ---------- (5) Install / update from requirements ----------
echo.
echo [INFO] Installing packages from requirements.txt ...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check messages above.
    pause
    exit /b 1
)

REM ---------- (6) Cleanup old/legacy stuff ----------
echo.
echo [INFO] Cleaning up legacy files ...
if exist "_legacy"          rmdir /s /q "_legacy"          2>nul
if exist "chroma_db"        rmdir /s /q "chroma_db"        2>nul
if exist ".docker"          rmdir /s /q ".docker"          2>nul
if exist "scripts\ingest_all.py" del /q "scripts\ingest_all.py" 2>nul

echo.
echo ===================================================================
if "%MODE%"=="fresh" (
    echo  [SUCCESS] Fresh install complete!
) else (
    echo  [SUCCESS] Packages updated to latest required versions.
)
echo.
echo  Next:  double-click  STEP2_INDEX.bat
echo ===================================================================
echo.
pause
endlocal
