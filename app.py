# Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

st.set_page_config(page_title="ICT Auto Trader Bot", layout="wide", initial_sidebar_state="collapsed")
st.title("🏹 ICT Liquidity Sweep & IFVG Automata Elemző")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot", "Margin"])

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Megengedett kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

@st.cache_resource
def init_exchange(exch_id):
    exch_class = getattr(ccxt, exch_id)
    return exch_class({'enableRateLimit': True})

try:
    exch = init_exchange(exchange_id)
    with st.spinner("Piacok betöltése a tőzsdéről..."):
        exch.load_markets()
        
    all_symbols = list(exch.markets.keys())
    
    if market_type == "Futures":
        filtered_symbols = [s for s in all_symbols if exch.markets[s].get('linear') or ('USDT' in s and ':' in s)]
    elif market_type == "Margin":
        filtered_symbols = [s for s in all_symbols if exch.markets[s].get('margin')]
    else:
        filtered_symbols = [s for s in all_symbols if exch.markets[s].get('spot')]
        
    selected_pair = st.selectbox("2. Válassz ki egy kriptopárt az elemzéshez:", filtered_symbols if filtered_symbols else ["Nincs adat"])

    if selected_pair and selected_pair != "Nincs adat":
        st.markdown(f"### 🔍 **{selected_pair.upper()}** Részletes ICT Elemzése...")
        
        with st.spinner("Gyertyaadatok letöltése és elemzése..."):
            htf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='1h', limit=48)
            df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            ltf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='15m', limit=40)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')

        # 1H/4H szintek meghatározása
        htf_high = df_htf['high'].max()
        htf_low = df_htf['low'].min()
        
        current_price = df_ltf['close'].iloc[-1]
        prev_price = df_ltf['close'].iloc[-2]
        df_ltf['ema20'] = df_ltf['close'].ewm(span=20, adjust=False).mean()
        current_ema20 = df_ltf['ema20'].iloc[-1]

        # ATR (Average True Range) alapú intelligens játszótér számítás a Stop Loss-hoz
        df_ltf['tr'] = pd.concat([
            df_ltf['high'] - df_ltf['low'],
            (df_ltf['high'] - df_ltf['close'].shift()).abs(),
            (df_ltf['low'] - df_ltf['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df_ltf['atr'] = df_ltf['tr'].rolling(window=14).mean()
        current_atr = df_ltf['atr'].iloc[-1] if pd.notna(df_ltf['atr'].iloc[-1]) else (current_price * 0.005)

        trade_signal = "VÁRAKOZÁS"
        reason = "Az árfolyam jelenleg a likviditási szintek között mozog, nincs érvényes sweep."
        
        was_sell_liquidity_swept = (df_ltf['low'].min() <= htf_low)
        was_buy_liquidity_swept = (df_ltf['high'].max() >= htf_high)

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

        # STRATÉGIA INTELLIGENS ATR JÁTSZÓTÉR STOP-LOSSAL ÉS MAX 10X ÁTTÉTELLEL
        if was_sell_liquidity_swept and fvg_high > 0 and current_price > fvg_high and current_price > current_ema20:
            trade_signal = "LONG / BUY"
            reason = "SHORT megállt, kialakult egy FVG, amit az árfolyam egy 15 perces zöld gyertyával felfelé INVERZELT! Ez igazolja, hogy a tőke akceptálta a támaszt."
            entry_price = current_price
            stop_loss = htf_low - (1.5 * current_atr)
            take_profit_1 = entry_price + (abs(entry_price - stop_loss) * 4.0)
            take_profit_2 = max(htf_high, entry_price + (abs(entry_price - stop_loss) * 6.0))
            
        elif was_buy_liquidity_swept and fvg_low > 0 and current_price < fvg_low and current_price < current_ema20:
            trade_signal = "SHORT / SELL"
            reason = "LONG megállt, kialakult egy FVG, amit az árfolyam egy 15 perces piros gyertyával lefelé INVERZELT! Ez igazolja, hogy a tőke elfogadta az ellenállást."
            entry_price = current_price
            stop_loss = htf_high + (1.5 * current_atr)
            take_profit_1 = entry_price - (abs(entry_price - stop_loss) * 4.0)
            take_profit_2 = min(htf_low, entry_price - (abs(entry_price - stop_loss) * 6.0))

        # TRADINGVIEW GRAFIKON RAJZOLÁSA
        fig = go.Figure()
        
        fig.add_trace(go.Candlestick(
            x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
            name="15M Gyertyák",
            increasing_line_color='#089981', decreasing_line_color='#f23645',
            increasing_fillcolor='#089981', decreasing_fillcolor='#f23645'
        ))
        
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[htf_high]*len(df_ltf), name="HTF High", line=dict(color='#00e676', width=1.5)))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[htf_low]*len(df_ltf), name="HTF Low", line=dict(color='#00e676', width=1.5)))

        if fvg_high > 0 and fvg_low > 0:
            fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc, df_ltf['time'].iloc[-1]], y=[fvg_high, fvg_high], line=dict(color='#ffd600', width=2), showlegend=False))
            fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc, df_ltf['time'].iloc[-1]], y=[fvg_low, fvg_low], line=dict(color='#ffd600', width=2), showlegend=False))
            fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc, df_ltf['time'].iloc[-1]], y=[fvg_mid, fvg_mid], line=dict(color='#ffd600', width=1, dash='dash'), showlegend=False))
            fig.add_hrect(y0=fvg_low, y1=fvg_high, fillcolor="rgba(255, 214, 0, 0.05)", line_width=0)

        if trade_signal != "VÁRAKOZÁS":
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[entry_price]*len(df_ltf), name="ENTRY", line=dict(color='#00b0ff', width=2.5)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[stop_loss]*len(df_ltf), name="STOP LOSS", line=dict(color='#ff1744', width=2.5)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[take_profit_1]*len(df_ltf), name="TAKE PROFIT 1", line=dict(color='#00e676', width=2.5)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[take_profit_2]*len(df_ltf), name="TAKE PROFIT 2", line=dict(color='#00c853', width=2.5)))

        # Automatikus skálázás a tiszta láthatóságért
        buffer = (df_ltf['high'].max() - df_ltf['low'].min()) * 0.15
        y_min = min(df_ltf['low'].min(), stop_loss if trade_signal != "VÁRAKOZÁS" else htf_low) - buffer
        y_max = max(df_ltf['high'].max(), stop_loss if trade_signal != "VÁRAKOZÁS" else htf_high) + buffer

        fig.update_layout(
            template="plotly_dark", xaxis_rangeslider_visible=False, height=480,
            margin=dict(l=10, r=60, t=10, b=10),
            yaxis=dict(range=[y_min, y_max], fixedrange=False, side="right", gridcolor="#212529", tickfont=dict(size=12)),
            xaxis=dict(gridcolor="#212529"), showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("🎯 Automatizált Kereskedési Javaslat")
        
        if trade_signal != "VÁRAKOZÁS":
            if trade_signal == "LONG / BUY":
                st.success(f"🔥 **JELZÉS:** {trade_signal}")
            else:
                st.error(f"🔥 **JELZÉS:** {trade_signal}")
            st.write(f"ℹ️ **Piaci logikád megerősítése:** {reason}")
            
            sl_dist_pct = abs(entry_price - stop_loss) / entry_price
            max_loss_usd = total_balance * (risk_percent / 100)
            position_size_usd = max_loss_usd / sl_dist_pct
            
            # TŐKEÁTTÉTEL MAXIMALIZÁLÁSA 10X-EN
            leverage = int(0.8 / sl_dist_pct)
            leverage = max(1, min(leverage, 10))
            
            margin = position_size_usd / leverage
            rrr1 = abs(take_profit_1 - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0
            rrr2 = abs(take_profit_2 - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("BELÉPŐ (Market)", f"${entry_price:,.6f}")
            c2.metric("STOP LOSS (SL)", f"${stop_loss:,.6f}")
            c3.metric("TAKE PROFIT 1", f"${take_profit_1:,.6f} (RRR: 1:{rrr1:.1f})")
            c4.metric("TAKE PROFIT 2", f"${take_profit_2:,.6f} (RRR: 1:{rrr2:.1f})")
            
            st.markdown("### 📐 Pozíció és Áttétel javaslat a tőzsdédhez:")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Javasolt Tőkeáttétel", f"{leverage}x")
            cc2.metric("Megnyitandó méret dollárban", f"${position_size_usd:,.2f}")
            cc3.metric("Szükséges Margin (Tőke)", f"${margin:,.2f}")
        else:
            st.info(f"⏳ **RENDSZER STÁTUSZ:** {trade_signal}")
            st.write(f"**Jelenlegi helyzet:** {reason}")

        

       
        
        


            
        
                
        
        
