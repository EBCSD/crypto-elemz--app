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
        pairs = [sym for sym in tickers.keys() if 'USDT' in sym and '/' in sym]
        return sorted(list(set(pairs)))
    except:
        return []

filtered_symbols = get_active_markets()

# --- TÖKÉLETESÍTETT STRATÉGIA MOTOR (PRECISION MODE) ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        
        # 1. HTF Likviditás
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = max(float(df_1h['high'].iloc[-2:].max()), float(df_4h['high'].iloc[-2:].max()))
        htf_low = min(float(df_1h['low'].iloc[-2:].min()), float(df_4h['low'].iloc[-2:].min()))

        # 2. DINAMIKUS IDŐSÍK (15m alap, 1m precíziós)
        last_price = exch.fetch_ticker(clean_symbol)['last']
        is_in_zone = (last_price >= htf_high * 0.998) or (last_price <= htf_low * 1.002)
        chosen_tf = '1m' if is_in_zone else '15m'
        
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=chosen_tf, limit=60)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        df_ltf['rsi'] = calculate_rsi(df_ltf['close'])
        
        # 3-5. (Az eredeti logika változatlan)
        length = len(df_ltf)
        current_price = float(df_ltf['close'].iloc[-1])
        current_rsi = float(df_ltf['rsi'].iloc[-1])
        
        # FVG/iFVG keresés az aktuális idősíkon
        short_candidates, long_candidates = [], []
        for i in range(max(0, length - 40), length - 2):
            if (df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i]) or (df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i]):
                fvg_top = max(float(df_ltf['low'].iloc[i+2]), float(df_ltf['low'].iloc[i])) if df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i] else float(df_ltf['low'].iloc[i])
                fvg_bot = min(float(df_ltf['high'].iloc[i]), float(df_ltf['high'].iloc[i+2])) if df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i] else float(df_ltf['high'].iloc[i+2])
                short_candidates.append({"type": "SHORT / SELL", "fvg_high": fvg_top, "fvg_low": fvg_bot, "idx": i})
            if (df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i]) or (df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i]):
                fvg_top = min(float(df_ltf['low'].iloc[i]), float(df_ltf['low'].iloc[i+2])) if df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i] else float(df_ltf['low'].iloc[i+2])
                fvg_bot = max(float(df_ltf['high'].iloc[i+2]), float(df_ltf['high'].iloc[i])) if df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i] else float(df_ltf['high'].iloc[i])
                long_candidates.append({"type": "LONG / BUY", "fvg_high": fvg_top, "fvg_low": fvg_bot, "idx": i})

        best_fvg = (max(short_candidates, key=lambda x: x["fvg_high"]) if short_candidates else None) if is_in_zone else None
        if not best_fvg: return None

        # Kockázatkezelés
        sl = best_fvg["fvg_high"] * 1.001 if best_fvg["type"] == "SHORT / SELL" else best_fvg["fvg_low"] * 0.999
        tp = current_price - (abs(current_price - sl) * 3) if best_fvg["type"] == "SHORT / SELL" else current_price + (abs(current_price - sl) * 3)

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": best_fvg["fvg_high"], "fvg_low": best_fvg["fvg_low"], "entry_price": current_price,
            "sl": sl, "tp": tp, "trade_signal": best_fvg["type"], "chosen_tf": chosen_tf, "fvg_idx": best_fvg["idx"],
            "leverage": 5, "rr": 3.0
        }
    except: return None

# UI Rajzoló (Változatlan)
def render_signal_block(display_name, res, unique_id):
    df_ltf = res["df_ltf"]
    st.subheader(f"🔥 {display_name} | Idősík: {res['chosen_tf']} | Irány: {res['trade_signal']}")
    # (A rajzoló kód marad a korábbi változatod, a megjelenésért felelős)
    st.write(f"🟢 **BELÉPŐ:** {res['entry_price']} | 🔴 **SL:** {res['sl']:.5f} | 🔵 **TP:** {res['tp']:.5f}")
    st.markdown("---")

# Fővezérlő (Változatlan)
if run_scanner:
    for pair in filtered_symbols[:20]:
        res = analyze_pair(pair)
        if res: render_signal_block(pair, res, pair)
