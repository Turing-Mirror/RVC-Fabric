@echo off
REM Shared: cd to repo root and set PY from Runtime (local junction or RVCMAX)
REM Variant: TM_VARIANT env, or User_Data\dev_variant.txt (nvidia|amd|nvidia50)
cd /d "%~dp0..\.."
set "REPO=%CD%"

REM --- resolve pack folder for fallback when no Runtime\ junction ---
set "TM_PACK="
if not defined TM_VARIANT if exist "%REPO%\User_Data\dev_variant.txt" (
  set /p TM_VARIANT=<"%REPO%\User_Data\dev_variant.txt"
)
if /i "%TM_VARIANT%"=="amd" set "TM_PACK=RVCMAX_AMD_xiaoyuan"
if /i "%TM_VARIANT%"=="nvidia50" set "TM_PACK=RVCMAX_Nvidia50x0_xiaoyuan"
if /i "%TM_VARIANT%"=="nvidia" set "TM_PACK=RVCMAX_Nvidia_xiaoyuan"
if not defined TM_PACK set "TM_PACK=RVCMAX_Nvidia_xiaoyuan"

set "PY="
if exist "%REPO%\Runtime\python.exe" set "PY=%REPO%\Runtime\python.exe"
if not defined PY if exist "%REPO%\runtime\python.exe" set "PY=%REPO%\runtime\python.exe"
if not defined PY if exist "%REPO%\RVCMAX\%TM_PACK%\Runtime\python.exe" (
  set "PY=%REPO%\RVCMAX\%TM_PACK%\Runtime\python.exe"
)
if not defined PY if exist "%REPO%\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe" (
  set "PY=%REPO%\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe"
)
if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 set "PY=python"
)

set "PYW="
if exist "%REPO%\Runtime\pythonw.exe" set "PYW=%REPO%\Runtime\pythonw.exe"
if not defined PYW if exist "%REPO%\runtime\pythonw.exe" set "PYW=%REPO%\runtime\pythonw.exe"
if not defined PYW if exist "%REPO%\RVCMAX\%TM_PACK%\Runtime\pythonw.exe" (
  set "PYW=%REPO%\RVCMAX\%TM_PACK%\Runtime\pythonw.exe"
)
if not defined PYW if defined PY (
  REM derive pythonw next to python.exe when possible
  for %%I in ("%PY%") do if exist "%%~dpIpythonw.exe" set "PYW=%%~dpIpythonw.exe"
)
if not defined PYW set "PYW=%PY%"

REM AMD pack: default DirectML env for official go-*-dml style (overridden by dml bats)
if /i "%TM_VARIANT%"=="amd" (
  if not defined TM_ACCEL set "TM_ACCEL=dml"
  if not defined TM_USE_DML set "TM_USE_DML=1"
)
