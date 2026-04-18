@echo off
title Stopping Jarvis Servers...

echo Stopping Agent (port 18889)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18889.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   Stopped PID %%a
)

echo Stopping Search UI (port 18888)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":18888.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   Stopped PID %%a
)

echo.
echo Both servers stopped.
timeout /t 3
