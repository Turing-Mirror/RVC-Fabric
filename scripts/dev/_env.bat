@echo off
REM Shared: cd to repo root and set PY from Runtime (local junction or RVCMAX)
cd /d "%~dp0..\.."
set "REPO=%CD%"

set "PY="
if exist "%REPO%\Runtime\python.exe" set "PY=%REPO%\Runtime\python.exe"
if not defined PY if exist "%REPO%\runtime\python.exe" set "PY=%REPO%\runtime\python.exe"
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
if not defined PYW if exist "%REPO%\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe" (
  set "PYW=%REPO%\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe"
)
if not defined PYW if defined PY (
  REM derive pythonw next to python.exe when possible
  for %%I in ("%PY%") do if exist "%%~dpIpythonw.exe" set "PYW=%%~dpIpythonw.exe"
)
if not defined PYW set "PYW=%PY%"
