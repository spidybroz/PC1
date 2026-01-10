@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title SEO Bot Launcher

REM Get the directory where this batch file is located
set "PROJECT_ROOT=%~dp0"
REM Remove trailing backslash
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "REQUIREMENTS_PATH=%PROJECT_ROOT%\source\requirements.txt"
set "BOT_SCRIPT_PATH=%PROJECT_ROOT%\source\SC_BOT.py"
set "CUSTOMIZE_DIR=%PROJECT_ROOT%\customize"
set "PYTHON_VERSION=3.11.4"
set "TEMP_DIR=%TEMP%\SC_BOT_setup"
set "LOG_FILE=%TEMP_DIR%\installation.log"

echo ========================================
echo           SEO Bot Launcher
echo ========================================
echo.
echo Project Location: %PROJECT_ROOT%
echo.

REM Create temp directory for logs and downloads
if not exist "%TEMP_DIR%" (
    mkdir "%TEMP_DIR%" >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Cannot create temporary directory: %TEMP_DIR%
        pause
        exit /b 1
    )
)

REM Function to log messages
set "LOG=>> "%LOG_FILE%" 2>&1 echo [%date% %time%]"
%LOG% Starting SEO Bot Launcher
%LOG% Project Root: %PROJECT_ROOT%

REM Check if project structure exists
echo Checking project structure...
if not exist "%PROJECT_ROOT%" (
    echo ERROR: Project root not found: %PROJECT_ROOT%
    %LOG% ERROR: Project root not found
    pause
    exit /b 1
)

REM Check if required files exist
echo Checking required files...
if not exist "%REQUIREMENTS_PATH%" (
    echo ERROR: Requirements file not found at: %REQUIREMENTS_PATH%
    %LOG% ERROR: Requirements file not found
    pause
    exit /b 1
)

if not exist "%BOT_SCRIPT_PATH%" (
    echo ERROR: Bot script not found at: %BOT_SCRIPT_PATH%
    %LOG% ERROR: Bot script not found
    pause
    exit /b 1
)

REM Check if customize folder and files exist
echo Checking configuration files...
if not exist "%CUSTOMIZE_DIR%\" (
    echo ERROR: Customize folder not found at: %CUSTOMIZE_DIR%
    echo Please create the customize folder with urls.txt and spend_time.txt
    %LOG% ERROR: Customize folder not found
    pause
    exit /b 1
)

if not exist "%CUSTOMIZE_DIR%\urls.txt" (
    echo ERROR: urls.txt not found in customize folder
    echo Please create %CUSTOMIZE_DIR%\urls.txt with your target URLs
    %LOG% ERROR: urls.txt not found
    pause
    exit /b 1
)

if not exist "%CUSTOMIZE_DIR%\spend_time.txt" (
    echo ERROR: spend_time.txt not found in customize folder
    echo Please create %CUSTOMIZE_DIR%\spend_time.txt with visit duration in seconds
    %LOG% ERROR: spend_time.txt not found
    pause
    exit /b 1
)

echo Required files and folders found.
%LOG% Project structure verified

REM Check if Python is installed and accessible
echo Checking Python installation...
python --version >nul 2>&1
set "PYTHON_CHECK=%errorlevel%"

if !PYTHON_CHECK! equ 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION_INSTALLED=%%i"
    echo Python found: !PYTHON_VERSION_INSTALLED!
    %LOG% Python found: !PYTHON_VERSION_INSTALLED!
    goto CHECK_REQUIREMENTS
)

echo.
echo ========================================
echo        Python Installation Required
echo ========================================
echo.
echo ERROR: Python !PYTHON_VERSION! or higher is required but not found.
echo.
echo Please install Python !PYTHON_VERSION! or higher from:
echo https://www.python.org/downloads/
echo.
echo After installation, make sure to:
echo 1. Check "Add Python to PATH" during installation
echo 2. Restart your command prompt
echo 3. Run this script again
echo.
%LOG% ERROR: Python !PYTHON_VERSION! required but not found
pause
exit /b 1

:CHECK_REQUIREMENTS
echo.
echo ========================================
echo    Checking Python Requirements
echo ========================================
echo.

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip not found. Please ensure Python installation includes pip.
    %LOG% ERROR: pip not found
    pause
    exit /b 1
)

echo Checking if requirements are already installed...
%LOG% Checking existing requirements installation

REM Quick check if main packages are already installed
python -c "import selenium, fake_useragent" >nul 2>&1
if !errorlevel! equ 0 (
    echo [SKIPPED] Requirements already installed.
    %LOG% Requirements already installed - skipping
    goto REQUIREMENTS_DONE
)

echo [INSTALLING] Packages not found. Installing requirements...
%LOG% Starting requirements installation
pip install --upgrade pip >nul 2>&1

echo Installing packages from requirements.txt...
pip install -r "%REQUIREMENTS_PATH%"

if errorlevel 1 (
    echo ERROR: Failed to install some requirements.
    echo Please check the requirements.txt file and your internet connection.
    %LOG% ERROR: Requirements installation failed
    echo.
    echo You can try installing manually with: pip install -r "%REQUIREMENTS_PATH%"
    pause
    exit /b 1
)

echo [SUCCESS] Requirements installed successfully.
%LOG% Requirements installed successfully

:REQUIREMENTS_DONE

REM Display configuration info
echo.
echo ========================================
echo    Configuration Summary
echo ========================================
echo Project Root:    %PROJECT_ROOT%
echo Bot Script:      %BOT_SCRIPT_PATH%
echo Customize Files: %CUSTOMIZE_DIR%
echo Logs Directory:  %PROJECT_ROOT%\Logs
echo.

REM Verify configuration files content
echo Verifying configuration files...
set "URLS_COUNT=0"
for /f "usebackq delims=" %%i in ("%CUSTOMIZE_DIR%\urls.txt") do (
    if not "%%i"=="" if not "%%i"==" " (
        set /a URLS_COUNT+=1
        if !URLS_COUNT! equ 1 (
            echo First URL: %%i
        )
    )
)

set "DURATION=0"
for /f "usebackq tokens=*" %%i in ("%CUSTOMIZE_DIR%\spend_time.txt") do (
    for /f "tokens=*" %%j in ("%%i") do (
        set "DURATION=%%j"
        goto :DURATION_FOUND
    )
)
:DURATION_FOUND

echo URLs Found:      !URLS_COUNT!
echo Visit Duration:  !DURATION! seconds
echo.

REM Create Logs directory if it doesn't exist
if not exist "%PROJECT_ROOT%\Logs" (
    mkdir "%PROJECT_ROOT%\Logs" >nul 2>&1
    echo Created Logs directory
)

REM Run the bot
echo ========================================
echo          Starting SEO Bot
echo ========================================
echo.
%LOG% Starting SEO bot

echo Running: python "%BOT_SCRIPT_PATH%"
echo Bot is starting... This may take a moment.
echo.

python "%BOT_SCRIPT_PATH%"

set "BOT_EXIT_CODE=%errorlevel%"
%LOG% SEO bot exited with code: %BOT_EXIT_CODE%

echo.
if %BOT_EXIT_CODE% equ 0 (
    echo ========================================
    echo    SEO Bot Finished Successfully!
    echo ========================================
    %LOG% SEO bot finished successfully
) else (
    echo ========================================
    echo    SEO Bot Finished with Errors
    echo ========================================
    echo Exit code: %BOT_EXIT_CODE%
    %LOG% SEO bot finished with error code: %BOT_EXIT_CODE%
)

echo.
echo Project Location: %PROJECT_ROOT%
echo Logs Location:    %PROJECT_ROOT%\Logs
echo Configuration:    %CUSTOMIZE_DIR%
echo Installation Log: %LOG_FILE%
echo.
echo Press any key to exit...
pause >nul

endlocal