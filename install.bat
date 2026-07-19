@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Logifetch.ps1"
set "exitcode=%ERRORLEVEL%"

if not "%exitcode%"=="0" (
    echo.
    echo Logifetch installation failed with exit code %exitcode%.
    pause
    exit /b %exitcode%
)

echo.
echo Logifetch installation completed.
pause