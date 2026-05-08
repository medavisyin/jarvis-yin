@echo off
title Restarting Jarvis Servers...
set SCRIPT_DIR=%~dp0

:: Set proxy for news fetchers (BBC, Reuters, DW, Guardian need SOCKS proxy)
if not defined BRIEFING_PROXY set BRIEFING_PROXY=socks5://localhost:10808

:: Resolve the real Python executable path (handles Windows Store alias)
set PYTHON=
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
    echo ERROR: Python not found. Install Python from python.org or the Microsoft Store.
    pause
    exit /b 1
)

echo Stopping existing servers...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18889.*LISTEN"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18888.*LISTEN"') do taskkill /PID %%a /F >nul 2>&1

timeout /t 3 /nobreak >nul

echo Starting Search UI (port 18888)...
start "Jarvis Search" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\search_ui.py"

timeout /t 2 /nobreak >nul

echo Starting Agent (port 18889)...
start "Jarvis Agent" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\agent.py"

echo.
echo Restarted. Wait ~15 seconds for model loading.
echo   Search UI: http://localhost:18888
echo   Agent:     http://localhost:18889
timeout /t 5
