@echo off
REM ===================================================================
REM run_api.bat — Gospel API 자가 복구 런처 (auto-restart on crash)
REM uvicorn 이 비정상 종료되면 3초 후 자동 재시작 → "서버 연결 끊김" 방지
REM 사용: 이 파일을 cmd 창에서 실행 (창을 닫으면 중지)
REM ===================================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0"

:loop
echo [%date% %time%] Gospel API 시작 (127.0.0.1:8000) ...
venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info
echo [%date% %time%] API 종료 (code %errorlevel%). 3초 후 재시작...
timeout /t 3 /nobreak >nul
goto :loop
