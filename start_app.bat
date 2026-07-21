@echo off
REM Silent hand-off to OpenApp.vbs (no lingering console). Double-click OpenApp.vbs for zero flash.
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "%CD%\OpenApp.vbs" (
  echo Missing OpenApp.vbs
  pause
  exit /b 1
)
REM Re-launch via hidden wscript so this cmd window can exit immediately
> "%TEMP%\tm_open_app.vbs" echo CreateObject("Wscript.Shell").Run "wscript.exe //nologo ""%CD%\OpenApp.vbs""", 0, False
wscript //nologo "%TEMP%\tm_open_app.vbs"
exit /b 0
