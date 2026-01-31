@echo off
title SpidyCrawler - One-Click Run
cd /d "%~dp0"

REM Auto setup: try python, then py -3 (no delayed expansion - works everywhere)
python --version >nul 2>&1
if not errorlevel 1 goto run_python
py -3 --version >nul 2>&1
if not errorlevel 1 goto run_py
echo Python not found. Install Python 3.8+ from https://python.org and add to PATH.
echo Or install "py" via Windows Store / python.org installer.
pause
exit /b 1

:run_python
echo First run? Dependencies and proxies will download automatically.
echo.
python run.py
goto end

:run_py
echo First run? Dependencies and proxies will download automatically.
echo.
py -3 run.py
goto end

:end
pause
