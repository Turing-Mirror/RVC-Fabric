@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0..\.."
title RVC Fabric - tauri dev

if not exist "app\package.json" (
  echo [错误] 当前目录不是 RVC Fabric 仓库：%CD%
  exit /b 1
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo [错误] 找不到 npm.cmd，请先安装 Node.js 或修正 PATH。
  exit /b 1
)

REM 默认使用隔离的 Cargo 缓存，避免复用其他检出目录的绝对路径。
if not defined CARGO_TARGET_DIR set "CARGO_TARGET_DIR=%TEMP%\RVC-Fabric\cargo-target"

REM 产品根 = 仓库根（paths.rs 也会自己爬；显式更稳）
set "TM_VOICE_ROOT=%CD%"
echo === RVC Fabric 开发版 ===
echo 仓库: %TM_VOICE_ROOT%
echo Cargo target: %CARGO_TARGET_DIR%
echo [env] TM_VOICE_ROOT=%TM_VOICE_ROOT%

if not exist "Runtime\pythonw.exe" (
  echo [注意] 没有 Runtime\pythonw.exe —— 界面能开，变声 worker 起不来。
  echo        需要本机已有 Runtime，或先用旧装机/补全拷一份到仓库根 Runtime\
  echo.
)

if not exist "app\node_modules\" (
  echo [app] npm install ...
  pushd app
  call npm.cmd install --no-audit --no-fund
  set "ERR=%ERRORLEVEL%"
  popd
  if not "%ERR%"=="0" exit /b %ERR%
)

echo.
echo 启动 tauri dev（关窗口或 Ctrl+C 结束）...
echo.
pushd app
call npm.cmd run tauri:dev
set ERR=%errorlevel%
popd
exit /b %ERR%
