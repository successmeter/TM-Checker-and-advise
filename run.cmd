@echo off
rem Start BizImprint locally: stops any server already using port 8000, gets the latest code, then starts.
rem   run        the site as customers see it: free summary, then the order form and Stripe payment
rem   run full   every result and explanation free on the page, for testing the checks
cd /d "%~dp0"
rem Update first, then start again from the updated copy of this file (cmd reads a batch file as it runs).
if not "%~2"=="updated" (
  git pull
  "%~f0" "%~1" updated
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
py -m pip install -e . --quiet
set TM_FREE_FULL=
if /i "%~1"=="full" set TM_FREE_FULL=1
if "%TM_FREE_FULL%"=="1" (echo Mode: full results, for testing) else (echo Mode: customer view. For payments to complete, also run stripe listen in another window.)
echo.
echo Open http://127.0.0.1:8000 when it says "Uvicorn running". Press Ctrl+C to stop.
py -m uvicorn tm_advisor.api:app
