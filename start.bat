@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe app.py
) else (
  where uv >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.11-3.13 and uv, then run: uv sync --locked
    pause
    exit /b 1
  )
  uv sync --locked --no-dev
  if errorlevel 1 exit /b 1
  uv run --no-sync python app.py
)
pause
