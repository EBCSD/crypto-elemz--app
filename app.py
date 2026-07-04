# Kesz_Alkalmazas_Vegleges_Strategia
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="expanded")

st.title("⚡ ALGO ICT PRO")
st.caption("Advanced Institutional Liquidity Terminal | Powered by Bitget")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot", "Margin"])

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Automata Keresési Mód")
run_scanner = st.sidebar.checkbox("Automata Piacszkenner Bekapcsolása")

# API Inicializálás
exch = getattr(ccxt, exchange_id)({'enableRateLimit': True})
exch.load_markets()
all_symbols = list(exch.markets.keys())
filtered_symbols = sorted(list(set([s for s in all_symbols if 'USDT' in s])))

def analyze_pair(pair_symbol):
    try:
        # 1. LÉPÉS: HTF Likviditási szintek lekérése (1 órás és 4 órás maximumok/minimumok)
        htf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe='1h', limit=48)
        df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        if df_htf.empty:
            return None
            
        htf_high = float(df_htf['high'].iloc[:-2].max())
        htf_low = float(df_htf['low'].iloc[:-2].min())
        
        # 2. LÉPÉS: Alacsonyabb idősík (LTF) kiválasztása. Elsőként 15m, ha nincs FVG, akkor 5m.
        timeframes_to_check = ['15m', '5m']
        chosen_tf = '15m'
        df_ltf = pd.DataFrame()
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_fvg = False
        
        for tf in timeframes_to_check:
            ltf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe=tf, limit=50)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
            
            # FVG Keresés hátulról előre az inverzió detektálásához
            for i in range(len(df_ltf) - 4, 2, -1):
                # Medve FVG (Bearish Gap)
                if df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]:
                    fvg_high = float(df_ltf['low'].iloc[i])
                    fvg_low = float(df_ltf['high'].iloc[i+2])
                    found_fvg = True
                    chosen_tf = tf
                    break
                # Bika FVG (Bullish Gap)
                elif df_ltf['high'].iloc[i] < df_ltf['low'].iloc[i+2]:
                    fvg_high = float(df_ltf['low'].iloc[i+2])
                    fvg_low = float(df_ltf['high'].iloc[i])
                    found_fvg = True
                    chosen_tf = tf
                    break
            if found_fvg:
                break
                
        if df_ltf.empty:
            return None
            
        current_price = float(df_ltf['close'].iloc[-1])
        fvg_mid = (fvg_high + fvg_low) / 2 if found_fvg else current_price
        
        # ATR a biztonsági Stop Loss kiszámításához
        high_low = df_ltf['high'] - df_ltf['low']
        high_close = (df_ltf['high'] - df_ltf['close'].shift()).abs()
        low_close = (df_ltf['low'] - df_ltf['close'].shift()).abs()
        df_ltf['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        current_atr = df_ltf['tr'].rolling(window=14).mean().iloc[-1]
        if pd.isna(current_atr):
            current_atr = current_price * 0.002
            
        trade_signal = "VÁRAKOZÁS"
        entry_price = fvg_mid  # A belépő PONTOSAN a doboz közepe (50% CE)
        sl = current_price
        tp1 = current_price
        tp2 = current_price
        
        # Likviditás söprés ellenőrzése
        was_sell_swept = df_ltf['low'].min() <= htf_low
        was_buy_swept = df_ltf['high'].max() >= htf_high
        
        # 3. LÉPÉS: INVERZ FVG ÉS PONTOS VISSZATESZT LOGIKA
        # LONG: Söpörte a HTF likviditást alul, az ár áttörte (inverzálta) az FVG-t felfelé, és most pontosan teszteli a CE (közép) szintet
        if was_sell_swept and found_fvg:
            sl = htf_low - (1.0 * current_atr)
            tp1 = entry_price + (abs(entry_price - sl) * 3.0)
            tp2 = htf_high
            # Ha a jelenlegi ár rásimul vagy nagyon közel van a doboz közepéhez (0.1%-os tűréshatár)
            if abs(current_price - fvg_mid) <= (fvg_mid * 0.0015):
                trade_signal = "LONG / BUY (CE Visszateszt)"
                
        # SHORT: Söpörte a HTF likviditást felül, az ár áttörte az FVG-t lefelé, és most pontosan teszteli a CE (közép) szintet
        elif was_buy_swept and found_fvg:
            sl = htf_high + (1.0 * current_atr)
            tp1 = entry_price - (abs(entry_price - sl) * 3.0)
            tp2 = htf_low
            if abs(current_price - fvg_mid) <= (fvg_mid * 0.0015):
                trade_signal = "SHORT / SELL (CE Visszateszt)"
                
        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp1": tp1, "tp2": tp2, "trade_signal": trade_signal, "chosen_tf": chosen_tf
        }
    except:
        return None

# --- AUTOMATA SZKENNER MEGJELENÍTÉSE ---
if run_scanner:
    st.subheader("🕵️‍♂️ Élő Inverz FVG és CE Visszateszt Találatok")
    scan_placeholder = st.empty()
    progress_bar = st.progress(0)
    
    target_pairs = filtered_symbols[:40] # Első 40 legaktívabb pár átfésülése tőzsdei rate-limit miatt
    detected_trades = []
    
    for idx, pair in enumerate(target_pairs):
        progress_bar.progress((idx + 1) / len(target_pairs))
        scan_placeholder.text(f"Folyamatos keresés: {pair}...")
        
        res = analyze_pair(pair)
        if res and "VÁRAKOZÁS" not in res["trade_signal"]:
            detected_trades.append({
                "Kriptopár": pair,
                "Idősík": res["chosen_tf"],
                "Szignál": res["trade_signal"],
                "Aktuális Ár": f"${res['current_price']:.4f}",
                "Belépő (50% CE)": f"${res['entry_price']:.4f}",
                "Stop Loss": f"${res['sl']:.4f}",
                "Target 1 (3R)": f"${res['tp1']:.4f}"
            })
        time.sleep(0.15)
        
    scan_placeholder.empty()
    progress_bar.empty()
    
    if detected_trades:
        st.dataframe(pd.DataFrame(detected_trades), use_container_width=True, hide_index=True)
    else:
        st.info("A szkenner aktív: Jelenleg egyetlen páron sincs aktív, szabályos doboz-közép (CE) visszateszt. Futás háttérben...")

# --- GRAFIKONOS RÉSZLETES NÉZET ---
st.markdown("---")
selected_pair = st.selectbox("🎯 Részletes grafikon elemzés:", filtered_symbols)
res = analyze_pair(selected_pair)

if res:
    df_ltf = res["df_ltf"]
    st.caption(f"Aktuálisan használt idősík az FVG kereséshez: **{res['chosen_tf']}**")
    
    fig = go.Figure()
    # Candlestick
    fig.add_trace(go.Candlestick(x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'], name="Gyertyák", increasing_line_color='#089981', decreasing_line_color='#f23645', increasing_fillcolor='#089981', decreasing_fillcolor='#f23645'))
    
    # HTF Likviditás Vonal (Zöld felső és alsó vonalak)
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*len(df_ltf), name="HTF Liquidity High", line=dict(color='#00e676', width=1.5, dash='solid')))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*len(df_ltf), name="HTF Liquidity Low", line=dict(color='#ff1744', width=1.5, dash='solid')))

    # FVG Doboz és a pontos szaggatott középvonal (CE) rajzolása
    if res["fvg_high"] > 0:
        fig.add_hrect(y0=res["fvg_low"], y1=res["fvg_high"], fillcolor="rgba(255, 214, 0, 0.05)", line=dict(color='#ffd600', width=1.5), name="Inverz FVG")
        # Doboz közepe (50% CE vonal szaggatottan a rajzod szerint!)
        fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[0], df_ltf['time'].iloc[-1]], y=[res["fvg_mid"], res["fvg_mid"]], name="CE 50% (Doboz Közepe)", line=dict(color='#ffea00', width=2, dash='dash')))

    # Szintek: Entry, SL, TP
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*len(df_ltf), name="BELÉPŐ (CE)", line=dict(color='#00b0ff', width=2.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*len(df_ltf), name="STOP LOSS", line=dict(color='#ff1744', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp1"]]*len(df_ltf), name="TAKE PROFIT", line=dict(color='#00c853', width=2)))

    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=480, margin=dict(l=10, r=65, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # Kockázatkezelő számítások
    sl_dist = abs(res["entry_price"] - res["sl"]) / res["entry_price"]
    loss_usd = total_balance * (risk_percent / 100)
    pos_size = loss_usd / sl_dist if sl_dist > 0 else 0
    lev = max(1, min(int(0.7 / sl_dist), 20)) if sl_dist > 0 else 1
    margin = pos_size / lev

    st.subheader("🎯 Automatizált Kereskedési Szintek (Pontos Visszateszthez)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BELÉPŐI ÁR (50% CE)", f"${res['entry_price']:.5f}")
    c2.metric("STOP LOSS (SL)", f"${res['sl']:.5f}")
    c3.metric("PROFIT CÉL (TP)", f"${res['tp1']:.5f}")
    c4.metric("AKTUÁLIS STÁTUSZ", res["trade_signal"])
    
    st.markdown("##### 📐 Javasolt pozícióméretezés ehhez a porthoz:")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Javasolt Tőkeáttétel", f"{lev}x")
