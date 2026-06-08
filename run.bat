@echo off
REM ============================================================
REM  Mihon Extension Builder - one-click launcher (Windows)
REM  Double-click this file, or run it from a terminal.
REM  It sets up everything the first time, then opens the wizard.
REM ============================================================
setlocal
cd /d "%~dp0"

REM 1. Find Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on your PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo         and tick "Add Python to PATH" during setup.
    pause
    exit /b 1
)

REM 2. Create the virtual environment on first run
if not exist ".venv\Scripts\python.exe" (
    echo First-time setup: creating an isolated environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
    echo Installing dependencies ^(this happens only once^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
)

REM 3. Launch the wizard (or pass through any CLI args)
".venv\Scripts\python.exe" main.py %*

echo.
pause
endlocal
