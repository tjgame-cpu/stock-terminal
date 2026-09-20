"""
DISCOVERY & MOMENTUM ENGINE
Downloads the universe in a single batch query to prevent cloud IP rate limits.
"""
import pandas as pd
import yfinance as yf
import streamlit as st

# ==============================================================================
# 1. UNIVERSE DEFINITIONS (57 Instruments)
# ==============================================================================
NSE_STOCKS_UNIVERSE = [
    # Nifty 50 Heavyweights
    "RELIANCE.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS", "SBIN.NS",
    "TCS.NS", "INFY.NS", "BAJFINANCE.NS", "HINDUNILVR.NS", "LT.NS",
    "SUNPHARMA.NS", "MARUTI.NS", "M&M.NS", "HCLTECH.NS", "AXISBANK.NS",
    "ITC.NS", "NTPC.NS", "ONGC.NS", "KOTAKBANK.NS", "TITAN.NS",
    "TATASTEEL.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "COALINDIA.NS", "ADANIENT.NS",
    # High-Growth / High-Beta Momentum Stocks
    "TRENT.NS", "VBL.NS", "POLYCAB.NS", "KEI.NS", "NCC.NS",
    "DIXON.NS", "PERSISTENT.NS", "COFORGE.NS", "BSE.NS", "HAL.NS",
    "BEL.NS", "MAZDOCK.NS", "RVNL.NS", "SUZLON.NS", "HINDPETRO.NS", "REC.NS"
]

NSE_ETFS_UNIVERSE = [
    # Benchmark & Sectoral Liquid ETFs
    "NIFTYBEES.NS", "BANKBEES.NS", "ITBEES.NS", "GOLDBEES.NS", "SILVERBEES.NS",
    "PHARMABEES.NS", "CONSUMBEES.NS", "AUTOBEES.NS", "MID150BEES.NS", "JUNIORBEES.NS",
    "CPSEETF.NS", "MON100.NS", "MAFANG.NS", "HDFCNIFTY.NS", "SETFNIF50.NS",
    "SETFNIFBK.NS", "ICICILIQUID.NS", "LIQUIDBEES.NS", "AXISNIFTY.NS", "KOTAKNIFTY.NS"
]

SCAN_POOL = list(dict.fromkeys(NSE_STOCKS_UNIVERSE + NSE_ETFS_UNIVERSE))

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def extract_ticker_data(batch_df, ticker):
    """Safely extracts clean OHLCV for a ticker regardless of pandas MultiIndex order."""
    if not isinstance(batch_df.columns, pd.MultiIndex):
        return batch_df.dropna()
    
    # Structure 1: Level 0 is Ticker (group_by='ticker')
    if ticker in batch_df.columns.levels[0]:
        return batch_df[ticker].dropna()
    
    # Structure 2: Level 1 is Ticker (Price Metric in Level 0)
    if ticker in batch_df.columns.levels[1]:
        return batch_df.xs(ticker, level=1, axis=1).dropna()
        
    return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data():
    """Fetches all 57 tickers in ONE single network request to bypass cloud rate-limits."""
    tickers_str = " ".join(SCAN_POOL)
    try:
        data = yf.download(
            tickers=tickers_str,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True
        )
        return data
    except Exception:
        return pd.DataFrame()

def run_scanner_and_analysis():
    batch_df = fetch_batch_data()
    if batch_df.empty:
        return []

    qualified_candidates = []

    for ticker in SCAN_POOL:
        clean_sym = ticker.replace(".NS", "")
        hist = extract_ticker_data(batch_df, ticker)

        if hist.empty or len(hist) < 50:
            continue

        close_series = hist["Close"]
        current_price = round(float(close_series.iloc[-1]), 2)
        prev_close = round(float(close_series.iloc[-2]), 2)
        pct_change = round(((current_price - prev_close) / prev_close) * 100.0, 2)

        # 200 SMA / 50 SMA Structural Trend Check
        sma_200 = (
            close_series.rolling(window=200).mean().iloc[-1]
            if len(close_series) >= 200
            else close_series.rolling(window=50).mean().iloc[-1]
        )
        is_above_trend = current_price >= sma_200

        # Relative Volume (RVol) - 20 SMA
        vol_series = hist["Volume"]
        vol_sma = vol_series.rolling(window=20).mean()
        last_vol = vol_series.iloc[-1]
        avg_vol = vol_sma.iloc[-1] if vol_sma.iloc[-1] > 0 else 1.0
        rvol = round(float(last_vol / avg_vol), 2)

        # RSI (14) Momentum
        rsi_series = calculate_rsi(close_series, 14)
        rsi_val = (
            round(float(rsi_series.iloc[-1]), 1)
            if not pd.isna(rsi_series.iloc[-1])
            else 50.0
        )

        # EXACT MOMENTUM CRITERIA
        if is_above_trend and rsi_val >= 48.0 and rvol >= 0.9:
            flow_tag = (
                "Accumulation"
                if (rvol >= 1.4 and pct_change >= 0)
                else (
                    "Distribution"
                    if (rvol >= 1.4 and pct_change < 0)
                    else "Active Rotation"
                )
            )
            is_etf = (
                ticker in NSE_ETFS_UNIVERSE
                or any(x in clean_sym for x in ["BEES", "ETF", "MON", "FANG", "LIQUID"])
            )
            asset_type = "ETF" if is_etf else "Stock"

            sl_pct = 0.02 if is_etf else 0.035
            tgt_pct = 0.04 if is_etf else 0.07
            sl_price = round(current_price * (1 - sl_pct), 2)
            tgt_price = round(current_price * (1 + tgt_pct), 2)
            rec_alloc = 50000 if is_etf else 25000

            qualified_candidates.append({
                "symbol": clean_sym,
                "full_ticker": ticker,
                "type": asset_type,
                "cmp": current_price,
                "pct_change": pct_change,
                "rvol": rvol,
                "rsi": rsi_val,
                "sma_200": round(float(sma_200), 2),
                "flow_status": flow_tag,
                "sl": sl_price,
                "target": tgt_price,
                "rec_allocation": rec_alloc
            })

    # Sort descending by RVol and Day Change
    if qualified_candidates:
        qualified_candidates.sort(key=lambda x: (x["rvol"], x["pct_change"]), reverse=True)

    return qualified_candidates
