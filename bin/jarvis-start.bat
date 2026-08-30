@echo off
title Starting Jarvis Servers...
set SCRIPT_DIR=%~dp0
set LOG=%SCRIPT_DIR%..\jarvis-start.log

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

echo Registering 08:00 Daily Fetch scheduled task...
echo [%date% %time%] Registering Daily Fetch scheduled task >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\rag\register-daily-fetch-task.ps1" >> "%LOG%" 2>&1

echo Starting Jarvis Search UI (port 18888)...
echo [%date% %time%] Starting search_ui.py >> "%LOG%"
start "Jarvis Search" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\search_ui.py"

timeout /t 2 /nobreak >nul

echo Starting Jarvis Agent (port 18889, LAN --host 0.0.0.0)...
echo [%date% %time%] Starting agent.py --host 0.0.0.0 >> "%LOG%"
start "Jarvis Agent" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\agent.py" --host 0.0.0.0

timeout /t 2 /nobreak >nul

echo Starting Jarvis Telegram Bot...
echo [%date% %time%] Starting bot_telegram.py >> "%LOG%"
start "Jarvis Telegram" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\bot_telegram.py"

echo.
echo All servers starting. Wait ~15 seconds for model loading.
echo   Search UI:     http://localhost:18888
echo   Agent:         http://localhost:18889  (LAN: use Wi-Fi IP, e.g. http://192.168.x.x:18889)
echo   Telegram Bot:  active (polling)
echo.
echo [%date% %time%] Done >> "%LOG%"
timeout /t 5
