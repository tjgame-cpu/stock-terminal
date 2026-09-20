import streamlit as st
import pandas as pd
from engine import PaperBrokerAdapter, get_live_price, check_market_status
from strategy import run_scanner_and_analysis

st.set_page_config(page_title="Paper Terminal", layout="wide", initial_sidebar_state="collapsed")

# --- LIVE MARKET / HOLIDAY BANNER ---
is_market_open, market_msg = check_market_status()
if is_market_open:
    st.success(f"🟢 **LIVE MARKET**: {market_msg}")
else:
    st.warning(f"🟡 **MARKET CLOSED**: {market_msg}")

st.title("⚡ Paper Trading Terminal")

tab_scan, tab_positions, tab_history = st.tabs(["🔍 Opportunities & Scan", "📊 Active Positions", "📈 Performance Ledger"])

# ==================== TAB 1: OPPORTUNITIES & SCAN ====================
with tab_scan:
    st.subheader("Market Scanner & Discovery Engine")
    
    if st.button("🚀 Run Finder & Analysis", use_container_width=True):
        with st.spinner("Scanning universe across Stocks & ETFs..."):
            st.session_state["candidates"] = run_scanner_and_analysis()

    candidates = st.session_state.get("candidates", [])

    if not candidates:
        st.info("Tap 'Run Finder & Analysis' to scan the market for momentum opportunities.")
    else:
        st.caption(f"Found **{len(candidates)} qualified instruments**. Tap any stock or ETF below to configure and place your order:")

        for item in candidates:
            sym = item["symbol"]
            cmp = item["cmp"]
            asset_type = item["type"]
            badge = "🪙 ETF" if asset_type == "ETF" else "🏢 STOCK"
            flow = item["flow_status"]
            change = item["pct_change"]
            change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"

            # Accordion card: Header shows overview; inputs are hidden until tapped
            header_title = f"{badge} | **{sym}** — ₹{cmp:,.2f} ({change_str}) | RVol: {item['rvol']}x | {flow}"
            
            with st.expander(header_title):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("CMP", f"₹{cmp:,.2f}")
                m2.metric("RSI (14)", f"{item['rsi']}")
                m3.metric("Trend Floor", f"₹{item['sma_trend']:,.2f}")
                m4.metric("Flow Status", item['flow_status'])

                st.divider()
                st.caption(f"💡 System Recommended Capital: **₹{item['rec_allocation']:,}**")

                # Investment input
                target_alloc = st.number_input(
                    "Amount you want to invest (₹)",
                    min_value=500,
                    value=int(item["rec_allocation"]),
                    step=1000,
                    key=f"alloc_{sym}"
                )

                # Real-time share count and cash calculation
                calc_qty = int(target_alloc // cmp) if cmp > 0 else 0
                actual_invested = round(calc_qty * cmp, 2)
                balance_left = round(target_alloc - actual_invested, 2)

                st.markdown(
                    f"**Investment Breakdown:**\n"
                    f"* Calculated Quantity: **{calc_qty} units**\n"
                    f"* Actual Amount to be Invested: **₹{actual_invested:,.2f}**\n"
                    f"* Unused Balance: **₹{balance_left:,.2f}**"
                )

                col_sl, col_tgt = st.columns(2)
                custom_sl = col_sl.number_input("Stop Loss (₹)", value=float(item["sl"]), key=f"sl_{sym}")
                custom_tgt = col_tgt.number_input("Target (₹)", value=float(item["target"]), key=f"tgt_{sym}")

                btn_label = f"Queue AMO Buy: {sym}" if not is_market_open else f"Punch Buy Order: {sym}"
                
                if st.button(btn_label, key=f"btn_{sym}", use_container_width=True):
                    if calc_qty < 1:
                        st.error(f"Allocation ₹{target_alloc} is too low to buy 1 unit at ₹{cmp:,.2f}.")
                    else:
                        success, msg = PaperBrokerAdapter.buy(
                            symbol=sym,
                            asset_type=asset_type,
                            qty=calc_qty,
                            actual_invested=actual_invested,
                            cmp=cmp,
                            sl=custom_sl,
                            target=custom_tgt,
                            is_amo=not is_market_open
                        )
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

# ==================== TAB 2: ACTIVE POSITIONS ====================
with tab_positions:
    col_t, col_btn = st.columns([3, 1])
    col_t.subheader("Active Positions")
    if col_btn.button("🔄 Refresh Rates", use_container_width=True):
        st.rerun()

    positions_df = PaperBrokerAdapter.get_open_positions()

    if positions_df.empty:
        st.info("No active positions. Expand any stock in 'Opportunities & Scan' to place a paper trade.")
    else:
        total_unrealized_pnl = 0.0
        total_capital = 0.0

        for _, row in positions_df.iterrows():
            pos_id = row['id']
            sym = row['symbol']
            asset_type = row.get('type', 'Stock')
            qty = int(row['qty'])
            buy_price = float(row['buy_price'])
            sl = float(row['sl_price'])
            target = float(row['target_price'])
            entry_time = row['entry_time']
            order_mode = row.get('order_mode', 'REGULAR')

            # Live price check
            cmp = get_live_price(sym) or buy_price
            pnl = round((cmp - buy_price) * qty, 2)
            pnl_pct = round(((cmp - buy_price) / buy_price) * 100, 2)
            
            total_capital += (buy_price * qty)
            total_unrealized_pnl += pnl

            # AUTO SL / TARGET MONITOR (Triggers during open market sessions)
            if is_market_open:
                if cmp <= sl:
                    PaperBrokerAdapter.sell(pos_id, sym, asset_type, qty, buy_price, cmp, "Stop-Loss Hit 🔴", entry_time)
                    st.warning(f"Auto-Trigger: SL Hit for {sym} at ₹{cmp:,.2f}")
                    st.rerun()
                elif cmp >= target:
                    PaperBrokerAdapter.sell(pos_id, sym, asset_type, qty, buy_price, cmp, "Target Hit 🟢", entry_time)
                    st.success(f"Auto-Trigger: Target Hit for {sym} at ₹{cmp:,.2f}")
                    st.rerun()

            # Mobile Position Card
            with st.container(border=True):
                h1, h2 = st.columns(2)
                mode_tag = " [AMO]" if order_mode == "AMO" else ""
                h1.markdown(f"**{sym}**{mode_tag} ({qty} units)")
                h2.markdown(f"**P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)**")

                c1, c2, c3 = st.columns(3)
                c1.caption(f"Buy Price: ₹{buy_price:,.2f}")
                c2.caption(f"CMP: ₹{cmp:,.2f}")
                c3.caption(f"SL: ₹{sl:,.2f} | Tgt: ₹{target:,.2f}")

                if st.button("Exit Position ⏹️", key=f"exit_{pos_id}", use_container_width=True):
                    PaperBrokerAdapter.sell(pos_id, sym, asset_type, qty, buy_price, cmp, "Manual Exit ⏹️", entry_time)
                    st.info(f"Position closed for {sym} at ₹{cmp:,.2f}")
                    st.rerun()

        st.divider()
        c_tot_cap, c_tot_pnl = st.columns(2)
        c_tot_cap.metric("Total Invested Capital", f"₹{total_capital:,.2f}")
        c_tot_pnl.metric("Total Unrealized P&L", f"₹{total_unrealized_pnl:+,.2f}")

# ==================== TAB 3: PERFORMANCE LEDGER ====================
with tab_history:
    st.subheader("Performance & Closed Trades")
    history_df = PaperBrokerAdapter.get_history()

    if history_df.empty:
        st.info("No completed trades yet. Once positions are closed manually or via SL/Target hits, your metrics, profit/loss ratio, and historical ledger will display here.")
    else:
        total_trades = len(history_df)
        wins = history_df[history_df['pnl'] > 0]
        losses = history_df[history_df['pnl'] <= 0]
        
        total_profit = wins['pnl'].sum()
        total_loss = abs(losses['pnl'].sum())
        net_pnl = history_df['pnl'].sum()
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        profit_loss_ratio = round(total_profit / total_loss, 2) if total_loss > 0 else (round(total_profit, 2) if total_profit > 0 else 0.0)

        col1, col2 = st.columns(2)
        col1.metric("Net Realized P&L", f"₹{net_pnl:+,.2f}")
        col2.metric("Win Rate", f"{win_rate:.1f}%")

        col3, col4 = st.columns(2)
        col3.metric("Profit / Loss Ratio", f"{profit_loss_ratio}")
        col4.metric("Total Completed Trades", f"{total_trades}")

        st.divider()
        st.dataframe(
            history_df[['symbol', 'type', 'qty', 'buy_price', 'sell_price', 'pnl', 'pnl_pct', 'exit_reason', 'exit_time']],
            use_container_width=True,
            hide_index=True
        )
