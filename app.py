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

# --- TÖKÉLETESÍTETT STRATÉGIA MOTOR (MÓDOSÍTVA 1m/5m-re) ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        
        # 1. HTF Likviditás (Marad 1h/4h)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        # 2. LTF Elemzés (1m-re állítva a gyorsabb jelzésért)
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='1m', limit=100)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        df_ltf['rsi'] = calculate_rsi(df_ltf['close'])
        
        length = len(df_ltf)
        current_price = float(df_ltf['close'].iloc[-1])
        current_rsi = float(df_ltf['rsi'].iloc[-1])

        # SZŰRŐ: Csak a HTF szint közelében keres
        is_near_htf = (current_price >= htf_high * 0.999) or (current_price <= htf_low * 1.001)
        if not is_near_htf: return None

        short_candidates = []
        long_candidates = []

        # 3. FVG/iFVG keresés (1m-en)
        for i in range(max(0, length - 60), length - 2): 
            if (df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i]) or (df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i]):
                fvg_top = max(float(df_ltf['low'].iloc[i+2]), float(df_ltf['low'].iloc[i])) if df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i] else float(df_ltf['low'].iloc[i])
                fvg_bot = min(float(df_ltf['high'].iloc[i]), float(df_ltf['high'].iloc[i+2])) if df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i] else float(df_ltf['low'].iloc[i+2])
                
                fvg_size = fvg_top - fvg_bot
                short_active = (fvg_bot - (fvg_size * 1.2)) <= current_price <= (fvg_top * 1.002)
                
                if short_active and current_rsi < 60:
                    short_candidates.append({"type": "SHORT / SELL", "fvg_high": fvg_top, "fvg_low": fvg_bot, "idx": i})

            if (df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i]) or (df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i]):
                fvg_top = min(float(df_ltf['low'].iloc[i]), float(df_ltf['low'].iloc[i+2])) if df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i] else float(df_ltf['low'].iloc[i+2])
                fvg_bot = max(float(df_ltf['high'].iloc[i+2]), float(df_ltf['high'].iloc[i])) if df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i] else float(df_ltf['high'].iloc[i])
                
                fvg_size = fvg_top - fvg_bot
                long_active = (fvg_bot * 0.998) <= current_price <= (fvg_top + (fvg_size * 1.2))
                
                if long_active and current_rsi > 40:
                    long_candidates.append({"type": "LONG / BUY", "fvg_high": fvg_top, "fvg_low": fvg_bot, "idx": i})

        best_fvg = None
        if short_candidates: best_fvg = max(short_candidates, key=lambda x: x["fvg_high"])
        elif long_candidates: best_fvg = min(long_candidates, key=lambda x: x["fvg_low"])

        if not best_fvg: return None

        fvg_high = best_fvg["fvg_high"]
        fvg_low = best_fvg["fvg_low"]
        fvg_idx = best_fvg["idx"]
        trade_signal = best_fvg["type"]

        entry_price = current_price
        if trade_signal == "SHORT / SELL":
            sl = fvg_high * 1.001
            tp = entry_price - (abs(entry_price - sl) * 3.0)
        else:
            sl = fvg_low * 0.999
            tp = entry_price + (abs(entry_price - sl) * 3.0)

        risk_dist = abs(entry_price - sl)
        reward_dist = abs(tp - entry_price)
        rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
        sl_percent = (risk_dist / entry_price) if entry_price > 0 else 0.01
        leverage_suggestion = max(1, min(int((risk_percent / 100.0) / sl_percent), 10))

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": "1m (PRECISION)", 
            "fvg_idx": fvg_idx, "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except: return None

# KÉPERNYŐ RAJZOLÓ MODUL (MARADT EREDETI)
def render_signal_block(display_name, res, unique_id):
    df_ltf = res["df_ltf"]
    length = len(df_ltf)
    st.subheader(f"🔥 {display_name} | Idősík: {res['chosen_tf']} | Irány: {res['trade_signal']}")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'], name="Ár"))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*length, name="HTF High", line=dict(color='#26a69a', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*length, name="HTF Low", line=dict(color='#ef5350', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*length, name="Belépő", line=dict(color='#29b6f6', width=2)))
    
    if res["fvg_high"] > 0:
        s_idx = int(res["fvg_idx"])
        e_idx = int(min(s_idx + 25, length - 1))
        fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[e_idx]], y=[res["fvg_high"], res["fvg_high"]], fill="toself", fillcolor="rgba(41, 182, 246, 0.2)", line=dict(color='#29b6f6')))
    
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"🟢 **BELÉPŐ:** ${res['entry_price']:.5f} | 🔴 **SL:** ${res['sl']:.5f} | 🔵 **TP:** ${res['tp']:.5f}")
    st.markdown("---")

# FŐ VEZÉRLŐ (MARADT EREDETI)
if run_scanner:
    for idx, pair in enumerate(filtered_symbols):
        res = analyze_pair(pair)
        if res: render_signal_block(pair, res, idx)
