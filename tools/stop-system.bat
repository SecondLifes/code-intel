@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%stop-system.ps1"

if not exist "%PS1%" (
  echo stop-system.ps1 bulunamadi:
  echo %PS1%
  exit /b 1
)

where pwsh >nul 2>nul
if %errorlevel%==0 (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
  exit /b %errorlevel%
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
exit /b %errorlevel%
