@echo off
setlocal
cd /d "%~dp0"
set TASK_NAME=KoreanGospelAI_DailyBackup

schtasks /Query /TN "%TASK_NAME%" >nul 2>nul
if errorlevel 1 (
    echo [INFO] No scheduled task to remove.
    pause
    exit /b 0
)
schtasks /Delete /TN "%TASK_NAME%" /F
echo [OK] Scheduled task removed.
pause
endlocal
