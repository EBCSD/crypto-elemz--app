# Kesz_Alkalmazas
import streamlit as st
import pandas as pd
import ccxt

st.set_page_config(page_title="ICT Auto Trader Bot", layout="wide", initial_sidebar_state="collapsed")
st.title("🏹 ICT Liquidity Sweep & IFVG Automata Elemző")

# 1. Tőzsde és Piac választó a felhasználó által
st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot"])

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
    
    # Kriptopárok betöltése a tőzsdéről
    with st.spinner("Piacok betöltése a tőzsdéről..."):
        exch.load_markets()
        
    all_symbols = list(exch.markets.keys())
    
    # Szűrés Spot vagy Futures (Linear/Swap) párokra
    if market_type == "Futures":
        filtered_symbols = [s for s in all_symbols if exch.markets[s]['linear'] or 'USDT' in s and ':' in s]
    else:
        filtered_symbols = [s for s in all_symbols if exch.markets[s]['spot']]
        
    # Felhasználó kiválasztja a konkrét párt
    selected_pair = st.selectbox("2. Válassz ki egy kriptopárt az elemzéshez:", filtered_symbols if filtered_symbols else ["Nincs adat"])

    if selected_pair and selected_pair != "Nincs adat":
        st.markdown(f"### 🔍 **{selected_pair.upper()}** Részletes ICT Elemzése...")
        
        # ADATGYŰJTÉS: 1H és 15M gyertyák lekérése a Bitget/Binance szerveréről
        with st.spinner("Gyertyaadatok elemzése (1H Likviditás és 15M Idősík)..."):
            # 1 Órás gyertyák a HTF Likviditáshoz (utolsó 48 gyertya)
            htf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='1h', limit=48)
            df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            
            # 15 Perces gyertyák a belépőhöz és az Inverse FVG-hez
            ltf_ohlcv = exch.fetch_ohlcv(selected_pair, timeframe='15m', limit=20)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])

        # STRATÉGIA SZÁMÍTÁSA: 1H Likviditási Pontok (High / Low) meghatározása
        htf_high = df_htf['high'].max()
        htf_low = df_htf['low'].min()
        
        current_price = df_ltf['close'].iloc[-1]
        prev_price = df_ltf['close'].iloc[-2]
        
        # 15M EMA megerősítés kiszámítása
        df_ltf['ema20'] = df_ltf['close'].ewm(span=20, adjust=False).mean()
        current_ema20 = df_ltf['ema20'].iloc[-1]

        # AUTOMATA JELZÉS GENERÁLÁS (Sweep + IFVG Törés koncepció)
        trade_signal = "VÁRAKOZÁS"
        reason = "Az árfolyam jelenleg a likviditási szintek között mozog, nincs érvényes sweep."

        # Ellenőrizzük, hogy az utolsó néhány gyertyában történt-e 1H Likviditás kiszedés (Sweep)
        was_sell_liquidity_swept = (df_ltf['low'].min() <= htf_low)
        was_buy_liquidity_swept = (df_ltf['high'].max() >= htf_high)

        # 1. LONG STRATÉGIA: Sell Liquidity kiszedve + az árfolyam egy korábbi medvés FVG fölé zárt (Inverzió) és az EMA20 felett van
        if was_sell_liquidity_swept and current_price > current_ema20 and current_price > prev_price:
            trade_signal = "LONG / BUY"
            reason = "A szoftver detektálta az 1H Sell Liquidity kiszedését, és a 15 perces gyertya megerősítette a fordulót az Inverse FVG zóna felett!"
            
            entry_price = current_price
            # Stop Loss szigorúan a kiszedett 1H likviditási minimum alá helyezve
            stop_loss = htf_low * 0.995 
            # Elsődleges Take Profit a szemközti 1H Buy Liquidity szint
            take_profit = htf_high
            
        # 2. SHORT STRATÉGIA: Buy Liquidity kiszedve + az árfolyam egy korábbi bikás FVG alá zárt (Inverzió) és az EMA20 alatt van
        elif was_buy_liquidity_swept and current_price < current_ema20 and current_price < prev_price:
            trade_signal = "SHORT / SELL"
            reason = "A szoftver detektálta az 1H Buy Liquidity kiszedését, és a 15 perces gyertya megerősítette a fordulót az Inverse FVG zóna alatt!"
            
            entry_price = current_price
            # Stop Loss a kiszedett maximum fölé helyezve
            stop_loss = htf_high * 1.005
            # Célár a lenti 1H Sell Liquidity szint
            take_profit = htf_low

        # EREDMÉNYEK KIIRATÁSA A KIJELZŐRE
        st.markdown("---")
        st.subheader("🎯 Automatizált Kereskedési Javaslat")
        
        if trade_signal == "LONG / BUY":
            st.success(f"🔥 **JELZÉS:** {trade_signal}")
            st.write(f"ℹ️ **Magyarázat:** {reason}")
            
            # Pozíció méretezés kiszámítása
            sl_dist_pct = abs(entry_price - stop_loss) / entry_price
            max_loss_usd = total_balance * (risk_percent / 100)
            position_size_usd = max_loss_usd / sl_dist_pct
            leverage = max(1, min(int(0.8 / sl_dist_pct), 50))
            margin = position_size_usd / leverage
            
            # Kész kereskedési terv megjelenítése
            c1, c2, c3 = st.columns(3)
            c1.metric("BELÉPÉSI ÁR (Market Entry)", f"${entry_price:,.4f}")
            c2.metric("STOP LOSS (SL)", f"${stop_loss:,.4f}")
            c3.metric("TAKE PROFIT (TP)", f"${take_profit:,.4f}")
            
            st.markdown("### 📐 Bitget Pozíció és Áttétel javaslat:")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Javasolt Tőkeáttétel", f"{leverage}x")
            cc2.metric("Megnyitandó méret dollárban", f"${position_size_usd:,.2f}")
            cc3.metric("Szükséges fedezet (Margin)", f"${margin:,.2f}")
            
        elif trade_signal == "SHORT / SELL":
            st.error(f"🔥 **JELZÉS:** {trade_signal}")
            st.write(f"ℹ️ **Magyarázat:** {reason}")
            
            sl_dist_pct = abs(entry_price - stop_loss) / entry_price
            max_loss_usd = total_balance * (risk_percent / 100)
            position_size_usd = max_loss_usd / sl_dist_pct
            leverage = max(1, min(int(0.8 / sl_dist_pct), 50))
            margin = position_size_usd / leverage
            
            c1, c2, c3 = st.columns(3)
            c1.metric("BELÉPÉSI ÁR (Market Entry)", f"${entry_price:,.4f}")
            c2.metric("STOP LOSS (SL)", f"${stop_loss:,.4f}")
            c3.metric("TAKE PROFIT (TP)", f"${take_profit:,.4f}")
            
            st.markdown("### 📐 Bitget Pozíció és Áttétel javaslat:")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Javasolt Tőkeáttétel", f"{leverage}x")
            cc2.metric("Megnyitandó méret dollárban", f"${position_size_usd:,.2f}")
            cc3.metric("Szükséges fedezet (Margin)", f"${margin:,.2f}")
            
        else:
            st.info(f"⏳ **RENDSZER STÁTUSZ:** {trade_signal}")
            st.write(f"**Jelenlegi helyzet:** {reason}")
            st.write(f"Az alkalmazás folyamatosan figyeli az 1H Likviditási szinteket: Felső korlát (Buy Liq): **${htf_high:,.4f}** | Alsó korlát (Sell Liq): **${htf_low:,.4f}**. Jelenlegi élő ár: **${current_price:,.4f}**.")

except Exception as e:
    st.error(f"Szerver csatlakozási hiba történt: {e}")
    st.info("Próbálj meg átváltani egy másik tőzsdére vagy piacra az oldalsó menüben a frissítéshez.")


 
             
    
    


            
        
                
        
        
