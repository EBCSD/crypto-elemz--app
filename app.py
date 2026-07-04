 # Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go

st.set_page_config(page_title="ICT Auto Trader Bot", layout="wide", initial_sidebar_state="collapsed")
st.title("🏹 ICT Liquidity Sweep & IFVG Automata Elemző")

# 1. Tőzsde és Piac választó a felhasználó által
st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot", "Margin"])

# Kockázatkezelési panel
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Megengedett kockázat (%):", min_value=0.5, max_value=5.0, value=1.0)

# Tőzsde inicializálása a háttérben
@st.cache_resource
def init_exchange(exch_id):
    exch_class = getattr(ccxt, exch_id)
    return exch_class({'enableRateLimit': True})

try:
    exch = init_exchange(exchange_id)
    
    with st.spinner("Piacok betöltése a tőzsdéről..."):
        exch.load_markets()
        
    all_symbols = list(exch.markets.keys())
    
    # Szűrés a felhasználó által választott piac típusra
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
            # HTF Adatgyűjtés (1 Órás gyertyák a Likviditáshoz)
            htf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='1h', limit=48)
            df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_htf['time'] = pd.to_datetime(df_htf['time'], unit='ms')
            
            # LTF Adatgyűjtés (15 Perces gyertyák a belépőhöz és grafikonhoz)
            ltf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='15m', limit=40)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')

        # Matematikai számítások
        htf_high = df_htf['high'].max()
        htf_low = df_htf['low'].min()
        current_price = df_ltf['close'].iloc[-1]
        prev_price = df_ltf['close'].iloc[-2]
        
        df_ltf['ema20'] = df_ltf['close'].ewm(span=20, adjust=False).mean()
        current_ema20 = df_ltf['ema20'].iloc[-1]

        # Automata stratégia szintek inicializálása
        trade_signal = "VÁRAKOZÁS"
        reason = "Az árfolyam jelenleg a likviditási szintek között mozog, nincs érvényes sweep."
        
        was_sell_liquidity_swept = (df_ltf['low'].min() <= htf_low)
        was_buy_liquidity_swept = (df_ltf['high'].max() >= htf_high)

        # FVG és Inverziós sáv meghatározása a grafikonhoz
        fvg_high, fvg_low = 0.0, 0.0
        
        # Szoftveres IFVG keresés az utolsó gyertyákban
        for i in range(len(df_ltf)-3, 1, -1):
            if df_ltf['high'].iloc[i-2] < df_ltf['low'].iloc[i]: # Medvés FVG rés
                fvg_high = df_ltf['low'].iloc[i]
                fvg_low = df_ltf['high'].iloc[i-2]
                break
            elif df_ltf['low'].iloc[i-2] > df_ltf['high'].iloc[i]: # Bikás FVG rés
                fvg_high = df_ltf['low'].iloc[i-2]
                fvg_low = df_ltf['high'].iloc[i]
                break

        # LONG SETUP
        if was_sell_liquidity_swept and current_price > current_ema20 and current_price > prev_price:
            trade_signal = "LONG / BUY"
            reason = "A szoftver detektálta az 1H Sell Liquidity sweep-et, és az árfolyam az Inverse FVG zóna felett zárt!"
            entry_price = current_price
            stop_loss = htf_low * 0.995 
            take_profit = htf_high
            
        # SHORT SETUP
        elif was_buy_liquidity_swept and current_price < current_ema20 and current_price < prev_price:
            trade_signal = "SHORT / SELL"
            reason = "A szoftver detektálta az 1H Buy Liquidity sweep-et, és az árfolyam az Inverse FVG zóna alatt zárt!"
            entry_price = current_price
            stop_loss = htf_high * 1.005
            take_profit = htf_low

        # 1. Grafikon felépítése (Interaktív Gyertya Chart)
        fig = go.Figure()
        
        # Élő 15M gyertyák rajzolása
        fig.add_trace(go.Candlestick(
            x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
            name="15M Gyertyák"
        ))
        
        # HTF Likviditási vonalak berajzolása
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[htf_high]*len(df_ltf), name="HTF Buy Liquidity (High)", line=dict(color='rgba(255, 0, 0, 0.5)', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[htf_low]*len(df_ltf), name="HTF Sell Liquidity (Low)", line=dict(color='rgba(0, 255, 0, 0.5)', width=2, dash='dash')))

        # Ha kialakult FVG zóna, szürke háttérsávként berajzoljuk
        if fvg_high > 0 and fvg_low > 0:
            fig.add_hrect(y0=fvg_low, y1=fvg_high, fillcolor="rgba(128, 128, 128, 0.2)", line_width=0, annotation_text="IFVG Zóna", annotation_position="top left")

        # Kereskedési szintek berajzolása a grafikonra, ha van aktív szignál
        if trade_signal != "VÁRAKOZÁS":
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[entry_price]*len(df_ltf), name="ENTRY (Belépő)", line=dict(color='cyan', width=3)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[stop_loss]*len(df_ltf), name="STOP LOSS (SL)", line=dict(color='crimson', width=3)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[take_profit]*len(df_ltf), name="TAKE PROFIT (TP)", line=dict(color='forestgreen', width=3)))

        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=450, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # 2. Szignál és Matematikai Eredmények Dobozai
        st.markdown("---")
        st.subheader("🎯 Automatizált Kereskedési Javaslat")
        
        if trade_signal != "VÁRAKOZÁS":
            if trade_signal == "LONG / BUY":
                st.success(f"🔥 **JELZÉS:** {trade_signal}")
            else:
                st.error(f"🔥 **JELZÉS:** {trade_signal}")
                
            st.write(f"ℹ️ **Magyarázat:** {reason}")
            
            # Kockázatszámítás
            sl_dist_pct = abs(entry_price - stop_loss) / entry_price
            max_loss_usd = total_balance * (risk_percent / 100)
            position_size_usd = max_loss_usd / sl_dist_pct
            leverage = max(1, min(int(0.8 / sl_dist_pct), 50))
            margin = position_size_usd / leverage
            rrr = abs(take_profit - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("BELÉPÉSI ÁR (Market Entry)", f"${entry_price:,.4f}")
            c2.metric("STOP LOSS (SL)", f"${stop_loss:,.4f}")
            c3.metric("TAKE PROFIT (TP)", f"${take_profit:,.4f}")
            
            st.markdown("### 📐 Pozíció és Áttétel javaslat:")
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("Javasolt Tőkeáttétel", f"{leverage}x")
            cc2.metric("Megnyitandó méret", f"${position_size_usd:,.2f}")
            cc3.metric("Szükséges Margin", f"${margin:,.2f}")
            cc4.metric("Kockázat/Nyereség (RRR)", f"1 : {rrr:.2f}")
            
        else:
            st.info(f"⏳ **RENDSZER STÁTUSZ:** {trade_signal}")
            st.write(f"**Jelenlegi helyzet:** {reason}")
            st.write(f"Élő ár: **${current_price:,.4f}** | Felső 1H Likviditás: **${htf_high:,.4f}** | Alsó 1H Likviditás: **${htf_low:,.4f}**")

except Exception as e:
    st.error(f"Hiba történt az adatok feldolgozásában: {e}")
    st.info("Próbálj meg átváltani egy másik tőzsdére vagy piacra az oldalsó menüben a frissítéshez.")

        
         
             
    
    


            
        
                
        
        
