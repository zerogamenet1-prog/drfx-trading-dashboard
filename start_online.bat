@echo off
title NEXUS QUANT PRO - Full Ecosystem Launcher
cd /d "%~dp0"

echo ========================================================
echo   🧬 NEXUS QUANT PRO - ALL-IN-ONE ONLINE LAUNCHER
echo ========================================================
echo.

echo [1/3] Starting Local Backend Server (Port 8000)...
start "NEXUS QUANT - Backend Server" /min python -m uvicorn server:app --host 127.0.0.1 --port 8000

timeout /t 2 /nobreak >nul

echo [2/3] Starting Real-time MT5 Auto Synchronizer...
start "NEXUS QUANT - MT5 Real Sync" /min python -u sync_real_mt5.py

timeout /t 1 /nobreak >nul

echo [3/3] Starting Cloudflare Public Tunnel...
echo.
echo --------------------------------------------------------
echo   ระบบกำลังเชื่อมต่อ Cloudflare Tunnel...
echo   คุณสามารถนำ Public URL ไปเปิดดูบนมือถือได้ทุกที่ในโลก
echo --------------------------------------------------------
echo.

cloudflared.exe tunnel --url http://127.0.0.1:8000
