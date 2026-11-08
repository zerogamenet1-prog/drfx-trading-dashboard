"""
NEXUS QUANT PRO - Smart Auto-Discovering MT5 Synchronizer for VPS.
Automatically scans all MT5 terminals installed on the VPS and syncs
account balance, equity, positions, and trade history in real-time.
"""
import glob
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import requests

API_URL = "http://127.0.0.1:8000/api/report"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "dashboard.db")

def discover_mt5_terminals():
    """Auto-scans Program Files & AppData for all MT5 terminal64.exe instances."""
    terminals = set()
    
    # 1. Standard Program Files
    patterns = [
        r"C:\Program Files\*\terminal64.exe",
        r"C:\Program Files (x86)\*\terminal64.exe",
        r"D:\Program Files\*\terminal64.exe",
        r"C:\Users\*\AppData\Roaming\MetaQuotes\Terminal\*\terminal64.exe"
    ]
    for pat in patterns:
        for p in glob.glob(pat):
            if os.path.isfile(p):
                terminals.add(p)
                
    # Format list
    res = []
    for path in sorted(terminals):
        folder = os.path.basename(os.path.dirname(path))
        res.append({
            "name": folder,
            "path": path
        })
    return res

def sync_terminal(term_config):
    path = term_config["path"]
    term_name = term_config["name"]
    
    if not os.path.exists(path):
        return False
        
    if not mt5.initialize(path=path):
        return False
        
    try:
        acc = mt5.account_info()
        if not acc:
            return False
            
        login = acc.login
        broker = acc.company or term_name
        server = acc.server or "VPS-Terminal"
        currency = acc.currency or "USD"
        balance = round(acc.balance, 2)
        equity = round(acc.equity, 2)
        margin = round(acc.margin, 2)
        free_margin = round(acc.margin_free, 2)
        floating = round(acc.profit, 2)
        
        # Read real open positions
        positions = mt5.positions_get() or []
        pos_list = []
        for p in positions:
            type_str = "BUY" if p.type == 0 else "SELL"
            pos_list.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": type_str,
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
            
        # Read closed deals (last 90 days)
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
        
        closed_deals_list = []
        daily_profit_map = {}
        
        for d in deals:
            if d.entry in (1, 2, 3):
                d_time = datetime.fromtimestamp(d.time)
                day_str = d_time.strftime("%Y-%m-%d")
                p_val = round(d.profit + d.swap + d.commission, 2)
                
                daily_profit_map[day_str] = round(daily_profit_map.get(day_str, 0.0) + p_val, 2)
                
                if d_time >= start_today:
                    today_profit += p_val
                elif d_time >= start_yesterday and d_time < start_today:
                    yesterday_profit += p_val
                if d_time >= start_week:
                    weekly_profit += p_val
                if d_time >= start_month:
                    monthly_profit += p_val
                    
                type_str = "BUY" if d.type == 0 else "SELL"
                closed_deals_list.append({
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "type": type_str,
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
        
        recent_deals = closed_deals_list[-150:] if len(closed_deals_list) > 150 else closed_deals_list

        # Write daily profit to database
        if os.path.exists(DB_PATH) and daily_profit_map:
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                for d_str, p_sum in daily_profit_map.items():
                    c.execute("""
                    INSERT INTO daily_history (login, date, profit, trades_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(login, date) DO UPDATE SET profit = excluded.profit
                    """, (str(login), d_str, p_sum, 1))
                conn.commit()
                conn.close()
            except Exception:
                pass

        payload = {
            "login": login,
            "name": f"{acc.name} ({term_name})",
            "broker": broker,
            "server": server,
            "currency": currency,
            "balance": balance,
            "equity": equity,
            "margin": margin,
            "free_margin": free_margin,
            "floating": floating,
            "today_profit": round(today_profit, 2),
            "yesterday_profit": round(yesterday_profit, 2),
            "weekly_profit": round(weekly_profit, 2),
            "monthly_profit": round(monthly_profit, 2),
            "open_positions": pos_list,
            "closed_deals": recent_deals
        }
        
        try:
            r = requests.post(API_URL, json=payload, timeout=3)
            if r.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] OK: {acc.name} (#{login}) -> Bal: {balance:,.2f} | Float: {floating:+,.2f} | {len(pos_list)} Orders")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] API Notice: Waiting for backend server...")
            
        return True
    finally:
        mt5.shutdown()

def clean_old_demo_data():
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            demo_logins = ("8899201", "6644109", "3311902")
            c.execute("DELETE FROM accounts WHERE login IN (?, ?, ?)", demo_logins)
            c.execute("DELETE FROM snapshots WHERE login IN (?, ?, ?)", demo_logins)
            c.execute("DELETE FROM daily_history WHERE login IN (?, ?, ?)", demo_logins)
            conn.commit()
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 NEXUS QUANT PRO - SMART MT5 AUTO-SYNC (VPS MODE)")
    print("=" * 60)
    clean_old_demo_data()
    
    terms = discover_mt5_terminals()
    print(f"🔍 Auto-discovered {len(terms)} MT5 Terminal(s) on this VPS:")
    for t in terms:
        print(f"  👉 [{t['name']}] {t['path']}")
    print("-" * 60)
    
    if not terms:
        print("⚠️ No MT5 found in standard directories. Please make sure MT5 is installed.")
        
    while True:
        # Re-scan occasionally in case a new terminal was opened
        terms = discover_mt5_terminals()
        for t in terms:
            try:
                sync_terminal(t)
            except Exception as ex:
                pass
            time.sleep(1)
        time.sleep(2)
