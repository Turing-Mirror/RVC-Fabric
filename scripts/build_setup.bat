@echo off
setlocal
cd /d "%~dp0.."
echo === build RVC Fabric Setup (thin, no Runtime) ===
python scripts\build_setup.py %*
if errorlevel 1 exit /b 1
echo.
echo Output: dist\RVC_Fabric_Setup\
echo Optional: python scripts\build_setup.py --copy-cnb
exit /b 0
