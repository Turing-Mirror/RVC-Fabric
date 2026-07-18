@echo off
chcp 65001 >nul
call "%~dp0_env.bat"
if not defined PY (
  echo [ERROR] No Runtime. Run scripts\sync_from_rvcmax.bat
  pause
  exit /b 1
)
title RVC WebUI DML (DEV)
set PORT=7897
"%PY%" infer-web.py --pycmd "%PY%" --port %PORT% --dml
pause
