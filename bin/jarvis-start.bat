@echo off
title Starting Jarvis Servers...
set SCRIPT_DIR=%~dp0
set LOG=%SCRIPT_DIR%..\jarvis-start.log

echo [%date% %time%] Starting Jarvis... > "%LOG%"

:: Verify Python is available and resolve real executable path
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
    echo ERROR: Python not found. Install Python from python.org or the Microsoft Store.
    echo [%date% %time%] ERROR: Python not found >> "%LOG%"
    pause
    exit /b 1
)
echo [%date% %time%] Python: %PYTHON% >> "%LOG%"

echo Starting Jarvis Search UI (port 18888)...
echo [%date% %time%] Starting search_ui.py >> "%LOG%"
start "Jarvis Search" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\search_ui.py"

timeout /t 2 /nobreak >nul

echo Starting Jarvis Agent (port 18889)...
echo [%date% %time%] Starting agent.py >> "%LOG%"
start "Jarvis Agent" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\agent.py"

echo.
echo Both servers starting. Wait ~15 seconds for model loading.
echo   Search UI: http://localhost:18888
echo   Agent:     http://localhost:18889
echo.
echo [%date% %time%] Done >> "%LOG%"
timeout /t 5
