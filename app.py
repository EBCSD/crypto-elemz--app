# Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

st.set_page_config(page_title="ICT Bot", layout="wide", initial_sidebar_state="collapsed")
st.title("🏹 ICT Liquidity Sweep & IFVG Automata Elemző")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot", "Margin"])

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Piacszűrés")
scan_all_pairs = st.sidebar.checkbox("Minden pár automata szűrése", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

exch = getattr(ccxt, exchange_id)({'enableRateLimit': True})
with st.spinner("Piacok szinkronizálása..."):
    exch.load_markets()
all_symbols = list(exch.markets.keys())

if market_type == "Futures":
    filtered_symbols = [s for s in all_symbols if exch.markets[s].get('linear') or ('USDT' in s and ':' in s)]
elif market_type == "Margin":
    filtered_symbols = [s for s in all_symbols if exch.markets[s].get('margin')]
else:
    filtered_symbols = [s for s in all_symbols if exch.markets[s].get('spot')]

if scan_all_pairs:
    st.markdown("### ⚡ **Élő ICT Piacszűrő futása...**")
    active_trades_found = 0
    symbols_to_scan = filtered_symbols[:25]
    progress_bar = st.progress(0)
    
    for index, sym in enumerate(symbols_to_scan):
        try:
            htf = exch.fetch_ohlcv(sym, timeframe='1h', limit=48)
            ltf = exch.fetch_ohlcv(sym, timeframe='15m', limit=40)
            if len(htf) < 10 or len(ltf) < 10: continue
            df_htf = pd.DataFrame(htf, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf = pd.DataFrame(ltf, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            htf_high = df_htf['high'].max()
            htf_low = df_htf['low'].min()
            current_price = df_ltf['close'].iloc[-1]
            prev_price = df_ltf['close'].iloc[-2]
            df_ltf['ema20'] = df_ltf['close'].ewm(span=20, adjust=False).mean()
            current_ema20 = df_ltf['ema20'].iloc[-1]
            
            df_ltf['tr'] = pd.concat([df_ltf['high'] - df_ltf['low'], (df_ltf['high'] - df_ltf['close'].shift()).abs(), (df_ltf['low'] - df_ltf['close'].shift()).abs()], axis=1).max(axis=1)
            df_ltf['atr'] = df_ltf['tr'].rolling(window=14).mean()
            current_atr = df_ltf['atr'].iloc[-1] if pd.notna(df_ltf['atr'].iloc[-1]) else (current_price * 0.005)
            
            was_sell_swept = (df_ltf['low'].min() <= htf_low)
            was_buy_swept = (df_ltf['high'].max() >= htf_high)
            
            fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
            for i in range(len(df_ltf)-3, 1, -1):
                if df_ltf['high'].iloc[i-2] < df_ltf['low'].iloc[i]:
                    fvg_high, fvg_low = df_ltf['low'].iloc[i], df_ltf['high'].iloc[i-2]
                    fvg_mid = (fvg_high + fvg_low) / 2
                    break
                elif df_ltf['low'].iloc[i-2] > df_ltf['high'].iloc[i]:
                    fvg_high, fvg_low = df_ltf['low'].iloc[i-2], df_ltf['high'].iloc[i]
                    fvg_mid = (fvg_high + fvg_low) / 2
                    break
            
            trade_signal = "VÁRAKOZÁS"
            if was_sell_swept and fvg_high > 0 and current_price > fvg_high and current_price > current_ema20:
                trade_signal = "LONG / BUY"
                sl = htf_low - (1.5 * current_atr)
                tp1 = current_price + (abs(current_price - sl) * 4.0)
                tp2 = max(htf_high, current_price + (abs(current_price - sl) * 6.0))
            elif was_buy_swept and fvg_low > 0 and current_price < fvg_low and current_price < current_ema20:
                trade_signal = "SHORT / SELL"
                sl = htf_high + (1.5 * current_atr)
                tp1 = current_price - (abs(current_price - sl) * 4.0)
                tp2 = min(htf_low, current_price - (abs(current_price - sl) * 6.0))
                
            if trade_signal != "VÁRAKOZÁS":
                active_trades_found += 1
                sl_dist = abs(current_price - sl) / current_price
                loss_usd = total_balance * (risk_percent / 100)
                pos_size = loss_usd / sl_dist
                lev = max(1, min(int(0.8 / sl_dist), 10))
                margin = pos_size / lev
                
                with st.expander(f"🔥 {sym} - JELZÉS: {trade_signal}", expanded=True):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Belépő", f"${current_price:,.4f}")
                    c2.metric("Stop Loss", f"${sl:,.4f}")
                    c3.metric("Take Profit 1", f"${tp1:,.4f}")
                    c4.metric("Take Profit 2", f"${tp2:,.4f}")
                    st.info(f"📐 **Méretezés:** Áttétel: **{lev}x** | Pozíció méret: **${pos_size:,.2f}** | Margin: **${margin:,.2f}**")
        except:
            continue
        progress_bar.progress((index + 1) / len(symbols_to_scan))
    if active_trades_found == 0:
        st.info("⏳ Inaktivitás. Egyetlen páron sincs aktív setup.")
        
else:
    selected_pair = st.selectbox("2. Válassz ki egy kriptopárt az elemzéshez:", filtered_symbols if filtered_symbols else ["Nincs adat"])
    if selected_pair and selected_pair != "Nincs adat":
        st.markdown(f"### 🔍 **{selected_pair.upper()}** Részletes ICT Elemzése...")
        with st.spinner("Adatok letöltése..."):
            htf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='1h', limit=48)
            df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            ltf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='15m', limit=40)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')

        htf_high = df_htf['high'].max()
        htf_low = df_htf['low'].min()
        current_price = df_ltf['close'].iloc[-1]
        prev_price = df_ltf['close'].iloc[-2]
        
        df_ltf['ema20'] = df_ltf['close'].ewm(span=20, adjust=False).mean()
        current_ema20 = df_ltf['ema20'].iloc[-1]
        
        df_ltf['tr'] = pd.concat([df_ltf['high'] - df_ltf['low'], (df_ltf['high'] - df_ltf['close'].shift()).abs(), (df_ltf['low'] - df_ltf['close'].shift()).abs()], axis=1).max(axis=1)
        df_ltf['atr'] = df_ltf['tr'].rolling(window=14).mean()
        current_atr = df_ltf['atr'].iloc[-1] if pd.notna(df_ltf['atr'].iloc[-1]) else (current_price * 0.005)
        
        was_sell_swept = (df_ltf['low'].min() <= htf_low)
        was_buy_swept = (df_ltf['high'].max() >= htf_high)
        
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        for i in range(len(df_ltf)-3, 1, -1):
            if df_ltf['high'].iloc[i-2] < df_ltf['low'].iloc[i]:
                fvg_high = df_ltf['low'].iloc[i]
                fvg_low = df_ltf['high'].iloc[i-2]
                fvg_mid = (fvg_high + fvg_low) / 2
                break
            elif df_ltf['low'].iloc[i-2] > df_ltf['high'].iloc[i]:
                fvg_high = df_ltf['low'].iloc[i-2]
                fvg_low = df_ltf['high'].iloc[i]
                fvg_mid = (fvg_high + fvg_low) / 2
                break
                
        trade_signal = "VÁRAKOZÁS"
        if was_sell_swept and fvg_high > 0 and current_price > fvg_high and current_price > current_ema20:
            trade_signal = "LONG / BUY"
            sl = htf_low - (1.5 * current_atr)
            take_profit_1 = current_price + (abs(current_price - sl) * 4.0)
            take_profit_2 = max(htf_high, current_price + (abs(current_price - sl) * 6.0))
        elif was_buy_swept and fvg_low > 0 and current_price < fvg_low and current_price < current_ema20:
            trade_signal = "SHORT / SELL"
            sl = htf_high + (1.5 * current_atr)
            take_profit_1 = current_price - (abs(current_price - sl) * 4.0)
            take_profit_2 = min(htf_low, current_price - (abs(current_price - sl) * 6.0))

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'], name="15M", increasing_line_color='#089981', decreasing_line_color='#f23645', increasing_fillcolor='#089981', decreasing_fillcolor='#f23645'))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[htf_high]*len(df_ltf), name="HTF High", line=dict(color='#00e676', width=1.5)))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[htf_low]*len(df_ltf), name="HTF Low", line=dict(color='#00e676', width=1.5)))
        
        if fvg_high > 0 and fvg_low > 0:
            fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[0], df_ltf['time'].iloc[-1]], y=[fvg_high, fvg_high], line=dict(color='#ffd600', width=2), showlegend=False))
            fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[0], df_ltf['time'].iloc[-1]], y=[fvg_low, fvg_low], line=dict(color='#ffd600', width=2), showlegend=False))
            fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[0], df_ltf['time'].iloc[-1]], y=[fvg_mid, fvg_mid], line=dict(color='#ffd600', width=1, dash='dash'), showlegend=False))
            fig.add_hrect(y0=fvg_low, y1=fvg_high, fillcolor="rgba(255, 214, 0, 0.05)", line_width=0)
            
        if trade_signal != "VÁRAKOZÁS":
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[current_price]*len(df_ltf), name="ENTRY", line=dict(color='#00b0ff', width=2.5)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[sl]*len(df_ltf), name="SL", line=dict(color='#ff1744', width=2.5)))
