@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-options-demo.ps1" %*
if errorlevel 1 (
  echo.
  echo Options demo did not start. Read the error above.
  pause
  exit /b 1
)
