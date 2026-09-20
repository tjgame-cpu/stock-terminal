"""
TARGETED ANALYSIS MODULE
Runs momentum screening formulas on user-provided symbols.
"""
import pandas as pd
import yfinance as yf
from engine import format_ticker_symbol

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def evaluate_pasted_symbols(raw_input_text):
    """
    Parses comma-separated tickers and applies structural trend,
    RVol, RSI momentum, and risk/reward allocation math.
    """
    # Clean input
    raw_list = [s.strip().upper().replace(".NS", "") for s in raw_input_text.split(",") if s.strip()]
    if not raw_list:
        return []

    evaluated_candidates = []

    for sym in raw_list:
        formatted = format_ticker_symbol(sym)
        try:
            t = yf.Ticker(formatted)
            hist = t.history(period="1y")

            if hist.empty or len(hist) < 30:
                continue

            close_series = hist["Close"]
            current_price = round(float(close_series.iloc[-1]), 2)
            prev_close = round(float(close_series.iloc[-2]), 2)
            pct_change = round(((current_price - prev_close) / prev_close) * 100.0, 2)

            # 200 SMA / 50 SMA Trend Floor
            sma_trend = (
                close_series.rolling(window=200).mean().iloc[-1]
                if len(close_series) >= 200
                else close_series.rolling(window=50).mean().iloc[-1]
            )

            # 20-period Relative Volume (RVol)
            vol_series = hist["Volume"]
            vol_sma = vol_series.rolling(window=20).mean()
            last_vol = vol_series.iloc[-1]
            avg_vol = vol_sma.iloc[-1] if vol_sma.iloc[-1] > 0 else 1.0
            rvol = round(float(last_vol / avg_vol), 2)

            # 14-period RSI
            rsi_series = calculate_rsi(close_series, 14)
            rsi_val = round(float(rsi_series.iloc[-1]), 1) if not pd.isna(rsi_series.iloc[-1]) else 50.0

            # Flow Footprint
            flow_tag = (
                "Accumulation 🟢" if (rvol >= 1.4 and pct_change >= 0)
                else ("Distribution 🔴" if (rvol >= 1.4 and pct_change < 0) else "Active Rotation 🟡")
            )

            is_etf = any(x in sym for x in ["BEES", "ETF", "MON", "FANG", "LIQUID", "GOLD", "SILVER"])
            asset_type = "ETF" if is_etf else "Stock"

            sl_pct = 0.02 if is_etf else 0.035
            tgt_pct = 0.04 if is_etf else 0.07

            evaluated_candidates.append({
                "symbol": sym,
                "formatted": formatted,
                "type": asset_type,
                "cmp": current_price,
                "pct_change": pct_change,
                "rvol": rvol,
                "rsi": rsi_val,
                "sma_trend": round(float(sma_trend), 2),
                "flow_status": flow_tag,
                "sl": round(current_price * (1 - sl_pct), 2),
                "target": round(current_price * (1 + tgt_pct), 2),
                "rec_allocation": 50000 if is_etf else 25000
            })
        except Exception:
            continue

    if evaluated_candidates:
        evaluated_candidates.sort(key=lambda x: (x["rvol"], x["pct_change"]), reverse=True)

    return evaluated_candidates
