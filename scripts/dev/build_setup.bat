@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0..\.."
title RVC Fabric · build Setup

echo === 打 RVC_Fabric_Setup.exe（Tauri 薄包）===
echo 仓库: %CD%
echo.

REM MSVC（cargo tauri build 需要）
if defined TM_VCVARS if exist "%TM_VCVARS%" goto :vc_ok
if exist "F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
:vc_ok
if not defined TM_VCVARS (
  echo [错误] 找不到 vcvars64.bat
  exit /b 1
)
echo [env] call "%TM_VCVARS%"
call "%TM_VCVARS%" >nul
set "CARGO_TARGET_DIR="
if exist "F:\VS2022\cargo-target\" set "CARGO_TARGET_DIR=F:\VS2022\cargo-target"

REM Inno Setup
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [错误] 找不到 ISCC.exe。安装 Inno Setup 6 或 set ISCC=...\ISCC.exe
  exit /b 1
)
echo [env] ISCC=%ISCC%
echo.

REM 默认 --clean 避免沿用旧 Tk payload
python scripts\build_setup.py --clean %*
set ERR=%errorlevel%
if not %ERR%==0 (
  echo.
  echo [失败] build_setup 退出码 %ERR%
  exit /b %ERR%
)

echo.
echo === 产物 ===
if exist "dist\RVC_Fabric_Setup.exe" (
  for %%A in ("dist\RVC_Fabric_Setup.exe") do echo   %%~fA  %%~zA bytes
) else (
  echo   [警告] 未找到 dist\RVC_Fabric_Setup.exe
)
if exist "dist\RVC_Fabric_Setup_payload\RVC Fabric.exe" (
  echo   payload: dist\RVC_Fabric_Setup_payload\
)
echo.
echo 全流程测法见 scripts\dev\TEST_CHECKLIST.md §B
exit /b 0
