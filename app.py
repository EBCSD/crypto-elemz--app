import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# --- RSI INDIKÁTOR SZÁMÍTÁSA ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# 1. ALAPBEÁLLÍTÁSOK ÉS STRUKTÚRA
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")
st.title("⚡ ALGO ICT PRO V2 - PRECISION MODE")

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

def get_active_markets():
    try:
        tickers = exch.fetch_tickers()
        pairs = [sym for sym in tickers.keys() if 'USDT' in sym and '/' in sym]
        return sorted(list(set(pairs)))
    except:
        return []

filtered_symbols = get_active_markets()

# --- FEJLESZTETT STRATÉGIA MOTOR (5m/1m Drill-down) ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0]
        
        # 1. HTF Likviditás (Referencia)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        htf_high = float(df_1h['h'].max())
        htf_low = float(df_1h['l'].min())

        # 2. LTF Elemzés (1m a pontos belépőhöz, 5m a szűréshez)
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='1m', limit=100)
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        
        current_price = float(df_ltf['close'].iloc[-1])
        
        # SZŰRŐ: Csak akkor dolgozik, ha az ár épp a HTF zónában van
        in_zone = (current_price >= htf_high * 0.998) or (current_price <= htf_low * 1.002)
        if not in_zone: return None

        # 3. iFVG keresés (1m)
        short_candidates, long_candidates = [], []
        length = len(df_ltf)
        for i in range(max(0, length - 60), length - 2):
            # Logika: iFVG azonosítás
            if df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i]: # Bullish FVG
                long_candidates.append({"high": df_ltf['low'].iloc[i+2], "low": df_ltf['high'].iloc[i], "idx": i})
            if df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i]: # Bearish FVG
                short_candidates.append({"high": df_ltf['low'].iloc[i], "low": df_ltf['high'].iloc[i+2], "idx": i})

        best_fvg = short_candidates[-1] if short_candidates else (long_candidates[-1] if long_candidates else None)
        if not best_fvg: return None

        # 4. Kockázatkezelés
        trade_signal = "SHORT / SELL" if short_candidates else "LONG / BUY"
        sl = best_fvg["high"] * 1.001 if trade_signal == "SHORT / SELL" else best_fvg["low"] * 0.999
        tp = current_price - (abs(current_price - sl) * 3) if trade_signal == "SHORT / SELL" else current_price + (abs(current_price - sl) * 3)

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low,
            "fvg_high": best_fvg["high"], "fvg_low": best_fvg["low"],
            "entry_price": current_price, "sl": sl, "tp": tp, 
            "trade_signal": trade_signal, "chosen_tf": "1m (PRECISION)"
        }
    except: return None

# KÉPERNYŐ RAJZOLÓ MODUL (Változatlan)
def render_signal_block(display_name, res):
    df = res["df_ltf"]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close']))
    fig.add_hline(y=res["htf_high"], line_dash="dash", line_color="red")
    fig.add_hline(y=res["htf_low"], line_dash="dash", line_color="green")
    st.subheader(f"🔥 {display_name} | Irány: {res['trade_signal']}")
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"🟢 **BELÉPŐ:** {res['entry_price']} | 🔴 **SL:** {res['sl']:.5f} | 🔵 **TP:** {res['tp']:.5f}")
    st.markdown("---")

# FŐ VEZÉRLŐ (Változatlan)
if run_scanner:
    for pair in filtered_symbols[:10]: # Első 10 pár tesztnek
        res = analyze_pair(pair)
        if res: render_signal_block(pair, res)
