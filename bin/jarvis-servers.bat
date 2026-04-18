@echo off
setlocal enabledelayedexpansion
title Jarvis Server Manager

set SCRIPT_DIR=%~dp0
set AGENT_SCRIPT=%SCRIPT_DIR%..\scripts\rag\agent.py
set SEARCH_SCRIPT=%SCRIPT_DIR%..\scripts\rag\search_ui.py

:: Resolve the real Python executable path (handles Windows Store alias)
set PYTHON=
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
    echo ERROR: Python not found. Install Python from python.org or the Microsoft Store.
    pause
    exit /b 1
)

:menu
cls
echo ============================================
echo          JARVIS SERVER MANAGER
echo ============================================
echo.
echo   [1] Start Both Servers
echo   [2] Stop Both Servers
echo   [3] Restart Both Servers
echo   [4] Start Agent Only    (port 18889)
echo   [5] Start Search UI Only (port 18888)
echo   [6] Stop Agent Only
echo   [7] Stop Search UI Only
echo   [8] Check Status
echo   [9] Exit
echo.
echo ============================================
set /p choice="Select option: "

if "%choice%"=="1" goto start_both
if "%choice%"=="2" goto stop_both
if "%choice%"=="3" goto restart_both
if "%choice%"=="4" goto start_agent
if "%choice%"=="5" goto start_search
if "%choice%"=="6" goto stop_agent
if "%choice%"=="7" goto stop_search
if "%choice%"=="8" goto status
if "%choice%"=="9" exit /b 0
echo Invalid option.
timeout /t 2 >nul
goto menu

:stop_agent
echo Stopping Agent (port 18889)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18889.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   Stopped PID %%a
)
goto done

:stop_search
echo Stopping Search UI (port 18888)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18888.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   Stopped PID %%a
)
goto done

:stop_both
call :stop_agent
call :stop_search
goto done

:start_agent
echo Starting Agent on port 18889...
start "Jarvis Agent" /min "%PYTHON%" "%AGENT_SCRIPT%"
echo   Agent starting in background window...
goto done

:start_search
echo Starting Search UI on port 18888...
start "Jarvis Search" /min "%PYTHON%" "%SEARCH_SCRIPT%"
echo   Search UI starting in background window...
goto done

:start_both
call :start_search
timeout /t 2 /nobreak >nul
call :start_agent
goto done

:restart_both
echo Restarting both servers...
call :stop_both
timeout /t 3 /nobreak >nul
call :start_both
goto done

:status
echo.
echo --- Server Status ---
echo.
set AGENT_RUNNING=NO
set SEARCH_RUNNING=NO
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18889.*LISTEN" 2^>nul') do set AGENT_RUNNING=YES (PID %%a)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18888.*LISTEN" 2^>nul') do set SEARCH_RUNNING=YES (PID %%a)
echo   Agent    (18889): %AGENT_RUNNING%
echo   Search UI (18888): %SEARCH_RUNNING%
echo.
goto done

:done
echo.
pause
goto menu
