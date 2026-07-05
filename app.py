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

# 1. ALAPBEÁLLÍTÁSOK (Minden marad az eredeti)
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")
st.title("⚡ ALGO ICT PRO V2")
st.caption("Advanced Institutional Liquidity Terminal | Powered by Bitget")
exch = ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
exch.load_markets()

# --- A KÉRT PRECÍZIÓS LOGIKÁVAL BŐVÍTETT ELEMZŐ FÜGGVÉNY ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0]
        # HTF adatok (hogy lássuk, zónában vagyunk-e)
        htf_ohlcv = exch.fetch_ohlcv(clean_symbol, '1h', limit=48)
        df_htf = pd.DataFrame(htf_ohlcv, columns=['t','o','h','l','c','v'])
        htf_h, htf_l = float(df_htf['h'].max()), float(df_htf['l'].min())
        
        # PRECÍZIÓS VÁLTÁS: Ha az ár közel van a HTF szinthez, 1m-re váltunk
        curr = exch.fetch_ticker(clean_symbol)['last']
        tf = '1m' if (curr >= htf_h*0.998 or curr <= htf_l*1.002) else '15m'
        
        # Adatok lekérése a választott idősíkon
        data = exch.fetch_ohlcv(clean_symbol, tf, limit=60)
        df = pd.DataFrame(data, columns=['t','o','h','l','c','v'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        
        # Stratégia (Visszatért az eredeti számítási logika)
        signal = "SHORT / SELL" if curr >= htf_h*0.998 else "LONG / BUY"
        sl = htf_h * 1.001 if signal == "SHORT / SELL" else htf_l * 0.999
        tp = curr - (abs(curr-sl)*3) if signal == "SHORT / SELL" else curr + (abs(curr-sl)*3)
        
        return {
            "df": df, "htf_h": htf_h, "htf_l": htf_l, "curr": curr,
            "sl": sl, "tp": tp, "signal": signal, "tf": tf, "lev": 5, "rr": 3.0
        }
    except: return None

# 2. VIZUÁLIS MEGJELENÍTŐ (Visszaállítva a chart, kék doboz, szintek)
def render_signal_block(pair, res):
    df = res["df"]
    st.subheader(f"🔥 {pair} | Idősík: {res['tf']} | Irány: {res['signal']}")
    
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['o'], high=df['h'], low=df['l'], close=df['c'])])
    fig.add_hline(y=res["htf_h"], line_color="red")
    fig.add_hline(y=res["htf_l"], line_color="green")
    fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
    
    # Adatok kiírása (Tőkeáttétel + RR visszaadva)
    st.write(f"🟢 **BELÉPŐ:** {res['curr']:.5f} | 🔴 **SL:** {res['sl']:.5f} | 🔵 **TP:** {res['tp']:.5f}")
    st.write(f"⚙️ **JAVASOLT TŐKEÁTTÉTEL:** {res['lev']}x | 📊 **R:R ARÁNY / AKTUÁLIS ÁR:** 1:{res['rr']} | ${res['curr']:.5f}")
    st.markdown("---")

# 3. FŐ VEZÉRLŐ (Automatikusan futtatja a keresést)
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'LUMIA/USDT:USDT']
for pair in symbols:
    res = analyze_pair(pair)
    if res: render_signal_block(pair, res)
