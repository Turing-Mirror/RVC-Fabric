@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0..\.."
title RVC Fabric · smoke tests

echo === 1) 环境检查 ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_test_env.ps1"
set ENVERR=%errorlevel%
echo.

echo === 2) Python 单元测试（宿主 python，非 Runtime）===
python -m unittest discover -s tests -p "test_*.py" -v
set PYERR=%errorlevel%
echo.

echo === 3) Rust 单元测试（app/src-tauri）===
if defined TM_VCVARS if exist "%TM_VCVARS%" goto :vc
if exist "F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" set "TM_VCVARS=F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
:vc
if defined TM_VCVARS call "%TM_VCVARS%" >nul
REM 不强制 CARGO_TARGET_DIR（错误带空格的值会让 cargo 直接失败）
set "CARGO_TARGET_DIR="
pushd app\src-tauri
cargo test
set RSERR=%errorlevel%
popd
echo.

echo === 汇总 ===
echo 环境检查 exit=%ENVERR%  (0=全就绪 2=dev缺 3=setup缺)
echo Python   exit=%PYERR%
echo Rust     exit=%RSERR%
if not %PYERR%==0 exit /b %PYERR%
if not %RSERR%==0 exit /b %RSERR%
if %ENVERR%==2 exit /b 2
echo 烟雾测试脚本段通过。请继续人工清单 TEST_CHECKLIST.md
exit /b 0
