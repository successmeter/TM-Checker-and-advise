@echo off
rem Start Trademark Advisor locally: stops any server already using port 8000, gets the latest code, then starts.
rem Double-click it, or type: run
cd /d "%~dp0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
git pull
py -m pip install -e . --quiet
set TM_FREE_FULL=1
echo.
echo Open http://127.0.0.1:8000 when it says "Uvicorn running". Press Ctrl+C to stop.
py -m uvicorn tm_advisor.api:app
