@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
where conda >nul 2>nul
if errorlevel 1 (
  echo Open an Anaconda Prompt, then run this script again.
  echo Required environment: chem-agent
  pause
  exit /b 1
)
call conda run --no-capture-output -n chem-agent python app.py
set "CHEM_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %CHEM_EXIT_CODE%
