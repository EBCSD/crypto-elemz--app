# Kesz_Alkalmazas_Vegleges_Es_Biztos
import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

# Szigorú TradingView Dark Mobil téma és kártya stílusok beállítása
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; background-color: #131722; }
    h1, h2, h3, p, span, caption { color: #d1d4dc !important; }
    div[data-testid="stVerticalBlock"] { background-color: #131722; }
    .signal-header { 
        background-color: #1c2030; 
        padding: 12px; 
        border-radius: 6px; 
        border-left: 5px solid #ffd600;
        margin-top: 25px;
        margin-bottom: 15px; 
    }
    .data-row {
        background-color: #1c2030;
        padding: 10px;
        border-radius: 6px;
        border: 1px solid #2a2e39;
        margin-top: 5px;
        margin-bottom: 5px;
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

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Automata Keresési Mód")
run_scanner = st.sidebar.checkbox("Automata Piacszkenner Indítása", value=True)

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
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol

        # 1. HTF szintek lekérése
        htf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        df_htf = pd.DataFrame(htf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        if df_htf.empty: return None
        
        htf_high = float(df_htf['high'].iloc[:-3].max())
        htf_low = float(df_htf['low'].iloc[:-3].min())
        
        # 2. LTF szintek (15m, ha nincs FVG -> 5m)
        timeframes_to_check = ['15m', '5m']
        chosen_tf = '15m'
        df_ltf = pd.DataFrame()
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_fvg = False
        fvg_index_start = None
        fvg_type = None
        
        for tf in timeframes_to_check:
            ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=tf, limit=40)
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
        
        sl = htf_high if fvg_type == "BEARISH" else htf_low
        tp = entry_price - (abs(entry_price - sl) * 3.5) if fvg_type == "BEARISH" else entry_price + (abs(entry_price - sl) * 3.5)
        
        was_sell_swept = df_ltf['low'].min() <= htf_low
        was_buy_swept = df_ltf['high'].max() >= htf_high
        
        if found_fvg and fvg_index_start is not None:
            if was_buy_swept and fvg_type == "BEARISH":
                entry_price = fvg_mid
                sl = htf_high
                tp = entry_price - (abs(entry_price - sl) * 3.5)
                trade_signal = "SHORT / SELL"
                        
            elif was_sell_swept and fvg_type == "BULLISH":
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

# --- AUTOMATA FOLYAMATOS MEGJELENÍTŐ RENDSZER ---
if run_scanner:
    st.subheader("🕵️‍♂️ Élő Kétirányú Piacszkenner (Minden Adat Egymás Alatt)")
    scan_depth = st.slider("Átvizsgálandó top aktív párok száma:", min_value=5, max_value=30, value=15, step=5)
    
    active_signals = []
    scan_placeholder = st.empty()
    
    target_pairs = filtered_symbols[:scan_depth]
    for pair in target_pairs:
        scan_placeholder.text(f"Piac pásztázása... Ellenőrzés: {pair}")
        res = analyze_pair(pair)
        if res and "VÁRAKOZÁS" not in res["trade_signal"]:
            active_signals.append((pair, res))
        time.sleep(0.04)

    scan_placeholder.empty()

    # Kirajzolási fázis teljesen tiszta, fix struktúrával
    if active_signals:
        for idx, (pair, res) in enumerate(active_signals):
            df_ltf = res["df_ltf"]
            
            # A) FEJLÉC KÁRTYA
            clean_display_name = pair.split(':')[0] if ':' in pair else pair
            st.markdown(f"""
                <div class="signal-header">
                    <h3 style='margin:0; font-size:16px;'>🔥 {clean_display_name} &nbsp;|&nbsp; Idősík: {res['chosen_tf']} &nbsp;|&nbsp; Irány: {res['trade_signal']}</h3>
                </div>
            """, unsafe_allow_html=True)
            
            # B) TRADINGVIEW STÍLUSÚ GRAFIKON (PONTOS, HIBÁTLAN HLINE MEGOLDÁSSAL)
            fig = go.Figure()
            
            fig.add_trace(go.Candlestick(
                x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
                increasing_line_color='#089981', decreasing_line_color='#f23645',
                increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Ár"
            ))
            
            # JAVÍTÁS: A go.Scatter szorzások helyett stabil, natív beépített Plotly hline-okat használunk!
            fig.add_hline(y=res["htf_high"], line_color="#26a69a", line_width=2, name="HTF Liq High")
            fig.add_hline(y=res["htf_low"], line_color="#ef5350", line_width=2, name="HTF Liq Low")
            
            fig.add_hline(y=res["entry_price"], line_color="#29b6f6", line_width=2, name="Belépő")
            fig.add_hline(y=res["sl"], line_color="#ff1744", line_width=1.5, line_dash="dash", name="SL")
            fig.add_hline(y=res["tp"], line_color="#00e676", line_width=1.5, name="TP")

            # FVG téglalap és a lila szaggatott CE középvonal kirajzolása
            if res["fvg_high"] > 0 and res["fvg_start_idx"] is not None:
                s_idx = int(res["fvg_start_idx"])
                e_idx = int(min(s_idx + 12, len(df_ltf) - 1))
                
                t_start = df_ltf['time'].iloc[s_idx]
                t_end = df_ltf['time'].iloc[e_idx]
                
                bx = [t_start, t_end, t_end, t_start, t_start]
                by = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
                
                fig.add_trace(go.Scatter(x=bx, y=by, fill="toself", fillcolor="rgba(255, 214, 0, 0.06)", line=dict(color='#ffd600', width=1.5), showlegend=False))
                fig.add_trace(go.Scatter(x=[t_start, t_end], y=[res["fvg_mid"], res["fvg_mid"]], line=dict(color='#e040fb', width=2, dash='dash'), name="CE 50%"))

            y_pad = (max(df_ltf['high'].max(), res["htf_high"]) - min(df_ltf['low'].min(), res["htf_low"])) * 0.1
            y_min = min(df_ltf['low'].min(), res["htf_low"], res["tp"]) - y_pad
            y_max = max(df_ltf['high'].max(), res["htf_high"], res["tp"]) + y_pad

            fig.update_layout(
                template="plotly_dark", xaxis_rangeslider_visible=False, height=400,
                paper_bgcolor='#131722', plot_bgcolor='#131722', margin=dict(l=10, r=55, t=10, b=10),
                showlegend=False,
