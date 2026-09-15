@echo off
title Starting Jarvis Servers...
set SCRIPT_DIR=%~dp0
set LOG=%SCRIPT_DIR%..\jarvis-start.log
set "PORT_UI=18888"
set "PORT_AGENT=18889"

:: Set proxy for news fetchers (BBC, Reuters, DW, Guardian need SOCKS proxy)
if not defined BRIEFING_PROXY set BRIEFING_PROXY=socks5://localhost:10808

echo [%date% %time%] Starting Jarvis... > "%LOG%"
echo [%date% %time%] BRIEFING_PROXY=%BRIEFING_PROXY% >> "%LOG%"

:: Verify Python is available and resolve real executable path
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
    echo ERROR: Python not found. Install Python from python.org or the Microsoft Store.
    echo [%date% %time%] ERROR: Python not found >> "%LOG%"
    pause
    exit /b 1
)
echo [%date% %time%] Python: %PYTHON% >> "%LOG%"

echo Stopping anything already on %PORT_UI% / %PORT_AGENT%...
echo [%date% %time%] Killing existing Search/Agent listeners >> "%LOG%"
call :KillPort %PORT_UI%
call :KillPort %PORT_AGENT%
timeout /t 2 /nobreak >nul

echo Ensuring Agent UI (web/dist) is built...
echo [%date% %time%] ensure_web_dist.py >> "%LOG%"
"%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\ensure_web_dist.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo WARNING: frontend build failed or npm missing. Agent may show an old UI.
    echo See %LOG%
    echo [%date% %time%] ensure_web_dist FAILED >> "%LOG%"
)

echo Registering 08:00 Daily Fetch scheduled task...
echo [%date% %time%] Registering Daily Fetch scheduled task >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\rag\register-daily-fetch-task.ps1" >> "%LOG%" 2>&1

echo Starting Jarvis Search UI (port %PORT_UI%)...
echo [%date% %time%] Starting search_ui.py >> "%LOG%"
start "Jarvis Search" /D "%SCRIPT_DIR%.." cmd /k ""%PYTHON%" "scripts\rag\search_ui.py""

timeout /t 2 /nobreak >nul

echo Starting Jarvis Agent (port %PORT_AGENT%, LAN --host 0.0.0.0)...
echo [%date% %time%] Starting agent.py --host 0.0.0.0 >> "%LOG%"
start "Jarvis Agent" /D "%SCRIPT_DIR%.." cmd /k ""%PYTHON%" "scripts\rag\agent.py" --host 0.0.0.0"

timeout /t 2 /nobreak >nul

echo Starting Jarvis Telegram Bot...
echo [%date% %time%] Starting bot_telegram.py >> "%LOG%"
start "Jarvis Telegram" /min /D "%SCRIPT_DIR%.." cmd /c ""%PYTHON%" "scripts\bot_telegram.py""

echo.
echo All servers starting. Wait ~15 seconds for model loading.
echo   Search UI:     http://localhost:%PORT_UI%
echo   Agent:         http://localhost:%PORT_AGENT%  (LAN: use Wi-Fi IP, e.g. http://192.168.x.x:%PORT_AGENT%)
echo   Telegram Bot:  active (polling)
echo   Search and Agent open in visible console windows (keep them open).
echo.
echo [%date% %time%] Done >> "%LOG%"
timeout /t 5
exit /b 0

:KillPort
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%~1 "') do taskkill /PID %%a /F >nul 2>&1
exit /b 0
