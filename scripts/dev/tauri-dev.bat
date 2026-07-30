@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0..\.."
title RVC Fabric · tauri dev

echo === RVC Fabric 开发版 ===
echo 仓库: %CD%
echo.

REM --- MSVC 环境（link.exe）---
if defined TM_VCVARS if exist "%TM_VCVARS%" goto :vc_ok
if exist "F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined TM_VCVARS if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

:vc_ok
if not defined TM_VCVARS (
  echo [错误] 找不到 vcvars64.bat。请安装 VS2022 C++ 生成工具，或 set TM_VCVARS=路径\vcvars64.bat
  exit /b 1
)
echo [env] call "%TM_VCVARS%"
call "%TM_VCVARS%" >nul
if errorlevel 1 (
  echo [错误] vcvars 失败
  exit /b 1
)

REM 可选：把 cargo target 放到短路径盘，减轻 L: 路径过长问题
REM 默认用 app\src-tauri\target，避免错误的 CARGO_TARGET_DIR 带空格导致编译失败
set "CARGO_TARGET_DIR="
if exist "F:\VS2022\cargo-target\" (
  set "CARGO_TARGET_DIR=F:\VS2022\cargo-target"
  echo [env] CARGO_TARGET_DIR=%CARGO_TARGET_DIR%
)

REM 产品根 = 仓库根（paths.rs 也会自己爬；显式更稳）
set "TM_VOICE_ROOT=%CD%"
echo [env] TM_VOICE_ROOT=%TM_VOICE_ROOT%

if not exist "Runtime\pythonw.exe" (
  echo [注意] 没有 Runtime\pythonw.exe —— 界面能开，变声 worker 起不来。
  echo        需要本机已有 Runtime，或先用旧装机/补全拷一份到仓库根 Runtime\
  echo.
)

if not exist "app\node_modules\" (
  echo [app] npm install ...
  pushd app
  call npm install --no-audit --no-fund
  if errorlevel 1 ( popd & exit /b 1 )
  popd
)

echo.
echo 启动 tauri dev（关窗口或 Ctrl+C 结束）...
echo.
pushd app
call npm run tauri:dev
set ERR=%errorlevel%
popd
exit /b %ERR%
