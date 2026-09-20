import sqlite3
import yfinance as yf
from datetime import datetime
import pandas as pd

DB_FILE = "trades.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table for active positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            qty INTEGER,
            buy_price REAL,
            sl_price REAL,
            target_price REAL,
            allocated_amount REAL,
            entry_time TEXT,
            status TEXT
        )
    ''')
    # Table for closed trades ledger
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
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

# --- MARKET DATA FEED ---
def get_live_price(symbol):
    """Fetches real-time LTP from NSE."""
    formatted_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
    try:
        ticker = yf.Ticker(formatted_symbol)
        # Using fast_info for sub-second snapshot
        price = ticker.fast_info.get("last_price")
        if price:
            return round(float(price), 2)
        # Fallback to intraday 1m bar
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            return round(float(data['Close'].iloc[-1]), 2)
    except Exception:
        pass
    return None

# --- PLUGGABLE BROKER ADAPTER (Paper Mode) ---
class PaperBrokerAdapter:
    """
    Executes paper trades against SQLite.
    When moving to live brokers later, replace internal DB queries 
    with broker.place_order() calls without modifying app.py.
    """
    
    @staticmethod
    def buy(symbol, allocated_amount, sl, target):
        cmp = get_live_price(symbol)
        if not cmp or cmp <= 0:
            return False, f"Could not fetch live price for {symbol}"
        
        qty = int(allocated_amount // cmp)
        if qty < 1:
            return False, f"Capital ₹{allocated_amount} is too low to buy 1 share at ₹{cmp}"
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''
            INSERT INTO positions (symbol, qty, buy_price, sl_price, target_price, allocated_amount, entry_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')
        ''', (symbol.upper(), qty, cmp, sl, target, allocated_amount, now))
        conn.commit()
        conn.close()
        return True, f"Bought {qty} shares of {symbol} at ₹{cmp}"

    @staticmethod
    def sell(pos_id, symbol, qty, buy_price, exit_price, reason, entry_time):
        pnl = round((exit_price - buy_price) * qty, 2)
        pnl_pct = round(((exit_price - buy_price) / buy_price) * 100, 2)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Remove from active positions
        c.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        # Write to history
        c.execute('''
            INSERT INTO trade_history (symbol, qty, buy_price, sell_price, pnl, pnl_pct, exit_reason, entry_time, exit_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, qty, buy_price, exit_price, pnl, pnl_pct, reason, entry_time, now))
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
