@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Build RVC-Fabric RELEASE

echo ============================================
echo  一键打包发行版 - Turing Mirror 变声器
echo  输出: dist\RVC-Fabric\
echo  含: 启动器.exe 变声器.exe Runtime 模型 VBCABLE
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 需要本机 Python 仅用于打包机，用户端不需要。
  pause
  exit /b 1
)

REM 默认从参考包拉 Runtime / 模型 / VBCABLE（若存在）
set "REF=RVCMAX\RVCMAX_Nvidia_xiaoyuan"
set "RT="
set "MD="
set "VB="
if exist "%REF%\Runtime\python.exe" set "RT=%REF%\Runtime"
if exist "%REF%\User_Data\models" set "MD=%REF%\User_Data\models"
if exist "%REF%\VBCABLE\VBCABLE_Setup_x64.exe" set "VB=%REF%\VBCABLE"

set "ARGS=--clean"
if defined RT set "ARGS=%ARGS% --runtime %RT%"
if defined MD set "ARGS=%ARGS% --models %MD%"
if defined VB set "ARGS=%ARGS% --vbcable %VB%"

echo Runtime source: %RT%
echo Models source:  %MD%
echo VBCABLE source: %VB%
echo.

python scripts\build_release.py %ARGS%
set ERR=%errorlevel%
echo.
if %ERR%==0 (
  echo 完成。发给用户: dist\RVC-Fabric\  整个文件夹（可再压 7z）
  echo 用户只双击 启动器.exe ，再装虚拟声卡即可。
) else (
  echo 打包失败 code=%ERR%
)
pause
exit /b %ERR%
