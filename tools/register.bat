@echo off
setlocal
REM ============================================================
REM Script:  register.bat
REM Purpose: Registers this kit in the machine-wide .rad hub by
REM          calling the workspace's own rad.ps1 through the hub
REM          root's symlink -- this kit carries no registration
REM          logic of its own, it only knows how to find and call
REM          the shared one.
REM Usage:   register.bat [-Unregister] [-Name <custom-name>]
REM ============================================================

set "KIT_ROOT=%~dp0.."

if not exist "%ProgramData%\rad\rad.ps1" (
  echo Hub kurulu degil.
  exit /b 1
)

pwsh -NoProfile -File "%ProgramData%\rad\rad.ps1" -Action Register -KitPath "%KIT_ROOT%" %*
