@echo off
REM ===================================================================
REM  Korean Gospel RAG - RESTORE
REM  Restores the most recent backup zip.
REM ===================================================================
setlocal
cd /d "%~dp0"
echo.
echo === RESTORE ===
echo.
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found.
    pause
    exit /b 1
)
call "venv\Scripts\activate.bat"
python scripts\restore.py
pause
endlocal
