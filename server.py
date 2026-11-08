import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="DRFX Live Trading Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "dashboard.db")
os.makedirs(STATIC_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────
# DATABASE INITIALIZATION
# ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        login TEXT PRIMARY KEY,
        name TEXT,
        broker TEXT,
        server TEXT,
        currency TEXT DEFAULT 'USD',
        balance REAL DEFAULT 0,
        equity REAL DEFAULT 0,
        margin REAL DEFAULT 0,
        free_margin REAL DEFAULT 0,
        floating REAL DEFAULT 0,
        today_profit REAL DEFAULT 0,
        yesterday_profit REAL DEFAULT 0,
        weekly_profit REAL DEFAULT 0,
        monthly_profit REAL DEFAULT 0,
        max_dd REAL DEFAULT 0,
        current_dd REAL DEFAULT 0,
        open_orders_count INTEGER DEFAULT 0,
        total_lots REAL DEFAULT 0,
        last_ping INTEGER DEFAULT 0,
        raw_positions TEXT DEFAULT '[]',
        raw_history TEXT DEFAULT '[]'
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT,
        timestamp INTEGER,
        balance REAL,
        equity REAL,
        floating REAL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT,
        date TEXT,
        profit REAL,
        trades_count INTEGER DEFAULT 0,
        UNIQUE(login, date) ON CONFLICT REPLACE
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS closed_deals (
        ticket INTEGER PRIMARY KEY,
        login TEXT,
        account_name TEXT,
        symbol TEXT,
        type TEXT,
        lots REAL,
        open_price REAL,
        close_price REAL,
        profit REAL,
        swap REAL DEFAULT 0,
        commission REAL DEFAULT 0,
        net_profit REAL,
        close_time TEXT,
        close_timestamp INTEGER,
        comment TEXT,
        magic INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ──────────────────────────────────────────────────────────────────
# WEBSOCKET MANAGER
# ──────────────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        payload = json.dumps(message)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

# ──────────────────────────────────────────────────────────────────
# DATA MODELS
# ──────────────────────────────────────────────────────────────────
class PositionModel(BaseModel):
    ticket: int
    symbol: str
    type: str # BUY / SELL
    lots: float
    open_price: float
    current_price: float
    sl: Optional[float] = 0.0
    tp: Optional[float] = 0.0
    profit: float
    swap: Optional[float] = 0.0
    comment: Optional[str] = ""
    magic: Optional[int] = 0
    open_time: Optional[str] = ""

class ClosedDealModel(BaseModel):
    ticket: int
    symbol: str
    type: str
    lots: float
    open_price: Optional[float] = 0.0
    close_price: Optional[float] = 0.0
    profit: float
    swap: Optional[float] = 0.0
    commission: Optional[float] = 0.0
    close_time: str
    close_timestamp: Optional[int] = 0
    comment: Optional[str] = ""
    magic: Optional[int] = 0

class ReportPayload(BaseModel):
    secret: Optional[str] = ""
    login: int
    name: Optional[str] = "DRFX Trader"
    broker: Optional[str] = "Broker"
    server: Optional[str] = "Demo"
    currency: Optional[str] = "USD"
    balance: float
    equity: float
    margin: Optional[float] = 0.0
    free_margin: Optional[float] = 0.0
    floating: Optional[float] = 0.0
    today_profit: Optional[float] = 0.0
    yesterday_profit: Optional[float] = 0.0
    weekly_profit: Optional[float] = 0.0
    monthly_profit: Optional[float] = 0.0
    max_dd: Optional[float] = 0.0
    current_dd: Optional[float] = 0.0
    open_positions: Optional[List[PositionModel]] = []
    closed_deals: Optional[List[ClosedDealModel]] = []

# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
def calculate_portfolio_snapshot():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts ORDER BY balance DESC")
    rows = cursor.fetchall()
    
    accounts = []
    all_positions = []
    total_balance = 0.0
    total_equity = 0.0
    total_floating = 0.0
    total_today = 0.0
    total_yesterday = 0.0
    total_weekly = 0.0
    total_monthly = 0.0
    total_open_orders = 0
    total_lots = 0.0

    now_ts = int(time.time())

    for r in rows:
        is_online = (now_ts - r["last_ping"]) < 30 # Online if reported within 30s
        acc_dict = {
            "login": r["login"],
            "name": r["name"] or f"Account {r['login']}",
            "broker": r["broker"],
            "server": r["server"],
            "currency": r["currency"] or "USD",
            "balance": round(r["balance"], 2),
            "equity": round(r["equity"], 2),
            "margin": round(r["margin"], 2),
            "free_margin": round(r["free_margin"], 2),
            "floating": round(r["floating"], 2),
            "today_profit": round(r["today_profit"], 2),
            "yesterday_profit": round(r["yesterday_profit"], 2),
            "weekly_profit": round(r["weekly_profit"], 2),
            "monthly_profit": round(r["monthly_profit"], 2),
            "max_dd": round(r["max_dd"], 2),
            "current_dd": round(r["current_dd"], 2),
            "open_orders_count": r["open_orders_count"],
            "total_lots": round(r["total_lots"], 2),
            "last_ping": r["last_ping"],
            "is_online": is_online
        }
        accounts.append(acc_dict)
        
        # Flatten all open positions across accounts
        try:
            raw_pos = json.loads(r["raw_positions"] or "[]")
            for p in raw_pos:
                p["account_name"] = acc_dict["name"]
                p["account_login"] = r["login"]
                all_positions.append(p)
        except Exception:
            pass

        total_balance += r["balance"]
        total_equity += r["equity"]
        total_floating += r["floating"]
        total_today += r["today_profit"]
        total_yesterday += r["yesterday_profit"]
        total_weekly += r["weekly_profit"]
        total_monthly += r["monthly_profit"]
        total_open_orders += r["open_orders_count"]
        total_lots += r["total_lots"]

    # Gather aggregated daily history across all accounts for the calendar
    cursor.execute("""
    SELECT date, SUM(profit) as total_profit, SUM(trades_count) as total_trades 
    FROM daily_history GROUP BY date ORDER BY date DESC LIMIT 45
    """)
    daily_calendar = [
        {"date": r["date"], "profit": round(r["total_profit"] or 0, 2), "trades": r["total_trades"] or 0}
        for r in cursor.fetchall()
    ]

    # Performance stats from closed deals
    cursor.execute("""
    SELECT 
        COUNT(*) as total_trades,
        SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) as win_trades,
        SUM(CASE WHEN net_profit < 0 THEN 1 ELSE 0 END) as loss_trades,
        SUM(CASE WHEN net_profit > 0 THEN net_profit ELSE 0 END) as gross_profit,
        ABS(SUM(CASE WHEN net_profit < 0 THEN net_profit ELSE 0 END)) as gross_loss,
        SUM(net_profit) as total_profit,
        MAX(net_profit) as best_trade,
        MIN(net_profit) as worst_trade
    FROM closed_deals
    """)
    s = cursor.fetchone()
    conn.close()

    tot_trades = s["total_trades"] or 0
    wins = s["win_trades"] or 0
    gp = round(s["gross_profit"] or 0.0, 2)
    gl = round(s["gross_loss"] or 0.0, 2)
    pf = round(gp / gl, 2) if gl > 0 else (gp if gp > 0 else 0)
    wr = round(wins / tot_trades * 100, 2) if tot_trades > 0 else 0

    performance_stats = {
        "total_trades": tot_trades,
        "win_trades": wins,
        "loss_trades": s["loss_trades"] or 0,
        "win_rate": wr,
        "profit_factor": pf,
        "gross_profit": gp,
        "gross_loss": gl,
        "net_profit": round(s["total_profit"] or 0.0, 2),
        "best_trade": round(s["best_trade"] or 0.0, 2),
        "worst_trade": round(s["worst_trade"] or 0.0, 2)
    }

    total_profit = total_equity - total_balance

    return {
        "portfolio": {
            "total_balance": round(total_balance, 2),
            "total_equity": round(total_equity, 2),
            "total_floating": round(total_floating, 2),
            "total_profit": round(total_profit, 2),
            "today_profit": round(total_today, 2),
            "yesterday_profit": round(total_yesterday, 2),
            "weekly_profit": round(total_weekly, 2),
            "monthly_profit": round(total_monthly, 2),
            "total_open_orders": total_open_orders,
            "total_lots": round(total_lots, 2),
            "accounts_count": len(accounts),
            "accounts": accounts,
            "all_positions": all_positions,
            "daily_calendar": daily_calendar,
            "performance_stats": performance_stats
        },
        "usdthb": {
            "rate": 34.65,
            "source": "Bank of Thailand / Market Ref",
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
        },
        "timestamp": now_ts
    }

# ──────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────────────────────────

@app.post("/api/report")
async def report_telemetry(payload: ReportPayload):
    login_str = str(payload.login)
    now_ts = int(time.time())
    
    positions_json = json.dumps([p.dict() for p in (payload.open_positions or [])])
    history_json = json.dumps([d.dict() for d in (payload.closed_deals or [])])
    
    total_lots = sum(p.lots for p in (payload.open_positions or []))
    orders_cnt = len(payload.open_positions or [])
    
    floating = payload.floating if payload.floating != 0.0 else (payload.equity - payload.balance)
    
    # Calculate current DD%
    current_dd = 0.0
    if payload.balance > 0 and floating < 0:
        current_dd = abs(floating) / payload.balance * 100.0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO accounts (
        login, name, broker, server, currency, balance, equity, margin, free_margin,
        floating, today_profit, yesterday_profit, weekly_profit, monthly_profit,
        max_dd, current_dd, open_orders_count, total_lots, last_ping, raw_positions, raw_history
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(login) DO UPDATE SET
        name = COALESCE(excluded.name, accounts.name),
        broker = COALESCE(excluded.broker, accounts.broker),
        server = COALESCE(excluded.server, accounts.server),
        currency = COALESCE(excluded.currency, accounts.currency),
        balance = excluded.balance,
        equity = excluded.equity,
        margin = excluded.margin,
        free_margin = excluded.free_margin,
        floating = excluded.floating,
        today_profit = excluded.today_profit,
        yesterday_profit = excluded.yesterday_profit,
        weekly_profit = excluded.weekly_profit,
        monthly_profit = excluded.monthly_profit,
        max_dd = MAX(accounts.max_dd, excluded.current_dd),
        current_dd = excluded.current_dd,
        open_orders_count = excluded.open_orders_count,
        total_lots = excluded.total_lots,
        last_ping = excluded.last_ping,
        raw_positions = excluded.raw_positions,
        raw_history = excluded.raw_history
    """, (
        login_str, payload.name, payload.broker, payload.server, payload.currency,
        payload.balance, payload.equity, payload.margin, payload.free_margin,
        floating, payload.today_profit, payload.yesterday_profit, payload.weekly_profit, payload.monthly_profit,
        payload.max_dd, current_dd, orders_cnt, total_lots, now_ts, positions_json, history_json
    ))

    # Throttle snapshots: record at most 1 snapshot per 10 minutes per account
    cursor.execute("SELECT timestamp FROM snapshots WHERE login = ? ORDER BY timestamp DESC LIMIT 1", (login_str,))
    last_snap = cursor.fetchone()
    if not last_snap or (now_ts - last_snap["timestamp"]) >= 600:
        cursor.execute("""
        INSERT INTO snapshots (login, timestamp, balance, equity, floating)
        VALUES (?, ?, ?, ?, ?)
        """, (login_str, now_ts, payload.balance, payload.equity, floating))

    # Update today's profit in daily_history
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
    INSERT INTO daily_history (login, date, profit, trades_count)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(login, date) DO UPDATE SET
        profit = excluded.profit
    """, (login_str, today_str, payload.today_profit, 0))

    # Save closed deals if provided
    if payload.closed_deals:
        for d in payload.closed_deals:
            net_p = d.profit + (d.swap or 0.0) + (d.commission or 0.0)
            cursor.execute("""
            INSERT INTO closed_deals (
                ticket, login, account_name, symbol, type, lots, open_price, close_price,
                profit, swap, commission, net_profit, close_time, close_timestamp, comment, magic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket) DO UPDATE SET
                net_profit = excluded.net_profit,
                profit = excluded.profit
            """, (
                d.ticket, login_str, payload.name, d.symbol, d.type, d.lots, d.open_price, d.close_price,
                d.profit, d.swap, d.commission, net_p, d.close_time, d.close_timestamp or now_ts,
                d.comment, d.magic
            ))

    conn.commit()
    conn.close()

    # Broadcast to all live WebSockets immediately
    snapshot = calculate_portfolio_snapshot()
    asyncio.create_task(manager.broadcast(snapshot))

    return {"status": "ok", "login": login_str, "timestamp": now_ts}

@app.get("/api/closed-deals")
async def get_closed_deals(limit: int = 150, symbol: Optional[str] = None):
    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM closed_deals"
    params = []
    if symbol:
        query += " WHERE symbol LIKE ?"
        params.append(f"%{symbol}%")
    query += " ORDER BY close_timestamp DESC, ticket DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    deals = [dict(r) for r in c.fetchall()]

    # Aggregated performance stats
    c.execute("""
    SELECT 
        COUNT(*) as total_trades,
        SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) as win_trades,
        SUM(CASE WHEN net_profit < 0 THEN 1 ELSE 0 END) as loss_trades,
        SUM(CASE WHEN net_profit > 0 THEN net_profit ELSE 0 END) as gross_profit,
        ABS(SUM(CASE WHEN net_profit < 0 THEN net_profit ELSE 0 END)) as gross_loss,
        SUM(net_profit) as total_profit,
        MAX(net_profit) as best_trade,
        MIN(net_profit) as worst_trade,
        SUM(commission) as total_commission,
        SUM(swap) as total_swap
    FROM closed_deals
    """)
    s = c.fetchone()
    conn.close()

    tot = s["total_trades"] or 0
    wins = s["win_trades"] or 0
    gp = round(s["gross_profit"] or 0.0, 2)
    gl = round(s["gross_loss"] or 0.0, 2)
    pf = round(gp / gl, 2) if gl > 0 else (gp if gp > 0 else 0)
    wr = round(wins / tot * 100, 2) if tot > 0 else 0

    return {
        "deals": deals,
        "stats": {
            "total_trades": tot,
            "win_trades": wins,
            "loss_trades": s["loss_trades"] or 0,
            "win_rate": wr,
            "profit_factor": pf,
            "gross_profit": gp,
            "gross_loss": gl,
            "net_profit": round(s["total_profit"] or 0.0, 2),
            "best_trade": round(s["best_trade"] or 0.0, 2),
            "worst_trade": round(s["worst_trade"] or 0.0, 2),
            "total_commission": round(s["total_commission"] or 0.0, 2),
            "total_swap": round(s["total_swap"] or 0.0, 2)
        }
    }

@app.get("/api/snapshot")
async def get_snapshot():
    return calculate_portfolio_snapshot()

@app.get("/api/account/{login}/details")
async def get_account_details(login: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE login = ?", (login,))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    # Get snapshots for Equity Curve (last 100 points)
    cursor.execute("""
    SELECT timestamp, balance, equity, floating FROM snapshots 
    WHERE login = ? ORDER BY timestamp ASC LIMIT 200
    """, (login,))
    snapshots = [dict(r) for r in cursor.fetchall()]

    # Get daily profit history (last 30 days)
    cursor.execute("""
    SELECT date, profit, trades_count FROM daily_history 
    WHERE login = ? ORDER BY date ASC LIMIT 30
    """, (login,))
    daily_stats = [dict(r) for r in cursor.fetchall()]

    positions = json.loads(acc["raw_positions"] or "[]")
    history_deals = json.loads(acc["raw_history"] or "[]")

    conn.close()

    return {
        "account": {
            "login": acc["login"],
            "name": acc["name"],
            "broker": acc["broker"],
            "server": acc["server"],
            "currency": acc["currency"],
            "balance": acc["balance"],
            "equity": acc["equity"],
            "floating": acc["floating"],
            "margin": acc["margin"],
            "free_margin": acc["free_margin"],
            "today_profit": acc["today_profit"],
            "yesterday_profit": acc["yesterday_profit"],
            "max_dd": acc["max_dd"],
            "current_dd": acc["current_dd"]
        },
        "snapshots": snapshots,
        "daily_stats": daily_stats,
        "positions": positions,
        "history_deals": history_deals
    }

@app.get("/api/mock-demo")
async def inject_mock_demo():
    """Infects realistic demo data so the user can experience the dashboard instantly!"""
    conn = get_db()
    cursor = conn.cursor()
    now_ts = int(time.time())
    
    mock_accounts = [
        {
            "login": "8899201",
            "name": "DRFX-NEMENEXUS (Gold Grid)",
            "broker": "ICMarkets-Live02",
            "server": "ICMarketsSC-Live",
            "currency": "USD",
            "balance": 12500.0,
            "equity": 12785.40,
            "margin": 240.0,
            "free_margin": 12545.40,
            "floating": 285.40,
            "today_profit": 195.50,
            "yesterday_profit": 320.10,
            "weekly_profit": 980.20,
            "monthly_profit": 2450.80,
            "max_dd": 4.15,
            "current_dd": 0.0,
            "positions": [
                {"ticket": 104521, "symbol": "XAUUSD", "type": "BUY", "lots": 0.04, "open_price": 2730.50, "current_price": 2736.20, "sl": 2715.0, "tp": 2745.0, "profit": 228.00, "swap": -1.2, "comment": "DRFX_Grid_L1", "magic": 9901},
                {"ticket": 104522, "symbol": "XAUUSD", "type": "BUY", "lots": 0.05, "open_price": 2733.10, "current_price": 2736.20, "sl": 2715.0, "tp": 2745.0, "profit": 155.00, "swap": -0.8, "comment": "DRFX_Grid_L2", "magic": 9901},
                {"ticket": 104529, "symbol": "EURUSD", "type": "SELL", "lots": 0.10, "open_price": 1.0845, "current_price": 1.0854, "sl": 1.0890, "tp": 1.0800, "profit": -97.60, "swap": 0.5, "comment": "Hedge_M15", "magic": 9902}
            ]
        },
        {
            "login": "6644109",
            "name": "PRO X1 Dynamic Grid V15",
            "broker": "Exness-Real19",
            "server": "Exness-Real19",
            "currency": "USD",
            "balance": 8400.0,
            "equity": 8345.20,
            "margin": 180.0,
            "free_margin": 8165.20,
            "floating": -54.80,
            "today_profit": 112.40,
            "yesterday_profit": 145.80,
            "weekly_profit": 640.50,
            "monthly_profit": 1620.00,
            "max_dd": 6.80,
            "current_dd": 0.65,
            "positions": [
                {"ticket": 223401, "symbol": "GBPUSD", "type": "BUY", "lots": 0.03, "open_price": 1.2980, "current_price": 1.2972, "sl": 1.2920, "tp": 1.3040, "profit": -24.00, "swap": -0.2, "comment": "PRO_Pending", "magic": 1501},
                {"ticket": 223402, "symbol": "GBPUSD", "type": "BUY", "lots": 0.04, "open_price": 1.2965, "current_price": 1.2972, "sl": 1.2920, "tp": 1.3040, "profit": 28.00, "swap": -0.1, "comment": "PRO_Martingale", "magic": 1501}
            ]
        },
        {
            "login": "3311902",
            "name": "Nexus Alpha Trend (Cent Port)",
            "broker": "RoboForex-ProCent",
            "server": "RoboForex-ProCent",
            "currency": "USC",
            "balance": 54000.0, # Cent
            "equity": 54850.0,
            "margin": 450.0,
            "free_margin": 54400.0,
            "floating": 850.0,
            "today_profit": 680.0,
            "yesterday_profit": 720.0,
            "weekly_profit": 3400.0,
            "monthly_profit": 8900.0,
            "max_dd": 3.20,
            "current_dd": 0.0,
            "positions": [
                {"ticket": 331001, "symbol": "USDJPY", "type": "SELL", "lots": 0.50, "open_price": 153.20, "current_price": 152.85, "sl": 154.00, "tp": 151.50, "profit": 850.0, "swap": 1.5, "comment": "Trend_Cent", "magic": 8812}
            ]
        }
    ]

    for acc in mock_accounts:
        pos_json = json.dumps(acc["positions"])
        cursor.execute("""
        INSERT INTO accounts (
            login, name, broker, server, currency, balance, equity, margin, free_margin,
            floating, today_profit, yesterday_profit, weekly_profit, monthly_profit,
            max_dd, current_dd, open_orders_count, total_lots, last_ping, raw_positions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(login) DO UPDATE SET
            balance = excluded.balance,
            equity = excluded.equity,
            floating = excluded.floating,
            today_profit = excluded.today_profit,
            yesterday_profit = excluded.yesterday_profit,
            weekly_profit = excluded.weekly_profit,
            monthly_profit = excluded.monthly_profit,
            open_orders_count = excluded.open_orders_count,
            total_lots = excluded.total_lots,
            last_ping = excluded.last_ping,
            raw_positions = excluded.raw_positions
        """, (
            acc["login"], acc["name"], acc["broker"], acc["server"], acc["currency"],
            acc["balance"], acc["equity"], acc["margin"], acc["free_margin"],
            acc["floating"], acc["today_profit"], acc["yesterday_profit"], acc["weekly_profit"], acc["monthly_profit"],
            acc["max_dd"], acc["current_dd"], len(acc["positions"]),
            sum(p["lots"] for p in acc["positions"]), now_ts, pos_json
        ))

        # Generate 14 days of realistic daily history
        base_bal = acc["balance"] * 0.90
        for i in range(14, -1, -1):
            day_dt = datetime.now() - timedelta(days=i)
            day_str = day_dt.strftime("%Y-%m-%d")
            # Random profit variation
            day_profit = round((acc["today_profit"] or 100) * (0.6 + (i * 7 % 9) / 10), 2)
            if i % 5 == 0 and i != 0:
                day_profit = -round(day_profit * 0.4, 2) # occasional small red day
            
            cursor.execute("""
            INSERT INTO daily_history (login, date, profit, trades_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(login, date) DO UPDATE SET profit = excluded.profit
            """, (acc["login"], day_str, day_profit, 5 + (i % 6)))

            # Snapshot points
            base_bal += max(0, day_profit)
            cursor.execute("""
            INSERT INTO snapshots (login, timestamp, balance, equity, floating)
            VALUES (?, ?, ?, ?, ?)
            """, (acc["login"], int(day_dt.timestamp()), base_bal, base_bal + (acc["floating"] if i == 0 else 10), 0))

    conn.commit()
    conn.close()

    snap = calculate_portfolio_snapshot()
    asyncio.create_task(manager.broadcast(snap))
    return {"status": "ok", "message": "Demo data successfully injected!", "accounts": len(mock_accounts)}

# ──────────────────────────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ──────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Send snapshot immediately on connect
    snapshot = calculate_portfolio_snapshot()
    await websocket.send_text(json.dumps(snapshot))
    try:
        while True:
            # Keep alive and receive ping from client
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "time": int(time.time())}))
            elif data == "refresh":
                await websocket.send_text(json.dumps(calculate_portfolio_snapshot()))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# ──────────────────────────────────────────────────────────────────
# STATIC FILE SERVING
# ──────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "DRFX Dashboard Backend running. Place index.html in static/"})

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 DRFX LIVE TRADING DASHBOARD SERVER RUNNING")
    print("📡 Local URL: http://localhost:8000")
    print("📡 WebSocket URL: ws://localhost:8000/ws")
    print("📡 MT5 Report Endpoint: http://localhost:8000/api/report")
    print("=" * 60)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

