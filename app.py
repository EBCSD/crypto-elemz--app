# Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

st.title("⚡ ALGO ICT PRO")
st.caption("Institutional Liquidity Sweep & Inversion FVG Terminal")

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

fvg_high = float(df_15['low'].iloc[-3])
fvg_low = float(df_15['high'].iloc[-5])
fvg_mid = (fvg_high + fvg_low) / 2

sl = htf_low - (1.5 * current_atr)
tp1 = current_price + (abs(current_price - sl) * 4.0)
tp2 = max(htf_high, current_price + (abs(current_price - sl) * 6.0))

fig = go.Figure()
fig.add_trace(go.Candlestick(x=df_15['time'], open=df_15['open'], high=df_15['high'], low=df_15['low'], close=df_15['close'], name="15M", increasing_line_color='#089981', decreasing_line_color='#f23645', increasing_fillcolor='#089981', decreasing_fillcolor='#f23645'))
fig.add_trace(go.Scatter(x=df_15['time'], y=[htf_high]*len(df_15), name="HTF High", line=dict(color='#00e676', width=1.5)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[htf_low]*len(df_15), name="HTF Low", line=dict(color='#00e676', width=1.5)))
fig.add_trace(go.Scatter(x=[df_15['time'].iloc[0], df_15['time'].iloc[-1]], y=[fvg_high, fvg_high], line=dict(color='#ffd600', width=2), showlegend=False))
fig.add_trace(go.Scatter(x=[df_15['time'].iloc[0], df_15['time'].iloc[-1]], y=[fvg_low, fvg_low], line=dict(color='#ffd600', width=2), showlegend=False))
fig.add_trace(go.Scatter(x=[df_15['time'].iloc[0], df_15['time'].iloc[-1]], y=[fvg_mid, fvg_mid], line=dict(color='#ffd600', width=1, dash='dash'), showlegend=False))
fig.add_hrect(y0=fvg_low, y1=fvg_high, fillcolor="rgba(255, 214, 0, 0.03)", line_width=0)

fig.add_trace(go.Scatter(x=df_15['time'], y=[current_price]*len(df_15), name="ENTRY", line=dict(color='#00b0ff', width=2.5)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[sl]*len(df_15), name="SL", line=dict(color='#ff1744', width=2.5)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[tp1]*len(df_15), name="TP1", line=dict(color='#00e676', width=2.5)))
fig.add_trace(go.Scatter(x=df_15['time'], y=[tp2]*len(df_15), name="TP2", line=dict(color='#00c853', width=2.5)))

buffer = (df_15['high'].max() - df_15['low'].min()) * 0.15
y_min = min(df_15['low'].min(), htf_low, sl) - buffer
y_max = max(df_15['high'].max(), htf_high, sl) + buffer
fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=440, margin=dict(l=10, r=60, t=10, b=10), yaxis=dict(range=[y_min, y_max], fixedrange=False, side="right", gridcolor="#1e293b", tickfont=dict(size=12, color="#94a3b8")), xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8")), showlegend=False)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("🎯 Automatizált Kereskedési Javaslat")

sl_dist = abs(current_price - sl) / current_price
loss_usd = total_balance * (risk_percent / 100)
pos_size = loss_usd / sl_dist if sl_dist > 0 else 0
lev = max(1, min(int(0.8 / sl_dist), 10)) if sl_dist > 0 else 1
margin = pos_size / lev

c1, c2, c3, c4 = st.columns(4)
c1.metric("BELÉPŐ", f"${current_price:,.4f}")
c2.metric("STOP LOSS", f"${sl:,.4f}")
c3.metric("TAKE PROFIT 1", f"${tp1:,.4f}")
c4.metric("TAKE PROFIT 2", f"${tp2:,.4f}")

st.markdown("##### 📐 Kockázatkezelés & Méretezés:")
cc1, cc2, cc3 = st.columns(3)
cc1.metric("Javasolt Áttétel", f"{lev}x")
cc2.metric("Pozíció Méret", f"${pos_size:,.2f}")
cc3.metric("Szükséges Margin", f"${margin:,.2f}")

st.markdown("---")
st.markdown("### 🔍 Minden Pár Élő Automata Szűrése")
st.write("Kattints az alábbi gombra az összes Bitget pár élő szűréséhez (RSI, trendek, volumen alapján):")
st.link_button("📈 Élő Bitget Piacszűrő Megnyitása", "https://tradingview.com", use_container_width=True)
