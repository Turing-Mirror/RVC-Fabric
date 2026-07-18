@echo off
REM Launch main app in the interactive user desktop session
cd /d "%~dp0..\.."
set "REPO=%CD%"
set "PYTHONPATH=%REPO%"

if exist "%REPO%\Runtime\pythonw.exe" (
  start "" "%REPO%\Runtime\pythonw.exe" "%REPO%\launcher\main_app.py"
  exit /b 0
)
if exist "%REPO%\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe" (
  start "" "%REPO%\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe" "%REPO%\launcher\main_app.py"
  exit /b 0
)
if exist "%REPO%\TM_Voice.exe" (
  start "" "%REPO%\TM_Voice.exe"
  exit /b 0
)
start "" pythonw "%REPO%\launcher\main_app.py"
