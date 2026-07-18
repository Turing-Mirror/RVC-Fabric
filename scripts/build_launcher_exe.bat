@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Redirect to full release build
echo 请使用完整发行打包（含 Runtime / 模型 / VBCABLE / exe）:
echo.
echo   scripts\build_release.bat
echo.
echo 或:
echo   python scripts\build_release.py --clean
echo.
pause
