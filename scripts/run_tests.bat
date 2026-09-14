@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Turing Mirror unit tests
echo Running product unit tests (unittest discover)...
echo.
set "PY=python"
if exist "%CD%\Runtime\python.exe" set "PY=%CD%\Runtime\python.exe"
echo Using: %PY%
rem 嵌入式 Runtime 的 sys.path 没有项目根：显式加上，否则 import tools.* 的
rem 测试模块整组载入失败（审计 2026-09-14 曾因此少收一组用例）。
set "PYTHONPATH=%CD%"
"%PY%" -m unittest discover -s tests -p "test_*.py" -v
set ERR=%errorlevel%
echo.
if %ERR%==0 (
  echo ALL PASSED
) else (
  echo FAILED code=%ERR%
)
exit /b %ERR%
