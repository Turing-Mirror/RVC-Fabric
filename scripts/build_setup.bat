@echo off
setlocal
cd /d "%~dp0.."
echo === build RVC Fabric Setup (Inno Setup) ===
echo Requires: Inno Setup 6  https://jrsoftware.org/isinfo.php
python scripts\build_setup.py %*
set ERR=%ERRORLEVEL%
if %ERR% equ 2 (
  echo.
  echo Payload ready but ISCC missing. Install Inno Setup 6, then re-run.
  exit /b 2
)
if %ERR% neq 0 exit /b %ERR%
echo.
echo Output: dist\RVC_Fabric_Setup.exe
echo Optional: python scripts\build_setup.py --copy-cnb
exit /b 0
