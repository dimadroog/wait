@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo venv not found — run scripts\setup_venv.ps1
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" scripts\operator_launcher.py %*
exit /b 0
