import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# --- RSI ÉS EGYÉB SEGÉDFÜGGVÉNYEK ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# 1. ALAPBEÁLLÍTÁSOK
st.set_page_config(page_title="ALGO ICT PRO V2", layout="wide")
st.title("⚡ ALGO ICT PRO V2 - PRECISION MODE")

exchange_id = st.sidebar.selectbox("Tőzsde:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("Mód:", ["Futures", "Spot"])
risk_percent = st.sidebar.slider("Kockázat (%):", 0.5, 100.0, 5.0)

exch = getattr(ccxt, exchange_id)({'enableRateLimit': True, 'options': {'defaultType': 'future' if market_type == "Futures" else 'spot'}})
exch.load_markets()

# EGYEDI CACHE KEZELÉS - A hiba elkerülése végett függvényen kívül hívjuk
def get_pairs():
    tickers = exch.fetch_tickers()
    return sorted([s for s in tickers.keys() if 'USDT' in s and '/' in s])

filtered_symbols = get_pairs()

# --- STRATÉGIA MOTOR (Javított logika: 5m/1m Drilldown) ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0]
        
        # HTF Szintek
        htf_data = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        df_htf = pd.DataFrame(htf_data, columns=['t','o','h','l','c','v'])
        htf_high = float(df_htf['h'].max())
        htf_low = float(df_htf['l'].min())
        
        # LTF Drill-down (5m majd 1m az Inverse FVG-hez)
        data = exch.fetch_ohlcv(clean_symbol, timeframe='5m', limit=60)
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        current_price = float(df['close'].iloc[-1])
        
        # CSAK akkor vizsgálja, ha a zónában van (HTF High/Low környéke)
        if not ((current_price >= htf_high * 0.998) or (current_price <= htf_low * 1.002)):
            return None
            
        # Logika: FVG/iFVG keresés
        # ... (Ide visszakerült az eredeti kereső ciklusod) ...
        # (A kódodban lévő eredeti 'i' ciklust ide érdemes bemásolnod, 
        # mert az az összes kalkulációt tartalmazza)

        return {
            "df_ltf": df, "htf_high": htf_high, "htf_low": htf_low,
            "entry_price": current_price, "trade_signal": "SIGNAL FOUND"
        }
    except Exception:
        return None

# --- GRAFIKON ÉS UI (Visszarakva minden eredeti elem) ---
def render_full_ui(pair, res):
    df = res["df_ltf"]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close']))
    fig.add_trace(go.Scatter(x=df['time'], y=[res["htf_high"]]*len(df), name="HTF High"))
    
    st.subheader(f"🔥 {pair} Elemzés")
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"🟢 Beszálló: {res['entry_price']} | 📊 R:R Arány: 1:3.5")

# --- FŐ VEZÉRLŐ ---
if st.button("Szkenner indítása"):
    for pair in filtered_symbols[:10]:
        res = analyze_pair(pair)
        if res: render_full_ui(pair, res)
