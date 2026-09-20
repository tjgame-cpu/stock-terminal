import sqlite3
import yfinance as yf
from datetime import datetime
import pytz
import pandas as pd

DB_FILE = "trades.db"
IST = pytz.timezone("Asia/Kolkata")

def check_market_status():
    """
    Verifies if Indian equity markets (NSE/BSE) are open.
    Trading hours: Mon-Fri, 9:15 AM - 3:30 PM IST.
    """
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()  # Monday = 0, Sunday = 6

    # 1. Weekend Check
    if weekday == 5:
        return False, "Market is closed today (Saturday). Orders will be placed as AMO (After Market Orders)."
    if weekday == 6:
        return False, "Market is closed today (Sunday). Orders will be placed as AMO (After Market Orders)."

    # 2. Weekday Trading Hours Check
    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    if now_ist < market_open:
        return False, "Market has not opened yet (Opens at 9:15 AM IST). Orders will be queued as AMO."
    elif now_ist > market_close:
        return False, "Market is closed for the day (Closed at 3:30 PM IST). Orders will be queued as AMO."

    return True, "Market is Open (Live Trading Active)"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            type TEXT,
            qty INTEGER,
            buy_price REAL,
            actual_invested REAL,
            sl_price REAL,
            target_price REAL,
            entry_time TEXT,
            status TEXT,
            order_mode TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            type TEXT,
            qty INTEGER,
            buy_price REAL,
            sell_price REAL,
            pnl REAL,
            pnl_pct REAL,
            exit_reason TEXT,
            entry_time TEXT,
            exit_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_live_price(symbol):
    """Fetches exact CMP or latest trading session closing price."""
    formatted_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
    try:
        t = yf.Ticker(formatted_symbol)
        price = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
        if price and price > 0:
            return round(float(price), 2)
        
        hist = t.history(period="5d", interval="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None

class PaperBrokerAdapter:
    @staticmethod
    def buy(symbol, asset_type, qty, actual_invested, cmp, sl, target, is_amo=False):
        if qty < 1:
            return False, "Allocation amount is too low to buy 1 unit."

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        order_mode = "AMO" if is_amo else "REGULAR"

        c.execute('''
            INSERT INTO positions (symbol, type, qty, buy_price, actual_invested, sl_price, target_price, entry_time, status, order_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        ''', (symbol.upper(), asset_type, qty, cmp, actual_invested, sl, target, now, order_mode))
        conn.commit()
        conn.close()

        msg = f"Queued AMO Order: {qty} units of {symbol} at ₹{cmp:,.2f}" if is_amo else f"Bought {qty} units of {symbol} at ₹{cmp:,.2f}"
        return True, msg

    @staticmethod
    def sell(pos_id, symbol, asset_type, qty, buy_price, exit_price, reason, entry_time):
        pnl = round((exit_price - buy_price) * qty, 2)
        pnl_pct = round(((exit_price - buy_price) / buy_price) * 100, 2)
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        c.execute('''
            INSERT INTO trade_history (symbol, type, qty, buy_price, sell_price, pnl, pnl_pct, exit_reason, entry_time, exit_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, asset_type, qty, buy_price, exit_price, pnl, pnl_pct, reason, entry_time, now))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def get_open_positions():
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM positions WHERE status='OPEN'", conn)
        conn.close()
        return df

    @staticmethod
    def get_history():
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM trade_history ORDER BY id DESC", conn)
        conn.close()
        return df
