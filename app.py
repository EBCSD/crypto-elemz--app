# Kesz_Alkalmazas_Vegleges_Tokeletes
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

# Pontos TradingView sötét téma és mobilbarát elrendezés injektálása
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; background-color: #131722; }
    [data-testid="stMetricValue"] { font-size: 22px !important; color: #d1d4dc; }
    h1, h2, h3, caption { color: #d1d4dc !important; }
    div[data-testid="stBlock"] { background-color: #1c2030; padding: 10px; border-radius: 6px; }
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
run_scanner = st.sidebar.checkbox("Automata Piacszkenner Bekapcsolása", value=True)

# API Inicializálás rate-limit és stabil típuskezeléssel
exch = getattr(ccxt, exchange_id)({
    'enableRateLimit': True,
    'options': {'defaultType': 'future' if market_type == "Futures" else 'spot'}
})
exch.load_markets()

@st.cache_data(ttl=300)
def get_active_markets():
    try:
        markets = exch.fetch_tickers()
        valid_pairs = []
        for symbol, ticker in markets.items():
            if 'USDT' in symbol and '/' in symbol:
                if ticker.get('quoteVolume', 0) > 10000 or market_type == "Futures":
                    valid_pairs.append((symbol, ticker.get('quoteVolume', 0)))
        valid_pairs.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in valid_pairs]
    except:
        all_symbols = list(exch.markets.keys())
        return sorted(list(set([s for s in all_symbols if 'USDT' in s])))

filtered_symbols = get_active_markets()

def analyze_pair(pair_symbol):
    try:
        # 1. HTF Likviditás lekérése (Valódi Swing szintek az 1 órásról)
        htf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe='1h', limit=48)
        df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        if df_htf.empty: return None
        
        htf_high = float(df_htf['high'].iloc[:-3].max())
        htf_low = float(df_htf['low'].iloc[:-3].min())
        
        # 2. LTF Idősík váltó logika (15m -> 5m)
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
            
            for i in range(len(df_ltf) - 4, 2, -1):
                if df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]: # Bearish FVG (Mint a beküldött képeden)
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
        sl, tp = 0.0, 0.0
        
        was_sell_swept = df_ltf['low'].min() <= htf_low
        was_buy_swept = df_ltf['high'].max() >= htf_high
        
        # 3. STRATÉGIA: Söprés -> Inverzió -> Visszazúzódás tesztelése
        if found_fvg and fvg_index_start is not None:
            if was_buy_swept and fvg_type == "BEARISH": # SHORT SZITUÁCIÓ (Mint a képen)
                post_fvg_df = df_ltf.iloc[fvg_index_start+2:]
                if not post_fvg_df.empty:
                    max_retest = post_fvg_df['high'].max()
                    # Ha az ár visszaszúrt a dobozba (visszazúzódás) a jobb beszállóért
                    if max_retest >= (fvg_low * 0.998):
                        entry_price = fvg_mid
                        sl = htf_high
                        tp = entry_price - (abs(entry_price - sl) * 3.5)
                        trade_signal = "SHORT / SELL"
                        
            elif was_sell_swept and fvg_type == "BULLISH": # LONG SZITUÁCIÓ
                post_fvg_df = df_ltf.iloc[fvg_index_start+2:]
                if not post_fvg_df.empty:
                    min_retest = post_fvg_df['low'].min()
                    if min_retest <= (fvg_high * 1.002):
                        entry_price = fvg_mid
                        sl = htf_low
                        tp = entry_price + (abs(entry_price - sl) * 3.5)
                        trade_signal = "LONG / BUY"
                        
        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": chosen_tf, 
            "fvg_start_idx": fvg_index_start, "fvg_type": fvg_type
        }
    except:
        return None

# --- AUTOMATA SZKENNER PANEL ---
if run_scanner:
    st.subheader("🕵️‍♂️ Élő Automata Piacszkenner (Szűrt találatok)")
    scan_depth = st.slider("Átvizsgálandó top aktív párok száma:", min_value=20, max_value=150, value=80, step=10)
    
    if st.button("🔄 Piac Átfésülése és Szignálok Listázása"):
        detected_trades = []
        scan_placeholder = st.empty()
        progress_bar = st.progress(0)
        
        target_pairs = filtered_symbols[:scan_depth]
        for idx, pair in enumerate(target_pairs):
            progress_bar.progress((idx + 1) / len(target_pairs))
            scan_placeholder.text(f"Keresés folyamatban ({idx+1}/{len(target_pairs)}): {pair}")
            res = analyze_pair(pair)
            if res and "VÁRAKOZÁS" not in res["trade_signal"]:
                detected_trades.append({
                    "Kriptopár": pair, "Idősík": res["chosen_tf"], "Irány/Szignál": res["trade_signal"],
                    "Aktuális Ár": f"${res['current_price']:.4f}", "Beszálló (CE)": f"${res['entry_price']:.4f}"
                })
            time.sleep(0.05)
        scan_placeholder.empty()
        progress_bar.empty()
        
        if detected_trades:
            st.success(f"Találtam {len(detected_trades)} db szabályos, visszatesztelt setupot!")
            st.dataframe(pd.DataFrame(detected_trades), use_container_width=True, hide_index=True)
        else:
            st.info("Jelenleg nincs éles mintázat a kiválasztott piaci tartományban.")

# --- HAJSZÁLPONTOS TRADINGVIEW GRAFIKON (A KÉPED ALAPJÁN) ---
st.markdown("---")
selected_pair = st.selectbox("🎯 Válassz ki egy párt a TradingView-nézethez:", filtered_symbols)
res = analyze_pair(selected_pair)

if res:
    df_ltf = res["df_ltf"]
    fig = go.Figure()
    
    # 1. Gyertyák rajzolása tűpontos TradingView színekkel
    fig.add_trace(go.Candlestick(
        x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
        increasing_line_color='#089981', decreasing_line_color='#f23645',
        increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Árfolyam"
    ))
    
    # 2. HTF Likviditási szintek előrevetítése (Zöld felső vonal hajszálpontosan a csúcsra illesztve)
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*len(df_ltf), name="HTF High Liq", line=dict(color='#26a69a', width=2)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*len(df_ltf), name="HTF Low Liq", line=dict(color='#ef5350', width=2)))

    # 3. FIX DOBOZ RAJZOLÁS: Pontosan úgy néz ki, mint a TradingView sárga zárt téglalapja!
    if res["fvg_high"] > 0 and res["fvg_start_idx"] is not None:
        start_idx = res["fvg_start_idx"]
        # A dobozt elhúzzuk a legfrissebb gyertya utáni ablakig, hogy zárt téglalapot alkosson a képed szerint
        end_idx = min(start_idx + 10, len(df_ltf) - 1)
        
        box_x = [df_ltf['time'].iloc[start_idx], df_ltf['time'].iloc[end_idx], df_ltf['time'].iloc[end_idx], df_ltf['time'].iloc[start_idx], df_ltf['time'].iloc[start_idx]]
        box_y = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
        
        # Sárga zárt téglalap doboz kitöltéssel
        fig.add_trace(go.Scatter(x=box_x, y=box_y, fill="toself", fillcolor="rgba(255, 214, 0, 0.04)", line=dict(color='#ffd600', width=2), name="FVG Doboz"))
        
        # Lila szaggatott CE 50% középvonal pontosan a dobozon belül vezetve, ahogy a képeden látszik!
