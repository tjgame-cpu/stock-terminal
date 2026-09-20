import streamlit as st
import pandas as pd
from engine import PaperBrokerAdapter, get_live_price, check_market_status
from strategy import run_scanner_and_analysis

st.set_page_config(page_title="Paper Terminal", layout="wide", initial_sidebar_state="collapsed")

# --- MARKET STATUS HEADER ---
is_market_open, market_msg = check_market_status()
if is_market_open:
    st.success(f"🟢 **LIVE MARKET**: {market_msg}")
else:
    st.warning(f"🟡 **MARKET CLOSED**: {market_msg}")

st.title("⚡ Paper Trading Terminal")

tab_scan, tab_positions, tab_history = st.tabs(["🔍 Discovery Scanner", "📊 Active Positions", "📈 Performance Ledger"])

# ==================== TAB 1: DISCOVERY SCANNER ====================
with tab_scan:
    col_t, col_b = st.columns([3, 1])
    col_t.subheader("Discovery Engine Pipeline")

    if col_b.button("🚀 Run Discovery Scan", use_container_width=True):
        st.cache_data.clear()  # Clear cache on manual run to pull fresh rates
        with st.spinner("Downloading and processing all 57 instruments in batch..."):
            st.session_state["candidates"] = run_scanner_and_analysis()

    candidates = st.session_state.get("candidates", [])

    if not candidates:
        st.info("Tap 'Run Discovery Scan' to execute momentum screening across 57 stocks and ETFs.")
    else:
        st.markdown(f"### 🎯 DISCOVERY SCAN COMPLETE")
        st.markdown(f"**📊 Qualified Assets:** `{len(candidates)} candidates`")

        # Ready-to-Paste Screener String
        ticker_list_str = ", ".join([c["symbol"] for c in candidates])
        with st.expander("📋 Click to view Ready-To-Paste String for Screener V3"):
            st.code(ticker_list_str, language="text")

        st.caption("Tap any qualified asset below to configure capital allocation and punch an order:")

        for item in candidates:
            sym = item["symbol"]
            cmp = item["cmp"]
            asset_type = item["type"]
            flow = item["flow_status"]
            change = item["pct_change"]
            change_sign = "+" if change >= 0 else ""

            # Card Header matching terminal screener format
            card_title = (
                f"[+] QUALIFIED: {sym:<10} | Price: ₹{cmp:<8,.2f} ({change_sign}{change:.2f}%) | "
                f"RVol: {item['rvol']}x | RSI: {item['rsi']} | {flow}"
            )

            with st.expander(card_title):
                # 4-Metric Grid
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("LTP (CMP)", f"₹{cmp:,.2f}", f"{change_sign}{change:.2f}%")
                c2.metric("Relative Vol (RVol)", f"{item['rvol']}x")
                c3.metric("RSI (14)", f"{item['rsi']}")
                c4.metric("200/50 SMA Floor", f"₹{item['sma_200']:,.2f}")

                st.markdown(f"**Asset Class:** `{asset_type}` | **Flow Footprint:** `{flow}`")
                st.divider()

                # Execution & Sizing Inputs (Contained inside expander)
                st.markdown("#### 💼 Order Allocation & Execution")
                st.caption(f"💡 Recommended Allocation: **₹{item['rec_allocation']:,}**")

                target_alloc = st.number_input(
                    "Capital to allocate (₹)",
                    min_value=500,
                    value=int(item["rec_allocation"]),
                    step=1000,
                    key=f"alloc_{sym}"
                )

                # Real-Time Calculations
                calc_qty = int(target_alloc // cmp) if cmp > 0 else 0
                actual_invested = round(calc_qty * cmp, 2)
                balance_left = round(target_alloc - actual_invested, 2)

                st.markdown(
                    f"* **Calculated Shares/Units:** `{calc_qty} units`\n"
                    f"* **Actual Amount Invested:** `₹{actual_invested:,.2f}`\n"
                    f"* **Unallocated Balance Left:** `₹{balance_left:,.2f}`"
                )

                col_sl, col_tgt = st.columns(2)
                custom_sl = col_sl.number_input("Stop Loss (₹)", value=float(item["sl"]), key=f"sl_{sym}")
                custom_tgt = col_tgt.number_input("Target (₹)", value=float(item["target"]), key=f"tgt_{sym}")

                btn_label = f"Queue AMO Buy Order: {sym}" if not is_market_open else f"Punch Buy Order: {sym}"

                if st.button(btn_label, key=f"btn_{sym}", use_container_width=True):
                    if calc_qty < 1:
                        st.error(f"Allocation ₹{target_alloc} is too low to purchase 1 share at ₹{cmp:,.2f}.")
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
        st.info("No active positions. Expand any asset in 'Discovery Scanner' to place a paper order.")
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

            cmp = get_live_price(sym) or buy_price
            pnl = round((cmp - buy_price) * qty, 2)
            pnl_pct = round(((cmp - buy_price) / buy_price) * 100, 2)

            total_capital += (buy_price * qty)
            total_unrealized_pnl += pnl

            # AUTO SL / TARGET MONITOR
            if is_market_open:
                if cmp <= sl:
                    PaperBrokerAdapter.sell(pos_id, sym, asset_type, qty, buy_price, cmp, "Stop-Loss Hit 🔴", entry_time)
                    st.warning(f"Auto-Trigger: SL Hit for {sym} at ₹{cmp:,.2f}")
                    st.rerun()
                elif cmp >= target:
                    PaperBrokerAdapter.sell(pos_id, sym, asset_type, qty, buy_price, cmp, "Target Hit 🟢", entry_time)
                    st.success(f"Auto-Trigger: Target Hit for {sym} at ₹{cmp:,.2f}")
                    st.rerun()

            with st.container(border=True):
                h1, h2 = st.columns(2)
                mode_tag = " [AMO]" if order_mode == "AMO" else ""
                h1.markdown(f"**{sym}**{mode_tag} ({qty} units)")
                h2.markdown(f"**P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)**")

                c1, c2, c3 = st.columns(3)
                c1.caption(f"Buy: ₹{buy_price:,.2f}")
                c2.caption(f"CMP: ₹{cmp:,.2f}")
                c3.caption(f"SL: ₹{sl:,.2f} | Tgt: ₹{target:,.2f}")

                if st.button("Exit Position ⏹️", key=f"exit_{pos_id}", use_container_width=True):
                    PaperBrokerAdapter.sell(pos_id, sym, asset_type, qty, buy_price, cmp, "Manual Exit ⏹️", entry_time)
                    st.info(f"Position closed for {sym} at ₹{cmp:,.2f}")
                    st.rerun()

        st.divider()
        c_tot_cap, c_tot_pnl = st.columns(2)
        c_tot_cap.metric("Total Capital Invested", f"₹{total_capital:,.2f}")
        c_tot_pnl.metric("Total Unrealized P&L", f"₹{total_unrealized_pnl:+,.2f}")

# ==================== TAB 3: PERFORMANCE LEDGER ====================
with tab_history:
    st.subheader("Performance & Closed Trades")
    history_df = PaperBrokerAdapter.get_history()

    if history_df.empty:
        st.info("No completed trades yet. Once positions are closed manually or via SL/Target hits, your metrics and trade ledger will appear here.")
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
