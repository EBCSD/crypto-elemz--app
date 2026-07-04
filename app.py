# Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

# Ultramodern TradingView / LuxAlgo UI konfiguráció
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

# Prémium sötét tónusok és tiszta elrendezés injektálása
st.markdown("""
    <style>
    .main { background-color: #0c0d14 !important; color: #f1f5f9 !important; }
    h1 { font-family: 'Inter', sans-serif !important; font-size: 26px !important; font-weight: 900 !important; color: #00b0ff !important; letter-spacing: -0.5px; }
    div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 700 !important; color: #f8fafc !important; }
    div.block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }
    </style>
""", unsafe_allow_code=True)

st.title("⚡ ALGO ICT PRO")
st.caption("Advanced Institutional Liquidity Terminal | Powered by Bitget")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot", "Margin"])

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

exch = getattr(ccxt, exchange_id)({'enableRateLimit': True})
exch.load_markets()
all_symbols = list(exch.markets.keys())
filtered_symbols = [s for s in all_symbols if 'USDT' in s]

selected_pair = st.selectbox("🎯 Válassz ki egy kriptopárt az elemzéshez:", filtered_symbols)

htf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='1h', limit=48)
df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
l15 = exch.fetch_ohlcv(selected_pair, timeframe='15m', limit=40)
df_15 = pd.DataFrame(l15, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
df_15['time'] = pd.to_datetime(df_15['time'], unit='ms')

htf_high = float(df_htf['high'].max())
htf_low = float(df_htf['low'].min())
current_price = float(df_15['close'].iloc[-1])

high_low = df_15['high'] - df_15['low']
high_close = (df_15['high'] - df_15['close'].shift()).abs()
low_close = (df_15['low'] - df_15['close'].shift()).abs()
df_15['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df_15['atr'] = df_15['tr'].rolling(window=14).mean()
current_atr = df_15['atr'].iloc[-1] if pd.notna(df_15['atr'].iloc[-1]) else (current_price * 0.005)

fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
highest_candle_idx = int(df_15['high'].idxmax())

for i in range(highest_candle_idx + 2, highest_candle_idx - 3, -1):
    if i < len(df_15) and i >= 2:
        if df_15['low'].iloc[i-2] > df_15['high'].iloc[i]:
            fvg_high = float(df_15['low'].iloc[i-2])
            fvg_low = float(df_15['high'].iloc[i])
            fvg_mid = (fvg_high + fvg_low) / 2
            break
        elif df_15['high'].iloc[i-2] < df_15['low'].iloc[i]:
            fvg_high = float(df_15['low'].iloc[i])
            fvg_low = float(df_15['high'].iloc[i-2])
            fvg_mid = (fvg_high + fvg_low) / 2
            break

if fvg_high == 0:
    for i in range(len(df_15)-1, 2, -1):
        if df_15['low'].iloc[i-2] > df_15['high'].iloc[i]:
            fvg_high = float(df_15['low'].iloc[i-2])
            fvg_low = float(df_15['high'].iloc[i])
            fvg_mid = (fvg_high + fvg_low) / 2
            break
        elif df_15['high'].iloc[i-2] < df_15['low'].iloc[i]:
            fvg_high = float(df_15['low'].iloc[i])
            fvg_low = float(df_15['high'].iloc[i-2])
            fvg_mid = (fvg_high + fvg_low) / 2
            break

trade_signal = "VÁRAKOZÁS"
entry_price = current_price
sl = htf_low - (1.5 * current_atr)
tp1 = current_price
tp2 = htf_high

was_sell_swept = (df_15['low'].min() <= htf_low) or (df_15['low'].iloc[-8:].min() <= htf_low)
var_buy_swept = (df_15['high'].max() >= htf_high) or (df_15['high'].iloc[-8:].max() >= htf_high)

if was_sell_swept and fvg_high > 0:
    entry_price = fvg_high
    sl = htf_low - (1.5 * current_atr)
    tp1 = entry_price + (abs(entry_price - sl) * 4.0)
    tp2 = max(htf_high, entry_price + (abs(entry_price - sl) * 6.0))
    if current_price <= entry_price * 1.005:
        trade_signal = "LONG / BUY"
elif var_buy_swept and fvg_low > 0:
    entry_price = fvg_low
    sl = htf_high + (1.5 * current_atr)
    tp1 = entry_price - (abs(entry_price - sl) * 4.0)
    tp2 = min(htf_low, entry_price - (abs(entry_price - sl) * 6.0))
    if current_price >= entry_price * 0.995:
        trade_signal = "SHORT / SELL"

# PROFESSZIONÁLIS TRADINGVIEW STÍLUSÚ GRAFIKON FELÉPÍTÉSE
fig = go.Figure()
fig.add_trace(go.Candlestick(x=df_15['time'], open=df_15['open'], high=df_15['high'], low=df_15['low'], close=df_15['close'], name="15M", increasing_line_color='#089981', decreasing_line_color='#f23645', increasing_fillcolor='#089981', decreasing_fillcolor='#f23645'))

# Szintek berajzolása TradingView stílusú jobb oldali árcímkékkel (Price Badges)
fig.add_trace(go.Scatter(x=df_15['time'], y=[htf_high]*len(df_15), name="HTF High", line=dict(color='rgba(0, 230, 118, 0.4)', width=1, dash='dash')))
fig.add_trace(go.Scatter(x=df_15['time'], y=[htf_low]*len(df_15), name="HTF Low", line=dict(color='rgba(0, 230, 118, 0.4)', width=1, dash='dash')))

if fvg_high > 0 and fvg_low > 0:
    fig.add_trace(go.Scatter(x=[df_15['time'].iloc[0], df_15['time'].iloc[-1]], y=[fvg_high, fvg_high], line=dict(color='#ffd600', width=1.5), showlegend=False))
    fig.add_trace(go.Scatter(x=[df_15['time'].iloc[0], df_15['time'].iloc[-1]], y=[fvg_low, fvg_low], line=dict(color='#ffd600', width=1.5), showlegend=False))
    fig.add_hrect(y0=fvg_low, y1=fvg_high, fillcolor="rgba(255, 214, 0, 0.02)", line_width=0)

# Éles szintek feliratozva az ársávon
fig.add_trace(go.Scatter(x=df_15['time'], y=[entry_price]*len(df_15), name="ENTRY", line=dict(color='#00b0ff', width=2)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[sl]*len(df_15), name="SL", line=dict(color='#ff1744', width=2)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[tp1]*len(df_15), name="TP1", line=dict(color='#00e676', width=2)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[tp2]*len(df_15), name="TP2", line=dict(color='#00c853', width=2)))

buffer = (df_15['high'].max() - df_15['low'].min()) * 0.15
y_min = min(df_15['low'].min(), htf_low, sl) - buffer
y_max = max(df_15['high'].max(), htf_high, sl) + buffer

# LuxAlgo ihlette sötét, tiszta rács elrendezés ársávval a jobb oldalon
fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#0c0d14",
    plot_bgcolor="#0c0d14",
    xaxis_rangeslider_visible=False,
    height=480,
    margin=dict(l=10, r=65, t=10, b=10),
    yaxis=dict(
        range=[y_min, y_max], 
        fixedrange=False, 
        side="right", 
        gridcolor="#1e293b", 
        zeroline=False,
        tickfont=dict(size=11, color="#64748b")
    ),
    xaxis=dict(gridcolor="#1e293b", zeroline=False, tickfont=dict(color="#64748b")),
    showlegend=False
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("🎯 Automatizált Kereskedési Javaslat")

sl_dist = abs(entry_price - sl) / entry_price
loss_usd = total_balance * (risk_percent / 100)
pos_size = loss_usd / sl_dist if sl_dist > 0 else 0
lev = max(1, min(int(0.8 / sl_dist), 10)) if sl_dist > 0 else 1
margin = pos_size / lev

c1, c2, c3, c4 = st.columns(4)
c1.metric("OPTIMÁLIS BELÉPŐ", f"${entry_price:,.4f}")
c2.metric("STOP LOSS (SL)", f"${sl:,.4f}")
c3.metric("TAKE PROFIT 1", f"${tp1:,.4f}")
c4.metric("TAKE PROFIT 2", f"${tp2:,.4f}")

st.markdown("##### 📐 Kockázatkezelés & Méretezés:")
cc1, cc2, cc3 = st.columns(3)
cc1.metric("Javasolt Áttétel", f"{lev}x")
cc2.metric("Pozíció Méret", f"${pos_size:,.2f}")
cc3.metric("Szükséges Margin", f"${margin:,.2f}")

st.markdown("---")
st.markdown("### 🔍 Minden Pár Élő Automata Szűrése")
st.link_button("📈 Élő Bitget Piacszűrő Megnyitása", "https://tradingview.com", use_container_width=True)
