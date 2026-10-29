@echo off
chcp 65001 >nul
title Xiaoshu
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :launch

echo.
echo   First run - setting up. This takes a few minutes.
echo.
python -m venv .venv
if errorlevel 1 goto :nopython

.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements-desktop.txt
if errorlevel 1 goto :pipfail
echo   Setup complete.
echo.

:launch
start "" ".venv\Scripts\pythonw.exe" desktop.py
exit /b 0

:nopython
echo.
echo   [ERROR] Python not found.
echo   Install Python 3.10+ from https://www.python.org/downloads/
echo   Check "Add Python to PATH" during installation.
pause
exit /b 1

:pipfail
echo.
echo   [ERROR] Dependency installation failed. Check your network.
pause
exit /b 1
