import streamlit as st
import pandas as pd
from engine import PaperBrokerAdapter, get_live_price
from strategy import run_scanner_and_analysis

# Mobile display config
st.set_page_config(page_title="Paper Trading Terminal", layout="wide", initial_sidebar_state="collapsed")

st.title("📈 Stock Paper Terminal")

tab_scan, tab_positions, tab_history = st.tabs(["🔍 Opportunities", "⚡ Live Positions", "📊 Ledger & Ratios"])

# ==================== TAB 1: SCANNER & INVEST ====================
with tab_scan:
    st.subheader("Market Scanner & Allocation")
    
    if st.button("🚀 Run Finder & Analysis", use_container_width=True):
        with st.spinner("Scanning market candidates..."):
            st.session_state["candidates"] = run_scanner_and_analysis()

    candidates = st.session_state.get("candidates", [])

    if not candidates:
        st.info("Tap 'Run Finder & Analysis' to scan the market.")
    else:
        for item in candidates:
            sym = item["symbol"]
            with st.container(border=True):
                st.markdown(f"### **{sym}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Est. CMP", f"₹{item['cmp']}")
                c2.metric("Analysis SL", f"₹{item['sl']}")
                c3.metric("Target", f"₹{item['target']}")
                
                st.caption(f"💡 Recommended Capital: **₹{item['rec_allocation']:,}**")

                # Editable Inputs
                alloc = st.number_input(
                    f"Capital to Invest (₹)", 
                    min_value=500, 
                    value=int(item["rec_allocation"]), 
                    step=1000, 
                    key=f"alloc_{sym}"
                )
                
                col_sl, col_tgt = st.columns(2)
                custom_sl = col_sl.number_input("SL (₹)", value=float(item["sl"]), key=f"sl_{sym}")
                custom_tgt = col_tgt.number_input("Target (₹)", value=float(item["target"]), key=f"tgt_{sym}")

                if st.button(f"Punch Invest Order: {sym}", key=f"btn_{sym}", use_container_width=True):
                    success, msg = PaperBrokerAdapter.buy(sym, alloc, custom_sl, custom_tgt)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# ==================== TAB 2: ACTIVE POSITIONS & LIVE P&L ====================
with tab_positions:
    col_t, col_btn = st.columns([3, 1])
    col_t.subheader("Active Positions")
    if col_btn.button("🔄 Refresh", use_container_width=True):
        st.rerun()

    positions_df = PaperBrokerAdapter.get_open_positions()

    if positions_df.empty:
        st.info("No active positions currently running.")
    else:
        total_unrealized_pnl = 0.0

        for _, row in positions_df.iterrows():
            pos_id = row['id']
            sym = row['symbol']
            qty = int(row['qty'])
            buy_price = float(row['buy_price'])
            sl = float(row['sl_price'])
            target = float(row['target_price'])
            entry_time = row['entry_time']

            # Live price check
            cmp = get_live_price(sym) or buy_price
            pnl = round((cmp - buy_price) * qty, 2)
            pnl_pct = round(((cmp - buy_price) / buy_price) * 100, 2)
            total_unrealized_pnl += pnl

            # AUTO-EXIT LOGIC (SL / Target Breach Check)
            if cmp <= sl:
                PaperBrokerAdapter.sell(pos_id, sym, qty, buy_price, cmp, "Stop-Loss Hit 🔴", entry_time)
                st.warning(f"Auto-Trigger: SL Hit for {sym} at ₹{cmp}")
                st.rerun()
            elif cmp >= target:
                PaperBrokerAdapter.sell(pos_id, sym, qty, buy_price, cmp, "Target Hit 🟢", entry_time)
                st.success(f"Auto-Trigger: Target Hit for {sym} at ₹{cmp}")
                st.rerun()

            # Render Trade Card
            with st.container(border=True):
                h1, h2 = st.columns(2)
                h1.markdown(f"**{sym}** ({qty} shares)")
                h2.markdown(f"**P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)**")

                m1, m2, m3 = st.columns(3)
                m1.caption(f"Buy: ₹{buy_price}")
                m2.caption(f"CMP: ₹{cmp}")
                m3.caption(f"SL: ₹{sl}")

                if st.button("Exit Position ⏹️", key=f"exit_{pos_id}", use_container_width=True):
                    PaperBrokerAdapter.sell(pos_id, sym, qty, buy_price, cmp, "Manual Exit ⏹️", entry_time)
                    st.info(f"Closed {sym} at ₹{cmp}")
                    st.rerun()

        st.divider()
        st.metric("Total Unrealized P&L", f"₹{total_unrealized_pnl:+,.2f}")

# ==================== TAB 3: PERFORMANCE & RATIOS ====================
with tab_history:
    st.subheader("Performance & Trade Ledger")
    history_df = PaperBrokerAdapter.get_history()

    if history_df.empty:
        st.info("No closed trades logged yet.")
    else:
        total_trades = len(history_df)
        wins = history_df[history_df['pnl'] > 0]
        losses = history_df[history_df['pnl'] <= 0]
        
        total_profit = wins['pnl'].sum()
        total_loss = abs(losses['pnl'].sum())
        net_pnl = history_df['pnl'].sum()
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        profit_loss_ratio = round(total_profit / total_loss, 2) if total_loss > 0 else (round(total_profit, 2) if total_profit > 0 else 0.0)

        # Performance Grid
        c1, c2 = st.columns(2)
        c1.metric("Net Realized P&L", f"₹{net_pnl:+,.2f}")
        c2.metric("Win Rate", f"{win_rate:.1f}%")

        c3, c4 = st.columns(2)
        c3.metric("Profit/Loss Ratio", f"{profit_loss_ratio}")
        c4.metric("Total Closed Trades", f"{total_trades}")

        st.divider()
        st.dataframe(
            history_df[['symbol', 'qty', 'buy_price', 'sell_price', 'pnl', 'pnl_pct', 'exit_reason', 'exit_time']],
            use_container_width=True,
            hide_index=True
        )
