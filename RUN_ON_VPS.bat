@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title NEXUS QUANT PRO - VPS Launcher
cd /d "%~dp0"

echo ========================================================================
echo   🧬 NEXUS QUANT PRO - INITIALIZING SYSTEM...
echo ========================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ตรวจสอบ: ยังไม่พบโปรแกรม Python บนเครื่องนี้
    echo [*] กำลังดาวน์โหลดและติดตั้ง Python ให้อัตโนมัติ (กรุณารอสักครู่)...
    powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile 'python_installer.exe'"
    if exist python_installer.exe (
        echo [*] กำลังติดตั้ง Python แบบ Silent Install...
        start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
        del python_installer.exe >nul 2>&1
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
    ) else (
        echo [X] ดาวน์โหลดไม่สำเร็จ กรุณาติดตั้ง Python 3.12 ด้วยตนเอง
        pause
        exit /b 1
    )
)

:: 2. Check & Install Requirements quietly
echo [*] กำลังตรวจสอบความพร้อมของระบบ (FastAPI, MetaTrader5, WebSockets)...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check

:: 3. Run Beautiful Launcher Dashboard
cls
python launcher.py

pause
