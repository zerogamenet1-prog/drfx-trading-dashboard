"""
Simulate Live Ticks and Order P/L changes in real-time.
This script sends periodic updates to the DRFX Live Dashboard to demonstrate real-time updates.
"""
import random
import time
import requests

API_URL = "http://localhost:8000/api/report"

print("🚀 Starting Live Simulation to Dashboard...")
print(f"📡 Sending data to: {API_URL}")
print("Press Ctrl+C to stop.\n")

login = 8899201
balance = 12500.0
base_gold = 2736.20

while True:
    try:
        # Simulate price tick fluctuations
        gold_tick = base_gold + random.uniform(-1.5, 1.5)
        p1_profit = round((gold_tick - 2730.50) * 0.04 * 100, 2)
        p2_profit = round((gold_tick - 2733.10) * 0.05 * 100, 2)
        total_float = round(p1_profit + p2_profit, 2)
        equity = round(balance + total_float, 2)

        payload = {
            "login": login,
            "name": "DRFX-NEMENEXUS (Live Demo)",
            "broker": "ICMarketsSC-Live",
            "server": "ICMarketsSC-Live",
            "currency": "USD",
            "balance": balance,
            "equity": equity,
            "margin": 240.0,
            "free_margin": round(equity - 240.0, 2),
            "floating": total_float,
            "today_profit": 235.80,
            "yesterday_profit": 320.10,
            "weekly_profit": 980.20,
            "monthly_profit": 2450.80,
            "open_positions": [
                {
                    "ticket": 104521,
                    "symbol": "XAUUSD",
                    "type": "BUY",
                    "lots": 0.04,
                    "open_price": 2730.50,
                    "current_price": round(gold_tick, 2),
                    "sl": 2715.0,
                    "tp": 2745.0,
                    "profit": p1_profit,
                    "comment": "DRFX_Grid_L1",
                    "magic": 9901
                },
                {
                    "ticket": 104522,
                    "symbol": "XAUUSD",
                    "type": "BUY",
                    "lots": 0.05,
                    "open_price": 2733.10,
                    "current_price": round(gold_tick, 2),
                    "sl": 2715.0,
                    "tp": 2745.0,
                    "profit": p2_profit,
                    "comment": "DRFX_Grid_L2",
                    "magic": 9901
                }
            ]
        }

        r = requests.post(API_URL, json=payload, timeout=2)
        print(f"[{time.strftime('%H:%M:%S')}] Pushed Live Tick -> XAUUSD: {gold_tick:.2f} | Floating: {total_float:+.2f} USD")
    except Exception as e:
        print(f"⚠️ Error: {e} (Is the server running?)")
    
    time.sleep(2)

