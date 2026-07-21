@echo off
REM Silent hand-off to OpenSetup.vbs (no lingering console). Double-click OpenSetup.vbs for zero flash.
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "%CD%\OpenSetup.vbs" (
  echo Missing OpenSetup.vbs
  pause
  exit /b 1
)
> "%TEMP%\tm_open_setup.vbs" echo CreateObject("Wscript.Shell").Run "wscript.exe //nologo ""%CD%\OpenSetup.vbs""", 0, False
wscript //nologo "%TEMP%\tm_open_setup.vbs"
exit /b 0
