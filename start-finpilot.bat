@echo off
setlocal EnableExtensions
chcp 65001 >nul
title FinPilot
if /i "%~1"=="--install" (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-finpilot.ps1" -Install
) else (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-finpilot.ps1" %*
)
set "FINPILOT_EXIT=%errorlevel%"
if not "%FINPILOT_EXIT%"=="0" pause
exit /b %FINPILOT_EXIT%
