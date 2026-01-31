@echo off
title Delete Logs folder
cd /d "%~dp0"
echo Closing any handles to Logs... (run this after closing Cursor/IDE and any bot)
timeout /t 2 /nobreak >nul
rd /s /q Logs 2>nul
if exist Logs (
    echo Some files still in use. Close Cursor and any "python run.py" window, then run this again.
    pause
    exit /b 1
)
echo Logs folder deleted.
pause
