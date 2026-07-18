@echo off
REM No-flash path: hand off to VBS (user desktop). Bat only reports errors.
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "%CD%\OpenApp.vbs" (
  echo Missing OpenApp.vbs
  pause
  exit /b 1
)
wscript //nologo "%CD%\OpenApp.vbs"
if errorlevel 1 (
  echo Launch failed.
  if exist "%CD%\TEMP\last_launch.log" type "%CD%\TEMP\last_launch.log"
  pause
  exit /b 1
)
exit /b 0
