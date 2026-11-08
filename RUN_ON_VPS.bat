@echo off
setlocal enabledelayedexpansion
title NEXUS QUANT PRO - 1-Click VPS Launcher
cd /d "%~dp0"

echo ========================================================================
echo   NEXUS QUANT PRO - 1-CLICK ALL-IN-ONE VPS LAUNCHER
echo ========================================================================
echo.

:: 1. Detect Python
set "PY_CMD=python"
python --version >nul 2>&1
if %errorlevel% equ 0 goto :PYTHON_READY

:: Check standard Python install directories
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
    goto :PYTHON_READY
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PY_CMD=%ProgramFiles%\Python312\python.exe"
    set "PATH=%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%PATH%"
    goto :PYTHON_READY
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    goto :PYTHON_READY
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set "PY_CMD=%ProgramFiles%\Python311\python.exe"
    set "PATH=%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts;%PATH%"
    goto :PYTHON_READY
)

:: 2. If python_installer.exe already exists, run it
if exist "python_installer.exe" (
    echo [*] Found existing python_installer.exe.
    echo [*] Installing Python 3.12 (Please wait 30-60 seconds)...
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    del python_installer.exe >nul 2>&1
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
    goto :CHECK_AFTER_INSTALL
)

:: 3. Download Python 3.12 installer fast
echo [!] Python is not found on this system.
echo [*] Downloading Python 3.12 official installer (approx 25 MB)...
echo [*] Downloading fast, please wait...

where curl >nul 2>&1
if %errorlevel% equ 0 (
    curl -L -s -o python_installer.exe https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
) else (
    powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe', 'python_installer.exe')"
)

if exist python_installer.exe (
    echo [*] Python installer downloaded successfully.
    echo [*] Installing Python 3.12 in silent mode...
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    del python_installer.exe >nul 2>&1
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
) else (
    echo [ERROR] Failed to download Python. Please install Python 3.12 manually from python.org
    pause
    exit /b 1
)

:CHECK_AFTER_INSTALL
python --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%ProgramFiles%\Python312\python.exe" set "PY_CMD=%ProgramFiles%\Python312\python.exe"
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

:PYTHON_READY
echo [+] Python detected:
%PY_CMD% --version
echo.

:: 4. Verify & Install required packages
echo [*] Checking dependencies (FastAPI, MetaTrader5, Uvicorn, WebSockets)...
%PY_CMD% -m pip install -r requirements.txt --quiet --disable-pip-version-check

:: 5. Launch System
if exist "launcher.py" (
    cls
    %PY_CMD% launcher.py
) else (
    echo [!] Notice: launcher.py not found in this folder.
    echo [*] Launching Server and Sync directly...
    start "NEXUS QUANT PRO - Server" %PY_CMD% server.py
    start "NEXUS QUANT PRO - MT5 Sync" %PY_CMD% sync_real_mt5.py
    if exist "cloudflared.exe" (
        start "NEXUS QUANT PRO - Public Tunnel" cloudflared.exe tunnel --url http://127.0.0.1:8000
    )
    echo [+] All services started! Open http://127.0.0.1:8000 in your browser.
)

pause
