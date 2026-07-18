@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Sync from RVCMAX for local bat testing
echo Sync hubert/rmvpe/ffmpeg/models/VBCABLE + Runtime junction from RVCMAX...
echo.
python scripts\sync_from_rvcmax.py %*
set ERR=%errorlevel%
if %ERR%==0 (
  echo.
  echo Done. Test without system Python:
  echo   start.bat
  echo   scripts\dev\go-web.bat
) else (
  echo Sync failed code=%ERR%
)
pause
exit /b %ERR%
