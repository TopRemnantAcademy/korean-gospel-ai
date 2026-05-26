@echo off
REM ===================================================================
REM  Korean Gospel RAG - RESET ALL DATA
REM
REM  Deletes:
REM    - SQLite DB     (.gospel.db)
REM    - Vector DB     (.qdrant_local/)
REM    - Upload cache  (data/uploads/)
REM    - Old legacy    (_legacy/)
REM
REM  Keeps:
REM    - venv/
REM    - data/documents/ (your source files)
REM    - data/eval/ (policy + tests)
REM    - .env (your API keys)
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ===================================================================
echo   RESET ALL DATA  -  This will delete:
echo     - SQLite DB (.gospel.db)
echo     - Vector DB (.qdrant_local/)
echo     - Uploaded files cache (data/uploads/)
echo     - Old legacy folder (_legacy/)
echo.
echo   It will NOT delete venv, .env, data/documents, data/eval
echo ===================================================================
echo.

set /p ANSWER="Are you sure? Type YES to confirm: "
if /I not "%ANSWER%"=="YES" (
    echo Canceled.
    pause
    exit /b 0
)

echo.
echo [INFO] Deleting ...

if exist ".gospel.db"       del /q ".gospel.db" 2>nul
if exist ".gospel.db-shm"   del /q ".gospel.db-shm" 2>nul
if exist ".gospel.db-wal"   del /q ".gospel.db-wal" 2>nul
if exist ".gospel.db-journal" del /q ".gospel.db-journal" 2>nul

if exist ".qdrant_local"    rmdir /s /q ".qdrant_local" 2>nul

if exist "data\uploads"     rmdir /s /q "data\uploads" 2>nul

if exist "_legacy"          rmdir /s /q "_legacy" 2>nul

echo.
echo [OK] Done.
echo      Now run:  STEP2_INDEX.bat  then  STEP3_START.bat
echo.
pause
endlocal
