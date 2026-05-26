@echo off
REM ===================================================================
REM  Korean Gospel RAG - Diagnose tool
REM  Run this when something is wrong.
REM  It checks Python, packages, port, env, and tries to load the app.
REM  Saves the full report to diagnose_result.txt
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ===================================================================
echo   DIAGNOSE  -  finding the problem
echo ===================================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Run STEP1_INSTALL.bat first.
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

python "scripts\diagnose.py"

echo.
echo ===================================================================
echo  Report saved to:  diagnose_result.txt
echo  Please share the LAST 30 lines if you need help.
echo ===================================================================
echo.
pause
endlocal
