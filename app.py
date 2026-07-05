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

# 1. ALAPBEÁLLÍTÁSOK
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")
st.title("⚡ ALGO ICT PRO V2 - PRECISION MODE")
st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("Tőzsde:", ["bitget", "binance", "bybit", "okx"])
exch = getattr(ccxt, exchange_id)({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
exch.load_markets()

# 2. STRATÉGIA MOTOR
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        htf_data = exch.fetch_ohlcv(clean_symbol, '1h', limit=48)
        df_htf = pd.DataFrame(htf_data, columns=['t','o','h','l','c','v'])
        htf_high, htf_low = float(df_htf['h'].max()), float(df_htf['l'].min())
        
        last_price = exch.fetch_ticker(clean_symbol)['last']
        # Precision Mode logika: Ha a zónában vagyunk, 1m-re váltunk
        chosen_tf = '1m' if (last_price >= htf_high*0.998 or last_price <= htf_low*1.002) else '15m'
        
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=chosen_tf, limit=60)
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['t','o','h','l','c','v'])
        df_ltf['time'] = pd.to_datetime(df_ltf['t'], unit='ms')
        
        # Signal és RR logika
        signal = "SHORT / SELL" if last_price >= htf_high*0.998 else "LONG / BUY"
        sl = htf_high * 1.001 if signal == "SHORT / SELL" else htf_low * 0.999
        tp = last_price - (abs(last_price-sl)*3) if signal == "SHORT / SELL" else last_price + (abs(last_price-sl)*3)
        
        return {
            "df": df_ltf, "h": htf_high, "l": htf_low, "price": last_price,
            "sl": sl, "tp": tp, "signal": signal, "tf": chosen_tf, "lev": 5, "rr": 3.0
        }
    except: return None

# 3. GRAFIKON ÉS UI (Eredeti formátum)
def render_signal_block(pair, res):
    df = res["df"]
    st.subheader(f"🔥 {pair} | Idősík: {res['tf']} | Irány: {res['signal']}")
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['o'], high=df['h'], low=df['l'], close=df['c'])])
    fig.add_hline(y=res["h"], line_dash="dash", line_color="red")
    fig.add_hline(y=res["l"], line_dash="dash", line_color="green")
    fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"🟢 **BESZÁLÓ ÁR:** {res['price']:.5f} | 🔴 **SL:** {res['sl']:.5f} | 🔵 **TP:** {res['tp']:.5f}")
    st.write(f"⚙️ **JAVASOLT TŐKEÁTTÉTEL:** {res['lev']}x | 📊 **R:R ARÁNY:** 1:{res['rr']}")
    st.markdown("---")

# 4. FŐ VEZÉRLŐ
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT'] # Itt bővítheted
for pair in symbols:
    res = analyze_pair(pair)
    if res: render_signal_block(pair, res)
