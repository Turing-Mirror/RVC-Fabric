@echo off
chcp 65001 >nul
call "%~dp0_env.bat"
if not defined PY (
  echo [ERROR] No Runtime. Run scripts\sync_from_rvcmax.bat
  pause
  exit /b 1
)
title RVC realtime GUI DML (DEV)
REM Official AMD/Intel path: gui uses Config --dml / torch_directml
set TM_USE_DML=1
set TM_ACCEL=dml
"%PY%" gui_v1.py --dml
pause
