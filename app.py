
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# 1. OLDALBEÁLLÍTÁSOK ÉS TRADINGVIEW DESIGN
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; background-color: #131722; }
    h1, h2, h3, p, span, caption { color: #d1d4dc !important; }
    div[data-testid="stVerticalBlock"] { background-color: #131722; }
    .signal-header { 
        background-color: #1c2030; 
        padding: 12px; 
        border-radius: 6px; 
        border-left: 5px solid #ffd600;
        margin-top: 25px;
        margin-bottom: 15px; 
    }
    .data-row {
        background-color: #1c2030;
        padding: 10px;
        border-radius: 6px;
        border: 1px solid #2a2e39;
        margin-top: 5px;
        margin-bottom: 5px;
    }
    </style>
""", unsafe_allow_html=True)

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
run_scanner = st.sidebar.checkbox("Automata Piacszkenner Indítása", value=True)

# API Inicializálás
exch = getattr(ccxt, exchange_id)({
    'enableRateLimit': True,
    'options': {'defaultType': 'future' if market_type == "Futures" else 'spot'}
})
exch.load_markets()

@st.cache_data(ttl=300)
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

# ATOMBIZTOS INVERZ FVG STRATÉGIAI MOTOR
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol

        # HTF szintek lekérése (1h és 4h kombinált likviditás)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h:
            return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        # LTF idősík betöltése (Fixen a 15m)
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='15m', limit=45)
        if not ltf_ohlcv:
            return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        length = len(df_ltf)

        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_ifvg = False
        fvg_idx = 0
        fvg_type = "NONE"

        # Lineáris iFVG szkennelés elcsúszás ellen
        for i in range(2, length - 4):
            if df_ltf['high'].iloc[i] < df_ltf['low'].iloc[i+2]:
                fvg_high = float(df_ltf['low'].iloc[i+2])
                fvg_low = float(df_ltf['high'].iloc[i])
                fvg_idx = i
                fvg_type = "BEARISH_INVERSE"
                found_ifvg = True
                break
            elif df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]:
                fvg_high = float(df_ltf['low'].iloc[i])
                fvg_low = float(df_ltf['high'].iloc[i+2])
                fvg_idx = i
                fvg_type = "BULLISH_INVERSE"
                found_ifvg = True
                break

        if not found_ifvg:
            return None

        current_price = float(df_ltf['close'].iloc[-1])
        fvg_mid = (fvg_high + fvg_low) / 2.0

        trade_signal = "DOBOZON BELÜL (Retest)"
        entry_price = fvg_mid
        sl = htf_high if fvg_type == "BEARISH_INVERSE" else htf_low
        tp = entry_price - (abs(entry_price - sl) * 3.5) if fvg_type == "BEARISH_INVERSE" else entry_price + (abs(entry_price - sl) * 3.5)

        if fvg_type == "BEARISH_INVERSE" and current_price < fvg_mid:
            trade_signal = "SHORT / SELL"
        elif fvg_type == "BULLISH_INVERSE" and current_price > fvg_mid:
            trade_signal = "LONG / BUY"

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": "15m", "fvg_idx": fvg_idx
        }
    except:
        return None

# --- EGYEDI PÁR KERESŐ ---
st.subheader("🎯 Egyedi Kriptopár Keresése és Azonnali Elemzése")
default_index = filtered_symbols.index("LUMIA/USDT") if "LUMIA/USDT" in filtered_symbols else 0
selected_pair = st.selectbox("Válassz ki egy párt a listából:", filtered_symbols, index=default_index)

res = analyze_pair(selected_pair)

if res:
    df_ltf = res["df_ltf"]
    length = len(df_ltf)
    
    st.markdown(f"""
        <div class="signal-header">
            <h3 style='margin:0; font-size:16px;'>🔥 {selected_pair} &nbsp;|&nbsp; Idősík: {res['chosen_tf']} &nbsp;|&nbsp; Irány: {res['trade_signal']}</h3>
        </div>
    """, unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
        increasing_line_color='#089981', decreasing_line_color='#f23645',
        increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Ár"
    ))
    
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*length, name="HTF High Liq", line=dict(color='#26a69a', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*length, name="HTF Low Liq", line=dict(color='#ef5350', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*length, name="Belépő", line=dict(color='#29b6f6', width=2)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*length, name="SL", line=dict(color='#ff1744', width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp"]]*length, name="TP", line=dict(color='#00e676', width=1.5)))

    if res["fvg_high"] > 0 and res["fvg_idx"] is not None:
        s_idx = int(res["fvg_idx"])
        e_idx = int(min(s_idx + 18, length - 1))
        t_start = df_ltf['time'].iloc[s_idx]
        t_end = df_ltf['time'].iloc[e_idx]
        
        bx = [t_start, t_end, t_end, t_start, t_start]
        by = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
        
        fig.add_trace(go.Scatter(x=bx, y=by, fill="toself", fillcolor="rgba(255, 214, 0, 0.04)", line=dict(color='#ffd600', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[t_start, t_end], y=[res["fvg_mid"], res["fvg_mid"]], line=dict(color='#e040fb', width=2, dash='dash'), showlegend=False))

    y_pad = (max(df_ltf['high'].max(), res["htf_high"]) - min(df_ltf['low'].min(), res["htf_low"])) * 0.1
    fig.update_layout(
        template="plotly_dark", xaxis_rangeslider_visible=False, height=420,
        paper_bgcolor='#131722', plot_bgcolor='#131722', margin=dict(l=10, r=55, t=10, b=10), showlegend=False,
        yaxis=dict(side="right", range=[min(df_ltf['low'].min(), res["htf_low"]) - y_pad, max(df_ltf['high'].max(), res["htf_high"]) + y_pad], gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)),
        xaxis=dict(gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10))
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown(f"""
        <div class="data-row">
            <p style='margin:3px; font-size:15px; color:#29b6f6;'><b>🟢 BESZÁLÓ (CE 50%):</b> ${res['entry_price']:.5f}</p>
            <p style='margin:3px; font-size:15px; color:#ff1744;'><b>🔴 STOP LOSS (SL):</b> ${res['sl']:.5f}</p>
            <p style='margin:3px; font-size:15px; color:#00e676;'><b>🔵 TAKE PROFIT (TP):</b> ${res['tp']:.5f}</p>
            <p style='margin:3px; font-size:14px; color:#848e9c;'><b>📊 AKTUÁLIS ÁR:</b> ${res['current_price']:.5f}</p>
        </div>
    """, unsafe_allow_html=True)
else:
    st.info("Ezen a páron jelenleg nincs aktív, szabályos iFVG szerkezet.")

# --- AUTOMATA PIACSZKENNER MODUL ---
st.markdown("---")
st.subheader("🕵️‍♂️ Háttér Automata Szkenner (A Teljes Piacról)")

if run_scanner:
    scan_placeholder = st.empty()
    active_signals = []
    
    for pair in filtered_symbols[:40]:
        scan_placeholder.text(f"Háttérszűrés folyamatban... Ellenőrzés: {pair}")
        s_res = analyze_pair(pair)
        if s_res and "VÁRAKOZÁS" not in s_res["trade_signal"]:
            active_signals.append(pair)
            
    scan_placeholder.empty()
    
    if active_signals:
        st.success(f"Aktív szignált találtam ezeken a párokon: {', '.join(active_signals)}")
    else:
        st.info("Jelenleg nincs egyidejű aktív visszateszt szignál a vizsgált tartományban.")

