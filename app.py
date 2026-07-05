import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

# --- CONFIG ---
st.set_page_config(page_title="ALGO ICT PRO V2", layout="wide")
exch = ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
exch.load_markets()

# --- ICT STRATÉGIA LOGIKA ---
def calculate_ict_setup(symbol):
    try:
        # Adatok lekérése (15m alap, de zónában Precision Mode-ra váltható)
        ohlcv = exch.fetch_ohlcv(symbol, '15m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        
        # Egyszerűsített FVG logika (a gyertyák közötti hézag)
        # Itt kellene implementálni a pontos ICT FVG detektálást
        fvg_top = df['l'].iloc[-2]
        fvg_bottom = df['h'].iloc[-4]
        
        curr = exch.fetch_ticker(symbol)['last']
        
        # SL/TP szintek kalkulációja
        sl = fvg_bottom if curr > fvg_top else fvg_top
        tp = curr + (abs(curr - sl) * 3) if curr > fvg_top else curr - (abs(curr - sl) * 3)
        
        return {"df": df, "fvg_top": fvg_top, "fvg_bottom": fvg_bottom, "sl": sl, "tp": tp, "curr": curr}
    except: return None

# --- VIZUÁLIS MEGJELENÍTÉS (Chart + Szintek) ---
def render_full_chart(symbol, res):
    df = res["df"]
    st.subheader(f"⚡ ICT SETUP: {symbol}")
    
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['o'], high=df['h'], low=df['l'], close=df['c'])])
    
    # FVG KÉK DOBOZ
    fig.add_shape(type="rect", x0=df['time'].iloc[-5], y0=res["fvg_bottom"], x1=df['time'].iloc[-1], y1=res["fvg_top"],
                  fillcolor="blue", opacity=0.3, line_width=0)
    
    # SL és TP szintek vonalai
    fig.add_hline(y=res["sl"], line_color="red", line_dash="dot", annotation_text="SL")
    fig.add_hline(y=res["tp"], line_color="green", line_dash="dot", annotation_text="TP")
    
    fig.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)
    
    # Adatok kiírása
    col1, col2, col3 = st.columns(3)
    col1.metric("BELÉPŐ", f"${res['curr']:.5f}")
    col2.metric("STOP LOSS", f"${res['sl']:.5f}")
    col3.metric("TAKE PROFIT", f"${res['tp']:.5f}")
    st.markdown("---")

# --- MAIN LOOP ---
st.title("ALGO ICT PRO - Automata Szkenner")
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'LUMIA/USDT:USDT']

for s in symbols:
    res = calculate_ict_setup(s)
    if res: render_full_chart(s, res)
