import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

# --- CONFIG ---
st.set_page_config(page_title="ALGO ICT PRO V2", layout="wide")
exch = ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
exch.load_markets()

# --- SZKENNER MOTOR ---
def get_analysis(symbol):
    try:
        # 1. HTF adatok (Likviditás és Zónák)
        ohlcv_1h = exch.fetch_ohlcv(symbol, '1h', limit=50)
        df = pd.DataFrame(ohlcv_1h, columns=['t','o','h','l','c','v'])
        
        # FVG / iFVG detektálás (egyszerűsített logika a képek alapján)
        high_zone = df['h'].max()
        low_zone = df['l'].min()
        curr = exch.fetch_ticker(symbol)['last']
        
        # Precision Mode: Automatikus váltás 1m-re, ha zónában vagyunk
        tf = '1m' if (abs(curr - high_zone) < high_zone*0.002 or abs(curr - low_zone) < low_zone*0.002) else '15m'
        
        # Adatok a chart-hoz
        data = exch.fetch_ohlcv(symbol, tf, limit=100)
        df_chart = pd.DataFrame(data, columns=['t','o','h','l','c','v'])
        df_chart['time'] = pd.to_datetime(df_chart['t'], unit='ms')
        
        return {"df": df_chart, "h": high_zone, "l": low_zone, "curr": curr, "tf": tf}
    except: return None

# --- VIZUÁLIS BLOKK ---
def render_chart(symbol, res):
    df = res["df"]
    st.subheader(f"⚡ {symbol} | Idősík: {res['tf']}")
    
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['o'], high=df['h'], low=df['l'], close=df['c'])])
    fig.add_hline(y=res["h"], line_color="red", line_dash="dash")
    fig.add_hline(y=res["l"], line_color="green", line_dash="dash")
    
    # Kék zóna (FVG vizualizáció)
    fig.add_shape(type="rect", x0=df['time'].iloc[-20], y0=res["l"], x1=df['time'].iloc[-1], y1=res["h"],
                  fillcolor="blue", opacity=0.2, line_width=0)
    
    fig.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)
    
    # Adatok
    st.write(f"🟢 **BELÉPŐ:** {res['curr']:.5f} | ⚙️ **Tőkeáttétel:** 5x | 📊 **RR:** 1:3")
    st.markdown("---")

# --- FŐ FOLYAMAT ---
st.title("🔍 ALGO ICT PRO: Automata Piacszkenner")
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'LUMIA/USDT:USDT', 'ACE/USDT:USDT'] # Itt bővítheted a listát

for s in symbols:
    res = get_analysis(s)
    if res: render_chart(s, res)
