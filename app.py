# Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

# Ultramodern, letisztult UI konfiguráció
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

# Modern dizájn injektálása: sötét tónusok, minimalizmus, neon kék részletek
st.markdown("""
    <style>
    .main { background-color: #080b10; color: #e2e8f0; }
    h1 { font-family: 'Inter', sans-serif; font-size: 26px !important; font-weight: 800 !important; color: #00b0ff !important; letter-spacing: -0.5px; margin-bottom: 5px !important; }
    div[data-testid="stExpander"] { background-color: #111622 !important; border: 1px solid #1e293b !important; border-radius: 8px !important; }
    .stProgress > div > div > div > div { background-image: linear-gradient(to right, #00b0ff, #00e676) !important; }
    div[data-testid="stNotification"] { background-color: #111622 !important; border: 1px solid #1e293b !important; border-radius: 8px !important; color: #94a3b8 !important; }
    div.block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }
    </style>
""", unsafe_allow_code=True)

# Új, letisztult, professzionális név és alcím
st.title("⚡ ALGO ICT PRO")
st.caption("Institutional Liquidity Sweep & Inversion FVG Terminal")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot", "Margin"])

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Piacszűrés")
scan_all_pairs = st.sidebar.checkbox("Minden pár automata szűrése", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

@st.cache_resource
def init_exchange(exch_id):
    return getattr(ccxt, exch_id)({'enableRateLimit': True})

def calc_atr(df):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    val = df['atr'].iloc[-1]
    return val if pd.notna(val) else (df['close'].iloc[-1] * 0.005)

def find_latest_fvg(df):
    f_high, f_low, f_mid = 0.0, 0.0, 0.0
    for i in range(len(df)-1, 2, -1):
        if df['high'].iloc[i-2] < df['low'].iloc[i]:
            f_high, f_low = df['low'].iloc[i], df['high'].iloc[i-2]
            f_mid = (f_high + f_low) / 2
            return f_high, f_low, f_mid
        elif df['low'].iloc[i-2] > df['high'].iloc[i]:
            f_high, f_low = df['low'].iloc[i-2], df['high'].iloc[i]
            f_mid = (f_high + f_low) / 2
            return f_high, f_low, f_mid
    return 0.0, 0.0, 0.0

def analyze_strategy(df_htf, df_15m, df_5m):
    htf_high = df_htf['high'].max()
    htf_low = df_htf['low'].min()
    
    df_ltf = df_15m
    timeframe_used = "15M"
    fvg_high, fvg_low, fvg_mid = find_latest_fvg(df_15m)
    
    if fvg_high == 0:
        df_ltf = df_5m
        timeframe_used = "5M"
        fvg_high, fvg_low, fvg_mid = find_latest_fvg(df_5m)
        
    current_price = df_ltf['close'].iloc[-1]
    df_ltf['ema20'] = df_ltf['close'].ewm(span=20, adjust=False).mean()
    current_ema20 = df_ltf['ema20'].iloc[-1]
    current_atr = calc_atr(df_ltf)
    
    was_sell_swept = (df_ltf['low'].min() <= htf_low) or (df_ltf['low'].iloc[-8:].min() <= htf_low)
    was_buy_swept = (df_ltf['high'].max() >= htf_high) or (df_ltf['high'].iloc[-8:].max() >= htf_high)
    
    if was_sell_swept and fvg_high > 0 and current_price > fvg_high and current_price > current_ema20:
        sl = htf_low - (1.5 * current_atr)
        tp1 = current_price + (abs(current_price - sl) * 4.0)
        tp2 = max(htf_high, current_price + (abs(current_price - sl) * 6.0))
        return "LONG / BUY", current_price, sl, tp1, tp2, fvg_high, fvg_low, fvg_mid, htf_high, htf_low, timeframe_used, df_ltf
        
    elif was_buy_swept and fvg_low > 0 and current_price < fvg_low and current_price < current_ema20:
        sl = htf_high + (1.5 * current_atr)
        tp1 = current_price - (abs(current_price - sl) * 4.0)
        tp2 = min(htf_low, current_price - (abs(current_price - sl) * 6.0))
        return "SHORT / SELL", current_price, sl, tp1, tp2, fvg_high, fvg_low, fvg_mid, htf_high, htf_low, timeframe_used, df_ltf
        
    return "VÁRAKOZÁS", current_price, 0, 0, 0, fvg_high, fvg_low, fvg_mid, htf_high, htf_low, timeframe_used, df_ltf

def draw_chart(df_plot, htf_high, htf_low, fvg_high, fvg_low, fvg_mid, signal, current_price, sl, tp1, tp2, tf_title):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_plot['time'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name=tf_title, increasing_line_color='#089981', decreasing_line_color='#f23645', increasing_fillcolor='#089981', decreasing_fillcolor='#f23645'))
    fig.add_trace(go.Scatter(x=df_plot['time'], y=[htf_high]*len(df_plot), name="HTF High", line=dict(color='#00e676', width=1.5)))
    fig.add_trace(go.Scatter(x=df_plot['time'], y=[htf_low]*len(df_plot), name="HTF Low", line=dict(color='#00e676', width=1.5)))
    
    if fvg_high > 0 and fvg_low > 0:
        fig.add_trace(go.Scatter(x=[df_plot['time'].iloc, df_plot['time'].iloc[-1]], y=[fvg_high, fvg_high], line=dict(color='#ffd600', width=2), showlegend=False))
        fig.add_trace(go.Scatter(x=[df_plot['time'].iloc, df_plot['time'].iloc[-1]], y=[fvg_low, fvg_low], line=dict(color='#ffd600', width=2), showlegend=False))
        fig.add_trace(go.Scatter(x=[df_plot['time'].iloc, df_plot['time'].iloc[-1]], y=[fvg_mid, fvg_mid], line=dict(color='#ffd600', width=1, dash='dash'), showlegend=False))
        fig.add_hrect(y0=fvg_low, y1=fvg_high, fillcolor="rgba(255, 214, 0, 0.03)", line_width=0)
        
    if signal != "VÁRAKOZÁS":
        fig.add_trace(go.Scatter(x=df_plot['time'], y=[fvg_low if signal == "SHORT / SELL" else fvg_high]*len(df_plot), name="ENTRY", line=dict(color='#00b0ff', width=2.5)))
        fig.add_trace(go.Scatter(x=df_plot['time'], y=[sl]*len(df_plot), name="SL", line=dict(color='#ff1744', width=2.5)))
        fig.add_trace(go.Scatter(x=df_plot['time'], y=[tp1]*len(df_plot), name="TP1", line=dict(color='#00e676', width=2.5)))
        fig.add_trace(go.Scatter(x=df_plot['time'], y=[tp2]*len(df_plot), name="TP2", line=dict(color='#00c853', width=2.5)))
        
    buffer = (df_plot['high'].max() - df_plot['low'].min()) * 0.15
    y_min = min(df_plot['low'].min(), sl if signal != "VÁRAKOZÁS" else htf_low) - buffer
    y_max = max(df_plot['high'].max(), sl if signal != "VÁRAKOZÁS" else htf_high) + buffer
    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=440, margin=dict(l=10, r=60, t=10, b=10), yaxis=dict(range=[y_min, y_max], fixedrange=False, side="right", gridcolor="#1e293b", tickfont=dict(size=12, color="#94a3b8")), xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8")), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

def show_metrics(entry, sl, tp1, tp2, bal, risk):
    sl_dist = abs(entry - sl) / entry
    loss_usd = bal * (risk / 100)
    pos_size = loss_usd / sl_dist if sl_dist > 0 else 0
    lev = max(1, min(int(0.8 / sl_dist), 10)) if sl_dist > 0 else 1
    margin = pos_size / lev
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BELÉPŐ", f"${entry:,.6f}")
    c2.metric("STOP LOSS", f"${sl:,.6f}")
    c3.metric("TAKE PROFIT 1", f"${tp1:,.4f}")
    c4.metric("TAKE PROFIT 2", f"${tp2:,.4f}")
    st.markdown("##### 📐 Kockázatkezelés & Méretezés:")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Javasolt Áttétel", f"{lev}x")
    cc2.metric("Pozíció Méret", f"${pos_size:,.2f}")
    cc3.metric("Szükséges Margin", f"${margin:,.2f}")

exch = init_exchange(exchange_id)
exch.load_markets()
all_symbols = list(exch.markets.keys())

if market_type == "Futures":
    filtered_symbols = [s for s in all_symbols if exch.markets[s].get('linear') or ('USDT' in s and ':' in s)]
elif market_type == "Margin":
    filtered_symbols = [s for s in all_symbols if exch.markets[s].get('margin')]
else:
    filtered_symbols = [s for s in all_symbols if exch.markets[s].get('spot')]

if scan_all_pairs:
    st.markdown("### ⚡ **Élő Piacszűrés...**")
    active_trades_found = 0
    symbols_to_scan = filtered_symbols[:50]
    progress_bar = st.progress(0)
    
    for index, sym in enumerate(symbols_to_scan):
        try:
            htf = exch.fetch_ohlcv(sym, timeframe='1h', limit=48)
            l15m = exch.fetch_ohlcv(sym, timeframe='15m', limit=40)
            l5m = exch.fetch_ohlcv(sym, timeframe='5m', limit=40)
            if len(htf) < 10 or len(l15m) < 10: continue
            
            df_h = pd.DataFrame(htf, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_15 = pd.DataFrame(l15m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_5 = pd.DataFrame(l5m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_15['time'] = pd.to_datetime(df_15['time'], unit='ms')
            df_5['time'] = pd.to_datetime(df_5['time'], unit='ms')
            
            signal, entry, sl, tp1, tp2, f_h, f_l, f_m, h_h, h_l, tf_used, df_active = analyze_strategy(df_h, df_15, df_5)
            
            if signal != "VÁRAKOZÁS":
                active_trades_found += 1
                with st.expander(f"🔥 {sym} - {signal} ({tf_used})", expanded=True):
                    draw_chart(df_active, h_h, h_l, f_h, f_l, f_m, signal, entry, sl, tp1, tp2, tf_used)
