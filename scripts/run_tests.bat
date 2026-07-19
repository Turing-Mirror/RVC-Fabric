@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Turing Mirror unit tests
echo Running product unit tests (unittest discover)...
echo.
python -m unittest discover -s tests -p "test_*.py" -v
set ERR=%errorlevel%
echo.
if %ERR%==0 (
  echo ALL PASSED
) else (
  echo FAILED code=%ERR%
)
exit /b %ERR%
