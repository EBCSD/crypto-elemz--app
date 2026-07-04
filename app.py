# Kesz_Alkalmazas_Javitott_Stabil
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

# TradingView-szerű mobil háttér beállítása
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; background-color: #131722; }
    [data-testid="stMetricValue"] { font-size: 22px !important; color: #d1d4dc; }
    h1, h2, h3, caption { color: #d1d4dc !important; }
    </style>
""", unsafe_allow_html=True)

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

# API Inicializálás - Hibajavítás a szűrésnél
exch = getattr(ccxt, exchange_id)({'enableRateLimit': True})
exch.load_markets()
all_symbols = list(exch.markets.keys())
filtered_symbols = sorted(list(set([s for s in all_symbols if 'USDT' in s])))

def analyze_pair(pair_symbol):
    try:
        # 1. LÉPÉS: HTF Szintek lekérése (1h / 4h szintek a likviditásért)
        htf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe='1h', limit=48)
        df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        if df_htf.empty: return None
        
        htf_high = float(df_htf['high'].iloc[:-2].max())
        htf_low = float(df_htf['low'].iloc[:-2].min())
        
        # 2. LÉPÉS: LTF Idősík kezelése (15m, ha nincs, akkor 5m)
        timeframes_to_check = ['15m', '5m']
        chosen_tf = '15m'
        df_ltf = pd.DataFrame()
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_fvg = False
        fvg_index_start = None
        fvg_type = None
        
        for tf in timeframes_to_check:
            ltf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe=tf, limit=45)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
            
            # FVG Keresése a grafikonon
            for i in range(len(df_ltf) - 4, 2, -1):
                if df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]: # Bearish FVG
                    fvg_high = float(df_ltf['low'].iloc[i])
                    fvg_low = float(df_ltf['high'].iloc[i+2])
                    fvg_index_start = i
                    fvg_type = "BEARISH"
                    found_fvg = True
                    chosen_tf = tf
                    break
                elif df_ltf['high'].iloc[i] < df_ltf['low'].iloc[i+2]: # Bullish FVG
                    fvg_high = float(df_ltf['low'].iloc[i+2])
                    fvg_low = float(df_ltf['high'].iloc[i])
                    fvg_index_start = i
                    fvg_type = "BULLISH"
                    found_fvg = True
                    chosen_tf = tf
                    break
            if found_fvg: break
            
        if df_ltf.empty: return None
        
        current_price = float(df_ltf['close'].iloc[-1])
        fvg_mid = (fvg_high + fvg_low) / 2 if found_fvg else current_price
        
        trade_signal = "VÁRAKOZÁS"
        entry_price = fvg_mid
        sl, tp = current_price, current_price
        
        was_sell_swept = df_ltf['low'].min() <= htf_low
        was_buy_swept = df_ltf['high'].max() >= htf_high
        
        # 3. LÉPÉS: PONTOS SHORT ÉS LONG IRÁNYÚ STRATÉGIA LOGIKA
        if found_fvg and fvg_index_start is not None:
            if was_buy_swept and fvg_type == "BEARISH":
                post_fvg_df = df_ltf.iloc[fvg_index_start+2:]
                if not post_fvg_df.empty:
                    max_retest = post_fvg_df['high'].max()
                    if max_retest >= fvg_low and current_price <= fvg_high:
                        entry_price = fvg_mid
                        sl = htf_high
                        tp = fvg_mid - (abs(fvg_mid - sl) * 3.5)
                        trade_signal = "SHORT / SELL (Inverz FVG Visszateszt)"
                        
            elif was_sell_swept and fvg_type == "BULLISH":
                post_fvg_df = df_ltf.iloc[fvg_index_start+2:]
                if not post_fvg_df.empty:
                    min_retest = post_fvg_df['low'].min()
                    if min_retest <= fvg_high and current_price >= fvg_low:
                        entry_price = fvg_mid
                        sl = htf_low
                        tp = fvg_mid + (abs(fvg_mid - sl) * 3.5)
                        trade_signal = "LONG / BUY (Inverz FVG Visszateszt)"
                        
        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": chosen_tf, 
            "fvg_start_idx": fvg_index_start, "fvg_type": fvg_type
        }
    except:
        return None

# --- AUTOMATA SZKENNER ---
if run_scanner:
    st.subheader("🕵️‍♂️ Élő Kétirányú Szkenner (LONG & SHORT Találatok)")
    scan_placeholder = st.empty()
    target_pairs = filtered_symbols[:35]
    detected_trades = []
    
    for pair in target_pairs:
        scan_placeholder.text(f"Keresés (Long/Short FVG és Visszateszt)... {pair}")
        res = analyze_pair(pair)
        if res and "VÁRAKOZÁS" not in res["trade_signal"]:
            detected_trades.append({
                "Kriptopár": pair, "Idősík": res["chosen_tf"], "Irány/Szignál": res["trade_signal"],
                "Aktuális Ár": f"${res['current_price']:.4f}", "Beszálló (CE)": f"${res['entry_price']:.4f}",
                "Stop Loss": f"${res['sl']:.4f}", "Take Profit": f"${res['tp']:.4f}"
            })
        time.sleep(0.1)
    scan_placeholder.empty()
    
    if detected_trades:
        st.dataframe(pd.DataFrame(detected_trades), use_container_width=True, hide_index=True)
    else:
        st.info("A piacot figyeljük: Jelenleg nincs egyetlen szabályos mintázat szerinti visszazúzódás sem.")

# --- MOBIL GRAFIKON STABIL JAVÍTÁSSAL ---
st.markdown("---")
selected_pair = st.selectbox("🎯 Válassz ki egy párt a TradingView-nézethez:", filtered_symbols)
res = analyze_pair(selected_pair)

if res:
    df_ltf = res["df_ltf"]
    
    fig = go.Figure()
    
    fig.add_trace(go.Candlestick(
        x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
        increasing_line_color='#089981', decreasing_line_color='#f23645',
        increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Árfolyam"
    ))
    
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*len(df_ltf), name="HTF Liquidity High", line=dict(color='#26a69a', width=2)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*len(df_ltf), name="HTF Liquidity Low", line=dict(color='#ef5350', width=2)))

    # JAVÍTÁS: Szabályos go.Scatter téglalap rajzolás fill='toself' paraméterrel, és .iloc[] zárójelek pótlása
    if res["fvg_high"] > 0 and res["fvg_start_idx"] is not None:
        start_idx = res["fvg_start_idx"]
        end_idx = min(start_idx + 8, len(df_ltf) - 1)
        
        box_x = [df_ltf['time'].iloc[start_idx], df_ltf['time'].iloc[end_idx], df_ltf['time'].iloc[end_idx], df_ltf['time'].iloc[start_idx], df_ltf['time'].iloc[start_idx]]
        box_y = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
        
        # Stabil TradingView FVG doboz
        fig.add_trace(go.Scatter(x=box_x, y=box_y, fill="toself", fillcolor="rgba(255, 214, 0, 0.08)", line=dict(color='#ffd600', width=1.5), name="FVG Doboz"))
        
        # Doboz felezővonala (CE 50%) - .iloc[] hiba javítva
        fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[start_idx], df_ltf['time'].iloc[end_idx]], y=[res["fvg_mid"], res["fvg_mid"]], line=dict(color='rgba(255, 214, 0, 0.6)', width=1.5, dash='dash'), name="CE 50%"))

    if "VÁRAKOZÁS" not in res["trade_signal"]:
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*len(df_ltf), name="Belépési Ár", line=dict(color='#29b6f6', width=2)))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*len(df_ltf), name="Stop Loss (SL)", line=dict(color='#ff1744', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp"]]*len(df_ltf), name="Take Profit (TP)", line=dict(color='#00e676', width=2)))

    fig.update_layout(
        template="plotly_dark", xaxis_rangeslider_visible=False, height=520,
        paper_bgcolor='#131722', plot_bgcolor='#131722',
        margin=dict(l=10, r=60, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5, font=dict(size=10, color="#d1d4dc")),
        yaxis=dict(side="right", gridcolor="#2a2e39", zeroline=False, tickfont=dict(size=11, color="#848e9c")),
        xaxis=dict(gridcolor="#2a2e39", zeroline=False, tickfont=dict(size=11, color="#848e9c"))
    )
    st.plotly_chart(fig, use_container_width=True)

    # Szintek kiírása
    st.subheader("🎯 Szignál és Pozíció Kalkulátor")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BESZÁLÓ (CE)", f"${res['entry_price']:.5f}")
    c2.metric("STOP LOSS", f"${res['sl']:.5f}")
    c3.metric("TAKE PROFIT", f"${res['tp']:.5f}")
