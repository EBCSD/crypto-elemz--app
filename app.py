# Kesz_Alkalmazas_Stabil_Folyamatos_Lista
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

# Szigorú TradingView Dark Mobil téma beállítása (Nincs többé fehér felület)
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; background-color: #131722; }
    [data-testid="stMetricValue"] { font-size: 20px !important; color: #00b0ff !important; font-weight: bold; }
    h1, h2, h3, p, span, caption { color: #d1d4dc !important; }
    div[data-testid="stVerticalBlock"] { background-color: #131722; }
    .signal-card { 
        background-color: #1c2030; 
        padding: 15px; 
        border-radius: 8px; 
        border: 1px solid #2a2e39; 
        margin-bottom: 25px; 
    }
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

# API Inicializálás
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
                    valid_pairs.append(symbol)
        return sorted(list(set(valid_pairs)))
    except:
        all_symbols = list(exch.markets.keys())
        return sorted(list(set([s for s in all_symbols if 'USDT' in s])))

filtered_symbols = get_active_markets()

def analyze_pair(pair_symbol):
    try:
        # 1. HTF szintek (1h Swing csúcsok és völgyek)
        htf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe='1h', limit=48)
        df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        if df_htf.empty: return None
        
        htf_high = float(df_htf['high'].iloc[:-3].max())
        htf_low = float(df_htf['low'].iloc[:-3].min())
        
        # 2. LTF szintek (15m, ha nincs FVG, leugrik 5m-re)
        timeframes_to_check = ['15m', '5m']
        chosen_tf = '15m'
        df_ltf = pd.DataFrame()
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_fvg = False
        fvg_index_start = None
        fvg_type = None
        
        for tf in timeframes_to_check:
            ltf_ohlcv = exch.fetch_ohlcv(pair_symbol, timeframe=tf, limit=40)
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
            
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
        sl, tp = 0.0, 0.0
        
        was_sell_swept = df_ltf['low'].min() <= htf_low
        was_buy_swept = df_ltf['high'].max() >= htf_high
        
        # Stratégia kiértékelése a visszahúzódás alapján
        if found_fvg and fvg_index_start is not None:
            if was_buy_swept and fvg_type == "BEARISH":
                post_fvg_df = df_ltf.iloc[fvg_index_start+2:]
                if not post_fvg_df.empty:
                    max_retest = post_fvg_df['high'].max()
                    if max_retest >= (fvg_low * 0.998):
                        entry_price = fvg_mid
                        sl = htf_high
                        tp = entry_price - (abs(entry_price - sl) * 3.5)
                        trade_signal = "SHORT / SELL"
                        
            elif was_sell_swept and fvg_type == "BULLISH":
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

# --- FOLYAMATOS EGYMÁS ALÁ LISTÁZÓ MEGJELENÍTÉS ---
st.subheader("🕵️‍♂️ Élő Találatok és Elemzések Folyamatos Listája")
scan_depth = st.slider("Átvizsgálandó top aktív párok száma:", min_value=10, max_value=100, value=40, step=10)

if st.button("🔄 Piac Pásztázása és Grafikonok Generálása", use_container_width=True):
    scan_placeholder = st.empty()
    progress_bar = st.progress(0)
    
    target_pairs = filtered_symbols[:scan_depth]
    found_any = False
    
    for idx, pair in enumerate(target_pairs):
        progress_bar.progress((idx + 1) / len(target_pairs))
        scan_placeholder.text(f"Párok elemzése háttérben: {pair}...")
        
        res = analyze_pair(pair)
        
        if res and "VÁRAKOZÁS" not in res["trade_signal"]:
            found_any = True
            df_ltf = res["df_ltf"]
            
            st.markdown(f"""
                <div class="signal-card">
                    <h3 style='margin:0;'>🔥 {pair} &nbsp;|&nbsp; Idősík: {res['chosen_tf']} &nbsp;|&nbsp; Irány: {res['trade_signal']}</h3>
                </div>
            """, unsafe_allow_html=True)
            
            fig = go.Figure()
            
            fig.add_trace(go.Candlestick(
                x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
                increasing_line_color='#089981', decreasing_line_color='#f23645',
                increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Ár"
            ))
            
            # HTF szintek előrevetítése
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*len(df_ltf), name="HTF Liq High", line=dict(color='#26a69a', width=1.5)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*len(df_ltf), name="HTF Liq Low", line=dict(color='#ef5350', width=1.5)))

            # Sárga FVG téglalap és lila szaggatott CE középvonal rajzolása (HIBA JAVÍTVA: iloc[0] és iloc[-1] pontosan lezárva)
            if res["fvg_high"] > 0 and res["fvg_start_idx"] is not None:
                s_idx = res["fvg_start_idx"]
                e_idx = min(s_idx + 10, len(df_ltf) - 1)
                
                bx = [df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[e_idx], df_ltf['time'].iloc[e_idx], df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[s_idx]]
                by = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
                
                fig.add_trace(go.Scatter(x=bx, y=by, fill="toself", fillcolor="rgba(255, 214, 0, 0.05)", line=dict(color='#ffd600', width=1.5), showlegend=False))
                fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[e_idx]], y=[res["fvg_mid"], res["fvg_mid"]], line=dict(color='#e040fb', width=1.5, dash='dash'), name="CE 50%"))

            # Kereskedési szintek berajzolása a chartra
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*len(df_ltf), name="Belépő", line=dict(color='#29b6f6', width=2)))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*len(df_ltf), name="SL", line=dict(color='#ff1744', width=1.5, dash='dash')))
            fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp"]]*len(df_ltf), name="TP", line=dict(color='#00e676', width=1.5)))

            fig.update_layout(
                template="plotly_dark", xaxis_rangeslider_visible=False, height=380,
                paper_bgcolor='#131722', plot_bgcolor='#131722', margin=dict(l=10, r=55, t=10, b=10),
                showlegend=False,
                yaxis=dict(side="right", gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)),
                xaxis=dict(gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10))
            )
