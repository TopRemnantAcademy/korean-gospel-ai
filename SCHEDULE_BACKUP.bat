@echo off
REM ===================================================================
REM  Register a Windows Task Scheduler entry that runs BACKUP.bat
REM  every day at 03:00 AM (when most likely the PC is idle).
REM
REM  To remove: run UNSCHEDULE_BACKUP.bat
REM ===================================================================
setlocal
cd /d "%~dp0"

set TASK_NAME=KoreanGospelAI_DailyBackup

schtasks /Query /TN "%TASK_NAME%" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Task already exists. Removing first ...
    schtasks /Delete /TN "%TASK_NAME%" /F >nul
)

echo [INFO] Registering daily backup at 03:00 AM ...
schtasks /Create /SC DAILY /TN "%TASK_NAME%" /TR "\"%~dp0BACKUP.bat\"" /ST 03:00 /F

if errorlevel 1 (
    echo [ERROR] Failed to register task. Run this .bat as Administrator?
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo  [OK] Daily backup registered: %TASK_NAME%
echo       Runs every day at 03:00 AM (PC must be on).
echo  To remove: UNSCHEDULE_BACKUP.bat
echo ===================================================================
pause
endlocal
