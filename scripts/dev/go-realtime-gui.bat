@echo off
chcp 65001 >nul
call "%~dp0_env.bat"
if not defined PY (
  echo [ERROR] No Runtime. Run scripts\sync_from_rvcmax.bat
  pause
  exit /b 1
)
title RVC realtime GUI (DEV)
"%PY%" gui_v1.py
pause
