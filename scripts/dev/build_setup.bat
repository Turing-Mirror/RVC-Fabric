@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
title RVC Fabric build Setup

echo === Build RVC_Fabric_Setup.exe ===
echo Repo: %CD%
echo.

if exist "F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS (
  echo [ERROR] vcvars64.bat not found
  exit /b 1
)
echo [env] %TM_VCVARS%
call "%TM_VCVARS%"
if errorlevel 1 (
  echo [ERROR] vcvars failed
  exit /b 1
)
set "CARGO_TARGET_DIR="

if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [ERROR] ISCC.exe not found
  exit /b 1
)
echo [env] ISCC=%ISCC%
echo.

python scripts\build_setup.py --clean %*
set ERR=%errorlevel%
if not %ERR%==0 (
  echo [FAIL] build_setup exit %ERR%
  exit /b %ERR%
)

echo.
echo === outputs ===
dir /b dist\RVC_Fabric_Setup.exe 2>nul
dir /b "dist\RVC_Fabric_Setup_payload\RVC Fabric.exe" 2>nul
dir /b "dist\RVC_Fabric_Setup_payload\frontend\index.html" 2>nul
exit /b 0