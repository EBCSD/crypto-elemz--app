import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# --- RSI INDIKÁTOR ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# --- ALAPBEÁLLÍTÁSOK ---
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")
st.title("⚡ ALGO ICT PRO V2 - PRECISION")

# Vezérlőpult
exchange_id = st.sidebar.selectbox("Tőzsde:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("Mód:", ["Futures", "Spot"])
risk_percent = st.sidebar.slider("Kockázat (%):", 0.5, 100.0, 5.0)
run_scanner = st.sidebar.checkbox("Automata Piacszkenner", value=True)

# API
exch = getattr(ccxt, exchange_id)({'enableRateLimit': True, 'options': {'defaultType': 'future' if market_type == "Futures" else 'spot'}})
exch.load_markets()

@st.cache_data(ttl=60)
def get_active_markets():
    try:
        markets = exch.fetch_tickers()
        return sorted([s for s in markets.keys() if 'USDT' in s and '/' in s])
    except: return []

filtered_symbols = get_active_markets()

# --- STRATÉGIA MOTOR (5m/1m LOGIKA) ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0]
        
        # 1. HTF Likviditás (1h/4h)
        htf_1h = pd.DataFrame(exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48), columns=['t','o','h','l','c','v'])
        htf_high = float(htf_1h['h'].max())
        htf_low = float(htf_1h['l'].min())

        # 2. LTF Elemzés (1m a pontos belépőhöz)
        ohlcv_1m = exch.fetch_ohlcv(clean_symbol, timeframe='1m', limit=60)
        df = pd.DataFrame(ohlcv_1m, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        current_price = float(df['close'].iloc[-1])
        
        # HTF Zóna ellenőrzés (itt a lényeg: csak a zónában keresünk!)
        in_zone = (current_price >= htf_high * 0.998) or (current_price <= htf_low * 1.002)
        if not in_zone: return None

        # FVG keresés a legfrissebb adatokban (utolsó 20 gyertya)
        short_candidates = []
        long_candidates = []
        for i in range(len(df) - 20, len(df) - 2):
            # Logika: Bearish/Bullish FVG detektálás
            if df['low'].iloc[i+2] > df['high'].iloc[i]: # Bullish FVG
                long_candidates.append({"high": df['low'].iloc[i+2], "low": df['high'].iloc[i], "idx": i})
            if df['high'].iloc[i+2] < df['low'].iloc[i]: # Bearish FVG
                short_candidates.append({"high": df['low'].iloc[i], "low": df['high'].iloc[i+2], "idx": i})

        if not short_candidates and not long_candidates: return None

        # Paraméterek beállítása
        best_fvg = short_candidates[-1] if short_candidates else long_candidates[-1]
        
        return {
            "df_ltf": df, "htf_high": htf_high, "htf_low": htf_low,
            "fvg_high": best_fvg["high"], "fvg_low": best_fvg["low"],
            "entry_price": current_price, "trade_signal": "SHORT" if short_candidates else "LONG"
        }
    except: return None

# --- RAJZOLÓ ---
def render_signal_block(display_name, res):
    df = res["df_ltf"]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close']))
    fig.add_hline(y=res["htf_high"], line_color="red")
    fig.add_hline(y=res["htf_low"], line_color="green")
    
    st.subheader(f"🔥 {display_name} | {res['trade_signal']}")
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"Belépő: {res['entry_price']} | Zóna: {res['fvg_low']} - {res['fvg_high']}")

# --- FŐ VEZÉRLŐ ---
if run_scanner:
    for pair in filtered_symbols[:10]: # Első 10 pár tesztnek
        res = analyze_pair(pair)
        if res: render_signal_block(pair, res)
