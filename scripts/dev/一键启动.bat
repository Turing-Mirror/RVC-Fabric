@echo off
REM Keep this file mostly ASCII so cmd never mangles Chinese names.
cd /d "%~dp0"

if exist "%~dp0start.bat" (
  call "%~dp0start.bat"
  exit /b %errorlevel%
)

wscript //nologo "%~dp0launcher\run_hidden.vbs" bootstrap
if errorlevel 1 pause
exit /b %errorlevel%
