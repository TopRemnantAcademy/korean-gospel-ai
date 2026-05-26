@echo off
REM ===================================================================
REM  Korean Gospel RAG - BACKUP
REM  Creates a single zip of: SQLite DB + Qdrant + uploads + policy
REM ===================================================================
setlocal
cd /d "%~dp0"
echo.
echo === BACKUP ===
echo.
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Run STEP1_INSTALL.bat first.
    pause
    exit /b 1
)
call "venv\Scripts\activate.bat"
python scripts\backup.py
if errorlevel 1 (
    echo.
    echo [ERROR] Backup failed.
    pause
    exit /b 1
)
echo.
echo [Done] Backup saved to: backups\
echo.
pause
endlocal
