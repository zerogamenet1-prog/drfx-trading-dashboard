"""
Real-time MT5 Telemetry Synchronizer for NEXUS QUANT PRO Dashboard.
Connects directly to active MetaTrader 5 terminals and pushes live data.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import requests

API_URL = "http://127.0.0.1:8000/api/report"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TERMINALS = [
    {
        "name": "InterStellar MT5 (PRO X1 Grid)",
        "path": r"C:\Program Files\InterStellar MT5\terminal64.exe"
    },
    {
        "name": "KVB Plus Real MT5",
        "path": r"C:\Program Files\MetaTrader 5\terminal64.exe"
    }
]

def clean_old_demo_data():
    """Removes mock/demo accounts from SQLite database so only real accounts show."""
    import sqlite3
    db_path = os.path.join(BASE_DIR, "dashboard.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        # Delete demo account logins
        demo_logins = ("8899201", "6644109", "3311902")
        c.execute("DELETE FROM accounts WHERE login IN (?, ?, ?)", demo_logins)
        c.execute("DELETE FROM snapshots WHERE login IN (?, ?, ?)", demo_logins)
        c.execute("DELETE FROM daily_history WHERE login IN (?, ?, ?)", demo_logins)
        conn.commit()
        conn.close()
        print("🧹 Cleaned old demo mock data from database.")

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
        broker = acc.company
        server = acc.server
        currency = acc.currency
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
            
        # Calculate profits from real closed deals
        now = datetime.now()
        start_today = datetime(now.year, now.month, now.day)
        start_yesterday = start_today - timedelta(days=1)
        start_week = start_today - timedelta(days=now.weekday())
        start_month = datetime(now.year, now.month, 1)
        
        deals = mt5.history_deals_get(start_month - timedelta(days=30), now) or []
        
        today_profit = 0.0
        yesterday_profit = 0.0
        weekly_profit = 0.0
        monthly_profit = 0.0
        
        for d in deals:
            if d.entry in (1, 2, 3): # deal out / inout
                d_time = datetime.fromtimestamp(d.time)
                p_val = d.profit + d.swap + d.commission
                if d_time >= start_today:
                    today_profit += p_val
                elif d_time >= start_yesterday and d_time < start_today:
                    yesterday_profit += p_val
                if d_time >= start_week:
                    weekly_profit += p_val
                if d_time >= start_month:
                    monthly_profit += p_val
                    
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
            "open_positions": pos_list
        }
        
        # Send to local dashboard server
        try:
            r = requests.post(API_URL, json=payload, timeout=2)
            if r.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] Synced {acc.name} (#{login}): Balance {balance:,.2f} | Equity {equity:,.2f} | Float {floating:+,.2f} | {len(pos_list)} Orders")
        except Exception as e:
            print(f"⚠️ API Error: {e}")
            
        return True
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 NEXUS QUANT PRO - REAL MT5 DATA SYNCHRONIZER")
    print("=" * 60)
    clean_old_demo_data()
    print("Connecting to live MT5 terminals and syncing...\n")
    
    # Run loop
    while True:
        for t in TERMINALS:
            try:
                sync_terminal(t)
            except Exception as ex:
                print(f"Error syncing {t['name']}: {ex}")
            time.sleep(1)
        time.sleep(1)
