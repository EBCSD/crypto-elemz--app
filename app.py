import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# 1. ALAPBEÁLLÍTÁSOK (Dizájn és stílusblokk teljesen törölve a hibák elkerülésére)
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

st.title("⚡ ALGO ICT PRO V2")
st.caption("Advanced Institutional Liquidity Terminal | Powered by Bitget")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot"])

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Keresési Mód")
run_scanner = st.sidebar.checkbox("Automata Piacszkenner Indítása", value=True)

# API Inicializálás
exch = getattr(ccxt, exchange_id)({
    'enableRateLimit': True,
    'options': {'defaultType': 'future' if market_type == "Futures" else 'spot'}
})
exch.load_markets()

@st.cache_data(ttl=120)
def get_active_markets():
    try:
        tickers = exch.fetch_tickers()
        pairs = []
        for sym, t in tickers.items():
            if 'USDT' in sym and '/' in sym:
                pairs.append(sym)
        return sorted(list(set(pairs)))
    except:
        return sorted(list(set([s for s in exch.markets.keys() if 'USDT' in s])))

filtered_symbols = get_active_markets()

# HAJSZÁLPONTOS INVERZ FVG MOTOR
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':') if ':' in pair_symbol else pair_symbol

        # HTF lekérése (1h és 4h kombinált likviditás)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: 
            return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        timeframes = ['15m', '5m']
        chosen_tf = '15m'
        df_ltf = pd.DataFrame()
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_ifvg = False
        fvg_idx = None
        fvg_type = "NONE"

        for tf in timeframes:
            ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=tf, limit=40)
            if not ltf_ohlcv: 
                continue
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
            length = len(df_ltf)

            for i in range(length - 5, 2, -1):
                if df_ltf['high'].iloc[i] < df_ltf['low'].iloc[i+2]:
                    o_fvg_high = float(df_ltf['low'].iloc[i+2])
                    o_fvg_low = float(df_ltf['high'].iloc[i])
                    
                    post_candles = df_ltf.iloc[i+2:]
                    was_buy_swept = post_candles['high'].max() >= htf_high or df_ltf['high'].max() >= htf_high
                    was_inversed = post_candles['close'].min() < o_fvg_low
                    
                    if was_buy_swept and was_inversed:
                        fvg_high, fvg_low = o_fvg_high, o_fvg_low
                        fvg_idx = i
                        fvg_type = "BEARISH_INVERSE"
                        found_ifvg = True
                        chosen_tf = tf
                        break
                
                elif df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]:
                    o_fvg_high = float(df_ltf['low'].iloc[i])
                    o_fvg_low = float(df_ltf['high'].iloc[i+2])
                    
                    post_candles = df_ltf.iloc[i+2:]
                    was_sell_swept = post_candles['low'].min() <= htf_low or df_ltf['low'].min() <= htf_low
                    was_inversed = post_candles['close'].max() > o_fvg_high
                    
                    if was_sell_swept and was_inversed:
                        fvg_high, fvg_low = o_fvg_high, o_fvg_low
                        fvg_idx = i
                        fvg_type = "BULLISH_INVERSE"
                        found_ifvg = True
                        chosen_tf = tf
                        break
            if found_ifvg: 
                break

        if df_ltf.empty or not found_ifvg: 
            return None

        current_price = float(df_ltf['close'].iloc[-1])
        fvg_mid = (fvg_high + fvg_low) / 2.0

        trade_signal = "DOBOZON BELÜL (Retest)"
        entry_price = fvg_mid
        sl = htf_high if fvg_type == "BEARISH_INVERSE" else htf_low
        tp = entry_price - (abs(entry_price - sl) * 3.5) if fvg_type == "BEARISH_INVERSE" else entry_price + (abs(entry_price - sl) * 3.5)

        # Minimum 1:3 RR szűrés
        risk_dist = abs(entry_price - sl)
        reward_dist = abs(tp - entry_price)
        rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
        if rr_ratio < 3.0: 
            return None

        # Tőkeáttétel számítás max 10x korláttal
        sl_percent = (risk_dist / entry_price) if entry_price > 0 else 0.01
        calculated_leverage = int((risk_percent / 100.0) / sl_percent) if sl_percent > 0 else 1
        leverage_suggestion = max(1, min(calculated_leverage, 10))

        if fvg_type == "BEARISH_INVERSE" and current_price <= (fvg_high * 1.005):
            trade_signal = "SHORT / SELL"
        elif fvg_type == "BULLISH_INVERSE" and current_price >= (fvg_low * 0.995):
            trade_signal = "LONG / BUY"

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": chosen_tf, "fvg_idx": fvg_idx,
            "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except:
        return None

# KÉPERNYŐ RAJZOLÓ MODUL (Sima Streamlit elemekkel)
def render_signal_block(display_name, res, unique_id):
    df_ltf = res["df_ltf"]
    length = len(df_ltf)
    
    st.subheader(f"🔥 {display_name} | Idősík: {res['chosen_tf']} | Irány: {res['trade_signal']}")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
        increasing_line_color='#089981', decreasing_line_color='#f23645',
        increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Ár"
    ))
    
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*length, name="HTF High", line=dict(color='#26a69a', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*length, name="HTF Low", line=dict(color='#ef5350', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*length, name="Belépő", line=dict(color='#29b6f6', width=2)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*length, name="SL", line=dict(color='#ff1744', width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp"]]*length, name="TP", line=dict(color='#00e676', width=1.5)))

    if res["fvg_high"] > 0 and res["fvg_idx"] is not None:
        s_idx = int(res["fvg_idx"])
        e_idx = int(min(s_idx + 15, length - 1))
        t_start = df_ltf['time'].iloc[s_idx]
        t_end = df_ltf['time'].iloc[e_idx]
        
        bx = [t_start, t_end, t_end, t_start, t_start]
        by = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
        
        fig.add_trace(go.Scatter(x=bx, y=by, fill="toself", fillcolor="rgba(255, 214, 0, 0.04)", line=dict(color='#ffd600', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[t_start, t_end], y=[res["fvg_mid"], res["fvg_mid"]], line=dict(color='#e040fb', width=2, dash='dash'), showlegend=False))

    y_pad = (df_ltf['high'].max() - df_ltf['low'].min()) * 0.15
    y_min = df_ltf['low'].min() - y_pad
    y_max = max(df_ltf['high'].max(), res["htf_high"]) + y_pad

    fig.update_layout(
        template="plotly_dark", xaxis_rangeslider_visible=False, height=400,
        paper_bgcolor='#131722', plot_bgcolor='#131722', margin=dict(l=10, r=55, t=10, b=10), showlegend=False,
        yaxis=dict(side="right", range=[y_min, y_max], gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)),
        xaxis=dict(gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10))
    )
    st.plotly_chart(fig, use_container_width=True, key=f"chart_render_{unique_id}")
    
    st.write(f"🟢 **BESZÁLÓ ÁR (CE 50%):** ${res['entry_price']:.5f}")
    st.write(f"🔴 **STOP LOSS ÁR (SL):** ${res['sl']:.5f}")
    st.write(f"🔵 **TAKE PROFIT ÁR (TP):** ${res['tp']:.5f}")
    st.write(f"⚙️ **JAVASOLT TŐKEÁTTÉTEL:** {res['leverage']}x (Max 10x)")
    st.write(f"📊 **R:R ARÁNY / AKTUÁLIS ÁR:** 1:{res['rr']} | ${res['current_price']:.5f}")
    st.markdown("---")

# --- FŐ VEZÉRLŐ LOGIKA ---
if not run_scanner:
    st.subheader("🎯 Kézi Elemzés és Egyedi Keresés")
    lumia_index = filtered_symbols.index("LUMIA/USDT") if "LUMIA/USDT" in filtered_symbols else 0
    selected_pair = st.selectbox("Válassz ki egy konkrét párt az azonnali elemzéshez:", filtered_symbols, index=lumia_index)
    
    manual_res = analyze_pair(selected_pair)
    if manual_res:
        render_signal_block(selected_pair, manual_res, "manual_mode")
    else:
