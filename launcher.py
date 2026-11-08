"""
NEXUS QUANT PRO - High-End Console Dashboard & Service Orchestrator.
Monitors ONLY active/running MT5 terminals and presents a beautiful live terminal UI.
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = os.path.join(BASE_DIR, "cloudflared.exe")
API_URL = "http://127.0.0.1:8000/api/report"
DB_PATH = os.path.join(BASE_DIR, "dashboard.db")

sys.path.insert(0, BASE_DIR)

# Global State
PUBLIC_URL = "Connecting..."
SYNC_LOGS = []
ACTIVE_ACCOUNTS_STATUS = []

def get_running_mt5_paths():
    """Detects ONLY the MT5 terminals that are currently RUNNING on the system."""
    paths = set()
    cmd = ["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.ProcessName -match '^terminal' } | Select-Object -ExpandProperty Path"]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            line = line.strip()
            if line and os.path.isfile(line) and line.lower().endswith(".exe"):
                paths.add(line)
    except Exception:
        pass
    return sorted(list(paths))

def start_backend():
    """Starts FastAPI Uvicorn backend in background."""
    from server import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

def start_cloudflared():
    """Starts Cloudflare Tunnel and captures the public HTTPS URL."""
    global PUBLIC_URL
    if not os.path.exists(CLOUDFLARED):
        PUBLIC_URL = "Error: cloudflared.exe not found"
        return

    proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", "http://127.0.0.1:8000"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in iter(proc.stdout.readline, ''):
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if match:
            PUBLIC_URL = match.group(0)
            with open(os.path.join(BASE_DIR, "public_url.txt"), "w") as f:
                f.write(PUBLIC_URL)
            try:
                # Open browser once URL is ready
                webbrowser.open(PUBLIC_URL)
            except Exception:
                pass
            break
            
    proc.wait()

def sync_single_mt5(path):
    """Connects to a single running MT5 instance and syncs telemetry."""
    if not mt5.initialize(path=path):
        return None
    try:
        acc = mt5.account_info()
        if not acc:
            return None
            
        term_name = os.path.basename(os.path.dirname(path))
        login = acc.login
        broker = acc.company or term_name
        server = acc.server or "VPS"
        currency = acc.currency or "USD"
        balance = round(acc.balance, 2)
        equity = round(acc.equity, 2)
        floating = round(acc.profit, 2)
        
        positions = mt5.positions_get() or []
        pos_list = []
        for p in positions:
            pos_list.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "lots": round(p.volume, 2),
                "open_price": p.price_open,
                "current_price": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": round(p.profit, 2),
                "swap": round(p.swap, 2),
                "comment": p.comment or "",
                "magic": p.magic
            })
            
        now = datetime.now()
        start_date = now - timedelta(days=90)
        deals = mt5.history_deals_get(start_date, now) or []
        start_today = datetime(now.year, now.month, now.day)
        start_yesterday = start_today - timedelta(days=1)
        start_week = start_today - timedelta(days=now.weekday())
        start_month = datetime(now.year, now.month, 1)
        
        today_profit = 0.0
        yesterday_profit = 0.0
        weekly_profit = 0.0
        monthly_profit = 0.0
        closed_deals = []
        
        for d in deals:
            if d.entry in (1, 2, 3):
                d_time = datetime.fromtimestamp(d.time)
                p_val = round(d.profit + d.swap + d.commission, 2)
                if d_time >= start_today: today_profit += p_val
                elif d_time >= start_yesterday and d_time < start_today: yesterday_profit += p_val
                if d_time >= start_week: weekly_profit += p_val
                if d_time >= start_month: monthly_profit += p_val
                
                closed_deals.append({
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "type": "BUY" if d.type == 0 else "SELL",
                    "lots": round(d.volume, 2),
                    "open_price": round(d.price, 5),
                    "close_price": round(d.price, 5),
                    "profit": round(d.profit, 2),
                    "swap": round(d.swap, 2),
                    "commission": round(d.commission, 2),
                    "close_time": d_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "close_timestamp": int(d.time),
                    "comment": d.comment or "",
                    "magic": d.magic
                })

        payload = {
            "login": login,
            "name": f"{acc.name} ({term_name})",
            "broker": broker,
            "server": server,
            "currency": currency,
            "balance": balance,
            "equity": equity,
            "margin": round(acc.margin, 2),
            "free_margin": round(acc.margin_free, 2),
            "floating": floating,
            "today_profit": round(today_profit, 2),
            "yesterday_profit": round(yesterday_profit, 2),
            "weekly_profit": round(weekly_profit, 2),
            "monthly_profit": round(monthly_profit, 2),
            "open_positions": pos_list,
            "closed_deals": closed_deals[-150:]
        }
        
        try:
            requests.post(API_URL, json=payload, timeout=2)
        except Exception:
            pass
            
        return {
            "login": login,
            "name": acc.name,
            "terminal": term_name,
            "broker": broker,
            "balance": balance,
            "equity": equity,
            "floating": floating,
            "orders": len(pos_list)
        }
    finally:
        mt5.shutdown()

def sync_loop():
    """Continuously monitors ONLY running MT5 instances."""
    global ACTIVE_ACCOUNTS_STATUS, SYNC_LOGS
    
    # Clean old demo logins on startup
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM accounts WHERE login IN ('8899201', '6644109', '3311902')")
            conn.commit()
            conn.close()
        except Exception:
            pass

    while True:
        running_paths = get_running_mt5_paths()
        statuses = []
        
        if not running_paths:
            ACTIVE_ACCOUNTS_STATUS = []
            time.sleep(2)
            continue
            
        for path in running_paths:
            res = sync_single_mt5(path)
            if res:
                statuses.append(res)
            time.sleep(0.5)
            
        ACTIVE_ACCOUNTS_STATUS = statuses
        
        ts = time.strftime("%H:%M:%S")
        if statuses:
            total_orders = sum(s["orders"] for s in statuses)
            SYNC_LOGS.append(f"[{ts}] OK: {len(statuses)} Port(s) synced ({total_orders} Orders in market)")
        else:
            SYNC_LOGS.append(f"[{ts}] Standby: MT5 detected but not ready...")
            
        if len(SYNC_LOGS) > 5:
            SYNC_LOGS = SYNC_LOGS[-5:]
            
        time.sleep(2)

def render_ui():
    """Renders a beautiful, high-status terminal interface."""
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 72)
    print("   ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗   ██████╗ ██████╗  ██████╗ ")
    print("   ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝   ██╔══██╗██╔══██╗██╔═══██╗")
    print("   ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗   ██████╔╝██████╔╝██║   ██║")
    print("   ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║   ██╔═══╝ ██╔══██╗██║   ██║")
    print("   ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║   ██║     ██║  ██║╚██████╔╝")
    print("   ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ")
    print("            Institutional Algorithmic Trading Intelligence")
    print("=" * 72)
    print()
    print(" 🌐 PUBLIC WEB DASHBOARD URL (เปิดดูผ่านมือถือได้ทันที):")
    print(" ┌" + "─" * 70 + "┐")
    print(f" │  👉 {PUBLIC_URL:<66} │")
    print(" └" + "─" * 70 + "┘")
    print()
    
    print(" 🟢 SYSTEM MONITOR (ติดตามผลเฉพาะ MT5 ที่เปิดรันอยู่เท่านั้น):")
    print(" ──────────────────────────────────────────────────────────────────────")
    if not ACTIVE_ACCOUNTS_STATUS:
        print("  ⏳ ยังไม่พบ MT5 ที่เปิดทำงานอยู่...")
        print("     👉 กรุณาเปิดโปรแกรม MT5 บนเครื่องนี้ ระบบจะตรวจจับและซิงค์ข้อมูลให้เอง")
    else:
        for idx, acc in enumerate(ACTIVE_ACCOUNTS_STATUS, 1):
            float_sign = "+" if acc['floating'] >= 0 else ""
            print(f"  [{idx}] ⚡ {acc['name']} · #{acc['login']} ({acc['terminal']})")
            print(f"      • Balance     : ${acc['balance']:,.2f} USD")
            print(f"      • Equity (NAV): ${acc['equity']:,.2f} USD")
            print(f"      • Floating P/L: {float_sign}${acc['floating']:,.2f} USD")
            print(f"      • Active Trades: {acc['orders']} Open Position(s)")
            print()

    print(" ──────────────────────────────────────────────────────────────────────")
    print(" 📡 Live Sync Activity Log:")
    for log in (SYNC_LOGS or [" [Standby] Initializing telemetry stream..."]):
        print(f"   {log}")
    print()
    print(" 💡 [คำแนะนำ] สามารถย่อหน้าต่างนี้ลงได้ (ห้ามกดปิดกากบาท เพื่อให้ออนไลน์ 24 ชม.)")
    print("=" * 72)

if __name__ == "__main__":
    # 1. Start Backend in Thread
    t_backend = threading.Thread(target=start_backend, daemon=True)
    t_backend.start()
    time.sleep(2)
    
    # 2. Start Cloudflare Tunnel in Thread
    t_cf = threading.Thread(target=start_cloudflared, daemon=True)
    t_cf.start()
    
    # 3. Start MT5 Sync in Thread
    t_sync = threading.Thread(target=sync_loop, daemon=True)
    t_sync.start()
    
    # 4. Main Thread renders the beautiful UI every second
    try:
        while True:
            render_ui()
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\nStopping NEXUS QUANT PRO...")
