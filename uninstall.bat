@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Logifetch.ps1" -Remove
set "exitcode=%ERRORLEVEL%"

if not "%exitcode%"=="0" (
    echo.
    echo Logifetch removal failed with exit code %exitcode%.
    pause
    exit /b %exitcode%
)

echo.
echo Logifetch Scheduled Task and running agent processes were removed.
pause
