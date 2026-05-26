@echo off
REM ===================================================================
REM  Korean Gospel RAG v3 - STEP 2 of 3 : INITIALIZE
REM
REM   - Auto-installs any missing packages (sqlalchemy, etc.)
REM   - Cleans old (incompatible) qdrant data on FIRST run
REM   - Initializes SQLite DB
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ===================================================================
echo   Korean Gospel RAG  -  STEP 2 / 3  : INITIALIZE
echo ===================================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Please run STEP1_INSTALL.bat first.
    pause
    exit /b 1
)
call "venv\Scripts\activate.bat"

if not exist ".env" (
    echo [ERROR] .env file is missing.
    pause
    exit /b 1
)

REM ---------- (1) Auto-fix missing packages ----------
echo [STEP 1/4] Checking critical packages ...
python -c "import sqlalchemy, fastapi, qdrant_client, streamlit" 2>nul
if errorlevel 1 (
    echo [INFO] Some packages are missing. Auto-installing from requirements.txt ...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed. Please run STEP1_INSTALL.bat instead.
        pause
        exit /b 1
    )
) else (
    echo [OK] All critical packages present.
)

REM ---------- (2) First-run cleanup of incompatible old data + legacy files ----------
echo.
echo [STEP 2/4] Cleaning up legacy / incompatible files ...
if not exist ".gospel.db" (
    if exist ".qdrant_local" (
        echo [INFO] Old vector data without DB - removing.
        rmdir /s /q ".qdrant_local" 2>nul
    )
)
REM Remove legacy files that bypass the new lifecycle
if exist "_legacy"                       rmdir /s /q "_legacy"                       2>nul
if exist "backend\app\api\ingest.py"     del   /q   "backend\app\api\ingest.py"     2>nul
REM ingest_documents.py 는 유지 (검색 인덱싱용)
if exist "src"                           rmdir /s /q "src"                           2>nul
if exist "chroma_db"                     rmdir /s /q "chroma_db"                     2>nul
echo [OK] legacy cleanup done.

REM ---------- (3) Create folders ----------
echo [STEP 3/4] Ensuring data folders ...
if not exist "data" mkdir "data"
if not exist "data\documents" mkdir "data\documents"
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\eval" mkdir "data\eval"

REM ---------- (4) Init DB ----------
echo [STEP 4/5] Initializing SQLite database ...
python scripts\init_db.py
if errorlevel 1 (
    echo.
    echo [ERROR] DB init failed.
    echo         Run DIAGNOSE.bat for details.
    pause
    exit /b 1
)

echo.
echo [STEP 5/5] Indexing sample documents into Qdrant ...
python scripts\ingest_documents.py --reset
if errorlevel 1 (
    echo [WARN] Document indexing failed. Run manually: python scripts\ingest_documents.py --reset
)

echo.
echo ===================================================================
echo  [SUCCESS] Initialization complete.
echo.
echo  Next:  double-click  STEP3_START.bat
echo         Then in the Admin UI: Upload -^> Library -^> Publish
echo ===================================================================
echo.
pause
endlocal
