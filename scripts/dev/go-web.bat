@echo off
chcp 65001 >nul
call "%~dp0_env.bat"
if not defined PY (
  echo [ERROR] No Runtime python. Run: scripts\sync_from_rvcmax.bat
  pause
  exit /b 1
)
title RVC WebUI (DEV via Runtime)
set PORT=7897
echo Using: %PY%
echo WebUI http://127.0.0.1:%PORT%
"%PY%" infer-web.py --pycmd "%PY%" --port %PORT%
pause
