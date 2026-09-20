import sqlite3
import yfinance as yf
from datetime import datetime
import pytz
import pandas as pd

DB_FILE = "trades.db"
IST = pytz.timezone("Asia/Kolkata")

def check_market_status():
    """Checks if Indian equity/derivative markets are open (Mon-Fri, 9:15 AM - 3:30 PM IST)."""
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()

    if weekday in [5, 6]:
        day = "Saturday" if weekday == 5 else "Sunday"
        return False, f"Market is closed today ({day}). Orders will queue as AMO."

    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    if now_ist < market_open:
        return False, "Market opens at 9:15 AM IST. Orders will queue as AMO."
    elif now_ist > market_close:
        return False, "Market closed for the day (3:30 PM IST). Orders will queue as AMO."

    return True, "Market is Open (Live Trading Active)"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Active open positions
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
    # Historical trade ledger
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
    # Universal saved watchlist
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE,
            asset_type TEXT,
            added_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def format_ticker_symbol(symbol):
    """Formats ticker for yfinance query."""
    sym = symbol.strip().upper()
    # If already formatted with exchange or commodity notation
    if sym.endswith(".NS") or sym.endswith(".BO") or "=" in sym:
        return sym
    return f"{sym}.NS"

def get_live_quote(symbol):
    """Fetches real-time market quote including price, previous close, and % change."""
    formatted = format_ticker_symbol(symbol)
    try:
        t = yf.Ticker(formatted)
        price = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
        prev_close = t.fast_info.get("previous_close") or price

        if not price:
            hist = t.history(period="5d", interval="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price

        if price and price > 0:
            price = round(float(price), 2)
            prev_close = round(float(prev_close), 2)
            pct_change = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0
            return {
                "symbol": symbol.strip().upper(),
                "formatted": formatted,
                "price": price,
                "prev_close": prev_close,
                "pct_change": pct_change
            }
    except Exception:
        pass
    return None

class PaperBrokerAdapter:
    @staticmethod
    def buy(symbol, asset_type, qty, actual_invested, cmp, sl, target, is_amo=False):
        if qty < 1:
            return False, "Quantity must be at least 1 unit."

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

    # --- WATCHLIST METHODS ---
    @staticmethod
    def add_to_watchlist(symbol, asset_type="Asset"):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            c.execute("INSERT INTO watchlist (symbol, asset_type, added_time) VALUES (?, ?, ?)",
                      (symbol.upper(), asset_type, now))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success

    @staticmethod
    def remove_from_watchlist(symbol):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
        conn.commit()
        conn.close()

    @staticmethod
    def get_watchlist():
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY id DESC", conn)
        conn.close()
        return df
