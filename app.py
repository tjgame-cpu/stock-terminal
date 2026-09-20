import streamlit as st
import pandas as pd
from engine import PaperBrokerAdapter, get_live_quote, check_market_status
from strategy import evaluate_pasted_symbols

st.set_page_config(page_title="Paper Terminal", layout="wide", initial_sidebar_state="collapsed")

# --- MARKET STATUS BANNER ---
is_market_open, market_msg = check_market_status()
if is_market_open:
    st.success(f"🟢 **LIVE MARKET**: {market_msg}")
else:
    st.warning(f"🟡 **MARKET CLOSED**: {market_msg}")

st.title("⚡ Paper Trading Terminal")

tab_analysis, tab_tv_search, tab_positions, tab_history = st.tabs([
    "🎯 Targeted Analysis", 
    "🔍 Search & Watchlist", 
    "📊 Active Positions", 
    "📈 Performance Ledger"
])

# ==================== TAB 1: TARGETED ANALYSIS ====================
with tab_analysis:
    st.subheader("Direct Symbol Screener & Evaluation")
    st.caption("Paste tickers separated by a comma (e.g. from your Screener V3 string):")

    default_sample = "TATASTEEL, RELIANCE, KEI, TRENT, GOLDBEES, HAL, BEL, BSE"
    input_text = st.text_area(
        "Paste comma-separated tickers:",
        value=st.session_state.get("saved_paste_text", default_sample),
        height=90
    )

    if st.button("🚀 Run Analysis on Tickers", use_container_width=True):
        st.session_state["saved_paste_text"] = input_text
        with st.spinner("Evaluating technical criteria on pasted instruments..."):
            st.session_state["evaluated_list"] = evaluate_pasted_symbols(input_text)

    candidates = st.session_state.get("evaluated_list", [])

    if candidates:
        st.markdown(f"### 📋 Evaluated Results ({len(candidates)})")
        st.caption("Tap any card below to view metrics, adjust capital, and punch orders:")

        for item in candidates:
            sym = item["symbol"]
            cmp = item["cmp"]
            asset_type = item["type"]
            badge = "🪙 ETF" if asset_type == "ETF" else "🏢 Stock"
            flow = item["flow_status"]
            change = item["pct_change"]
            change_sign = "+" if change >= 0 else ""

            card_title = f"{sym} | {badge} | ₹{cmp:,.2f} ({change_sign}{change:.2f}%) | RVol: {item['rvol']}x | {flow}"

            with st.expander(card_title):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("LTP (CMP)", f"₹{cmp:,.2f}", f"{change_sign}{change:.2f}%")
                m2.metric("RVol (20)", f"{item['rvol']}x")
                m3.metric("RSI (14)", f"{item['rsi']}")
                m4.metric("Trend Floor", f"₹{item['sma_trend']:,.2f}")

                st.markdown(f"**Footprint:** `{flow}` | **Asset Class:** `{asset_type}`")
                st.divider()

                # Order Execution Inputs
                st.markdown("#### 💼 Order Execution & Sizing")
                st.caption(f"💡 Recommended Allocation: **₹{item['rec_allocation']:,}**")

                target_alloc = st.number_input(
                    "Capital to allocate (₹)",
                    min_value=500,
                    value=int(item["rec_allocation"]),
                    step=1000,
                    key=f"eval_alloc_{sym}"
                )

                calc_qty = int(target_alloc // cmp) if cmp > 0 else 0
                actual_invested = round(calc_qty * cmp, 2)
                balance_left = round(target_alloc - actual_invested, 2)

                st.markdown(
                    f"* **Shares to be Purchased:** `{calc_qty} units`\n"
                    f"* **Actual Amount Invested:** `₹{actual_invested:,.2f}`\n"
                    f"* **Unused Balance:** `₹{balance_left:,.2f}`"
                )

                col_sl, col_tgt = st.columns(2)
                custom_sl = col_sl.number_input("Stop Loss (₹)", value=float(item["sl"]), key=f"eval_sl_{sym}")
                custom_tgt = col_tgt.number_input("Target (₹)", value=float(item["target"]), key=f"eval_tgt_{sym}")

                btn_label = f"Queue AMO Buy Order: {sym}" if not is_market_open else f"Punch Buy Order: {sym}"

                if st.button(btn_label, key=f"eval_btn_{sym}", use_container_width=True):
                    if calc_qty < 1:
                        st.error("Capital is too low to purchase 1 share.")
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

# ==================== TAB 2: SEARCH & WATCHLIST ====================
with tab_tv_search:
    st.subheader("🔍 Universal Market Search & Watchlist")
    st.caption("Search any Stock, ETF, Commodity (e.g. INFY, GOLDBEES, SILVERBEES, GC=F, CL=F):")

    c_search_input, c_search_btn = st.columns([3, 1])
    query = c_search_input.text_input("Symbol search", placeholder="e.g. RELIANCE, GOLDBEES, INFY", label_visibility="collapsed")
    execute_search = c_search_btn.button("Search", use_container_width=True)

    if query and execute_search:
        quote = get_live_quote(query)
        if quote:
            st.session_state["active_search_quote"] = quote
        else:
            st.error(f"Could not find live quote for '{query}'. Verify ticker symbol.")

    active_q = st.session_state.get("active_search_quote")
    if active_q:
        q_sym = active_q["symbol"]
        q_price = active_q["price"]
        q_chg = active_q["pct_change"]
        q_sign = "+" if q_chg >= 0 else ""

        with st.container(border=True):
            sc1, sc2 = st.columns([2, 1])
            sc1.markdown(f"### **{q_sym}**")
            sc2.metric("LTP", f"₹{q_price:,.2f}", f"{q_sign}{q_chg:.2f}%")

            if st.button(f"⭐ Add {q_sym} to Watchlist", use_container_width=True):
                if PaperBrokerAdapter.add_to_watchlist(q_sym):
                    st.success(f"{q_sym} added to Watchlist!")
                    st.rerun()
                else:
                    st.info(f"{q_sym} is already in Watchlist.")

            st.divider()
            st.markdown("#### ⚡ Order Execution Ticket")
            s_alloc = st.number_input("Investment Amount (₹)", min_value=500, value=25000, step=1000, key="quick_alloc")
            s_qty = int(s_alloc // q_price) if q_price > 0 else 0
            s_invested = round(s_qty * q_price, 2)

            st.caption(f"Will buy **{s_qty} units** totaling **₹{s_invested:,.2f}**")

            col_q_sl, col_q_tgt = st.columns(2)
            s_sl = col_q_sl.number_input("Stop Loss (₹)", value=round(q_price * 0.965, 2), key="quick_sl")
            s_tgt = col_q_tgt.number_input("Target (₹)", value=round(q_price * 1.07, 2), key="quick_tgt")

            buy_lbl = f"Queue AMO Buy: {q_sym}" if not is_market_open else f"Punch Buy Order: {q_sym}"
            if st.button(buy_lbl, key="quick_buy_btn", use_container_width=True):
                if s_qty < 1:
                    st.error("Capital is too low to purchase 1 unit.")
                else:
                    success, msg = PaperBrokerAdapter.buy(
                        symbol=q_sym,
                        asset_type="Manual",
                        qty=s_qty,
                        actual_invested=s_invested,
                        cmp=q_price,
                        sl=s_sl,
                        target=s_tgt,
                        is_amo=not is_market_open
                    )
                    if success:
                        st.success(msg)
                        st.rerun()

    # --- PERSISTENT WATCHLIST SECTION ---
    st.divider()
    st.subheader("⭐ Saved Watchlist")
    wl_df = PaperBrokerAdapter.get_watchlist()

    if wl_df.empty:
        st.info("Watchlist is currently empty. Search symbols above to add them.")
    else:
        for _, row in wl_df.iterrows():
            w_sym = row['symbol']
            w_quote = get_live_quote(w_sym)
            w_price = w_quote["price"] if w_quote else 0.0
            w_chg = w_quote["pct_change"] if w_quote else 0.0
            w_sign = "+" if w_chg >= 0 else ""

            with st.container(border=True):
                c_w1, c_w2, c_w3 = st.columns([2, 2, 1])
                c_w1.markdown(f"**{w_sym}**")
                c_w2.markdown(f"₹{w_price:,.2f} ({w_sign}{w_chg:.2f}%)")
                if c_w3.button("🗑️", key=f"del_wl_{w_sym}"):
                    PaperBrokerAdapter.remove_from_watchlist(w_sym)
                    st.rerun()

# ==================== TAB 3: ACTIVE POSITIONS ====================
with tab_positions:
    col_t, col_btn = st.columns([3, 1])
    col_t.subheader("Active Positions")
    if col_btn.button("🔄 Refresh Rates", use_container_width=True):
        st.rerun()

    positions_df = PaperBrokerAdapter.get_open_positions()

    if positions_df.empty:
        st.info("No active positions running.")
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

            quote = get_live_quote(sym)
            cmp = quote["price"] if quote else buy_price
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

# ==================== TAB 4: PERFORMANCE LEDGER ====================
with tab_history:
    st.subheader("Performance & Closed Trades")
    history_df = PaperBrokerAdapter.get_history()

    if history_df.empty:
        st.info("No completed trades logged yet.")
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
