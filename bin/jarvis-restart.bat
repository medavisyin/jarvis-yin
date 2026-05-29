@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Restarting Jarvis Servers...
set "SCRIPT_DIR=%~dp0"

:: Restart target (default ALL). Accepts /UI /AGENT /TELEGRAM /ALL
:: (case-insensitive; the leading slash is optional).
set "TARGET=ALL"
if not "%~1"=="" (
    set "ARG=%~1"
    set "ARG=!ARG:/=!"
    for %%A in (UI AGENT TELEGRAM ALL) do if /I "!ARG!"=="%%A" set "TARGET=%%A"
)

echo Restart Mode: %TARGET%
echo (Use: jarvis-restart.bat [/UI ^| /AGENT ^| /TELEGRAM ^| /ALL])

:: Set proxy for news fetchers (BBC, Reuters, DW, Guardian need SOCKS proxy)
if not defined BRIEFING_PROXY set "BRIEFING_PROXY=socks5://localhost:10808"

:: Resolve the real Python executable path (handles Windows Store alias)
set "PYTHON="
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
    echo ERROR: Python not found. Install Python from python.org or the Microsoft Store.
    pause
    exit /b 1
)

set "PORT_UI=18888"
set "PORT_AGENT=18889"
set "PORT_TG=18890"

echo Stopping existing servers...

if /I "%TARGET%"=="ALL" (
    call :KillPort %PORT_UI%
    call :KillPort %PORT_AGENT%
    call :KillPort %PORT_TG%
    call :KillBot
) else if /I "%TARGET%"=="UI" (
    call :KillPort %PORT_UI%
) else if /I "%TARGET%"=="AGENT" (
    call :KillPort %PORT_AGENT%
) else if /I "%TARGET%"=="TELEGRAM" (
    call :KillPort %PORT_TG%
    call :KillBot
)

timeout /t 3 /nobreak >nul

if /I "%TARGET%"=="ALL" (
    call :StartUI
    timeout /t 2 /nobreak >nul
    call :StartAgent
    timeout /t 2 /nobreak >nul
    call :StartTelegram
) else if /I "%TARGET%"=="UI" (
    call :StartUI
) else if /I "%TARGET%"=="AGENT" (
    call :StartAgent
) else if /I "%TARGET%"=="TELEGRAM" (
    call :StartTelegram
)

echo.
echo Restart complete (%TARGET%).
echo   Search UI:    http://localhost:%PORT_UI%
echo   Agent:        http://localhost:%PORT_AGENT%
echo   Telegram Bot: port %PORT_TG%
echo.
echo Usage: jarvis-restart.bat [/UI ^| /AGENT ^| /TELEGRAM ^| /ALL]
echo   Restart all:        jarvis-restart.bat /ALL   (or just double-click)
echo   Restart UI only:    jarvis-restart.bat /UI
echo   Restart Agent:      jarvis-restart.bat /AGENT
echo   Restart Telegram:   jarvis-restart.bat /TELEGRAM
echo.
timeout /t 5
endlocal
exit /b 0

:: ---------------------------------------------------------------------------
:: Subroutines
:: ---------------------------------------------------------------------------

:KillPort
:: %1 = TCP port whose owning process should be terminated
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%~1 "') do taskkill /PID %%a /F >nul 2>&1
exit /b 0

:KillBot
:: Stop the Telegram bot via its PID file (it has no listening port)
set "BOT_PID_FILE=%SCRIPT_DIR%..\scripts\bot_telegram.pid"
if exist "%BOT_PID_FILE%" (
    for /f %%p in ('type "%BOT_PID_FILE%"') do taskkill /PID %%p /F >nul 2>&1
    del "%BOT_PID_FILE%" >nul 2>&1
)
exit /b 0

:StartUI
echo Starting Search UI (port %PORT_UI%)...
start "Jarvis Search" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\search_ui.py" %PORT_UI%
exit /b 0

:StartAgent
echo Starting Agent (port %PORT_AGENT%)...
start "Jarvis Agent" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\rag\agent.py" %PORT_AGENT%
exit /b 0

:StartTelegram
echo Starting Telegram Bot (port %PORT_TG%)...
start "Jarvis Telegram" /min "%PYTHON%" "%SCRIPT_DIR%..\scripts\bot_telegram.py"
exit /b 0
