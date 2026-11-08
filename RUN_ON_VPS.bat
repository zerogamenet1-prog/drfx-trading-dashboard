@echo off
setlocal enabledelayedexpansion
title NEXUS QUANT PRO - 1-Click VPS Launcher
cd /d "%~dp0"

echo ===================================================================
echo     🧬 NEXUS QUANT PRO - 1-CLICK ALL-IN-ONE VPS LAUNCHER
echo     Dashboard + Real MT5 Live Auto-Sync + Global HTTPS Tunnel
echo ===================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ไม่พบโปรแกรม Python บนเครื่อง VPS นี้
    echo [i] กำลังดาวน์โหลดและติดตั้ง Python ให้อัตโนมัติ กรุณารอสักครู่...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile 'python_installer.exe'}"
    if exist python_installer.exe (
        echo [i] กำลังติดตั้ง Python แบบ Silent...
        start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
        del python_installer.exe
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
    ) else (
        echo [X] ไม่สามารถดาวน์โหลด Python ได้ กรุณาติดตั้ง Python จาก python.org ด้วยตนเอง
        pause
        exit /b 1
    )
)

echo [+] ตรวจพบ Python:
python --version
echo.

:: 2. Install required packages
echo [*] ตรวจสอบและอัปเดต Library ที่จำเป็น (FastAPI, MetaTrader5, Uvicorn ฯลฯ)...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo [+] ตรวจสอบ Library เรียบร้อยแล้ว!
echo.

:: 3. Launch Backend Server
echo [*] กำลังเริ่มทำงาน Backend Server (Port 8000)...
start "NEXUS QUANT - Backend Server" /min python -m uvicorn server:app --host 127.0.0.1 --port 8000
timeout /t 2 /nobreak >nul

:: 4. Launch Smart MT5 Auto Synchronizer
echo [*] กำลังเริ่มทำงาน Smart MT5 Auto Synchronizer...
start "NEXUS QUANT - MT5 Real Synchronizer" /min python -u sync_real_mt5.py
timeout /t 1 /nobreak >nul

:: 5. Launch Cloudflare Public Tunnel
echo.
echo ===================================================================
echo   🌐 กำลังเชื่อมต่อ Cloudflare Tunnel สำหรับเปิดดูผ่านมือถือจากทั่วโลก...
echo ===================================================================
echo.
echo [คำแนะนำ] 
echo  - เมื่อได้ Public URL ด้านล่างแล้ว สามารถ Copy ไปเปิดดูในมือถือได้ทันที
echo  - สามารถย่อหน้าต่างนี้ลงได้ (ห้ามกดปิดกากบาท เพื่อให้ระบบออนไลน์ตลอดเวลา)
echo.

cloudflared.exe tunnel --url http://127.0.0.1:8000
pause
