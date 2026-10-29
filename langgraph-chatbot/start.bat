@echo off
chcp 65001 >nul
title Xiaoshu Chatbot
cd /d "%~dp0"

curl -s -o nul --max-time 2 http://127.0.0.1:8000/api/health
if errorlevel 1 goto :boot
echo.
echo   Xiaoshu is already running. Opening browser...
start "" http://127.0.0.1:8000
exit /b 0

:boot
if exist ".venv\Scripts\python.exe" goto :run

echo.
echo   [1/3] First run - creating virtual environment...
python -m venv .venv
if errorlevel 1 goto :nopython

echo   [2/3] Installing dependencies, may take a few minutes...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt
if errorlevel 1 goto :pipfail
echo   [3/3] Done.

:run
echo.
echo   Starting Xiaoshu ... browser will open automatically.
echo   Press Ctrl+C to stop this window.
echo.
.venv\Scripts\python.exe run.py
echo.
echo   Service stopped.
pause
exit /b 0

:nopython
echo.
echo   [ERROR] Python not found.
echo   Install Python 3.10+ from https://www.python.org/downloads/
echo   Remember to check "Add Python to PATH" during installation.
pause
exit /b 1

:pipfail
echo.
echo   [ERROR] Dependency installation failed. Check your network.
pause
exit /b 1
