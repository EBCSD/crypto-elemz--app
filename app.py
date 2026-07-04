import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# 1. OLDALBEÁLLÍTÁSOK ÉS TRADINGVIEW DESIGN
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")

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

st.title("⚡ ALGO ICT PRO V2")
st.caption("Advanced Institutional Liquidity Terminal | Powered by Bitget")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot"])

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
        tickers = exch.fetch_tickers()
        pairs = []
        for sym, t in tickers.items():
            if 'USDT' in sym and '/' in sym:
                if t.get('quoteVolume', 0) > 5000 or market_type == "Futures":
                    pairs.append(sym)
        return sorted(list(set(pairs)))
    except:
        return sorted(list(set([s for s in exch.markets.keys() if 'USDT' in s])))

filtered_symbols = get_active_markets()

# HAJSZÁLPONTOS INVERZ FVG STRATÉGIAI MOTOR
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol

        # 1. LÉPÉS: HTF Likviditás lekérése 1 órás (1h) ÉS 4 órás (4h) idősíkokról is!
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        # Kiválasztjuk a legmagasabb és legalacsonyabb szinteket a két idősíkról kombinálva
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        # 2. LÉPÉS: LTF (15m / 5m) idősík átvizsgálása iFVG-ért
        timeframes = ['15m', '5m']
        chosen_tf = '15m'
        df_ltf = pd.DataFrame()
        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_ifvg = False
        fvg_idx = None
        fvg_type = None

        for tf in timeframes:
            ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=tf, limit=60)
            if not ltf_ohlcv: continue
            df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
            length = len(df_ltf)

            # Végigmegyünk a gyertyákon, hogy keressünk egy korábbi FVG-t, amit az ár később átütött (Inverz FVG)
            for i in range(2, length - 5):
                # Eredetileg bika FVG (Felfelé mutató rés)
                if df_ltf['high'].iloc[i] < df_ltf['low'].iloc[i+2]:
                    o_fvg_high = float(df_ltf['low'].iloc[i+2])
                    o_fvg_low = float(df_ltf['high'].iloc[i])
                    
                    # Ellenőrizzük, hogy a HTF söprés után az ár letörte-e ezt az FVG-t testtel (Bezárás a doboz ALÁ = iFVG)
                    post_candles = df_ltf.iloc[i+3:]
                    for idx_p, candle in post_candles.iterrows():
                        if candle['high'] >= htf_high and candle['close'] < o_fvg_low:
                            fvg_high, fvg_low = o_fvg_high, o_fvg_low
                            fvg_idx = i
                            fvg_type = "BEARISH_INVERSE"
                            found_ifvg = True
                            chosen_tf = tf
                            break
                
                # Eredetileg medve FVG (Lefelé mutató rés)
                elif df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]:
                    o_fvg_high = float(df_ltf['low'].iloc[i])
                    o_fvg_low = float(df_ltf['high'].iloc[i+2])
                    
                    # Ellenőrizzük, hogy a HTF söpörte a lenti likviditást, majd az ár átütötte felfelé (Bezárás a doboz FÖLÉ = iFVG)
                    post_candles = df_ltf.iloc[i+3:]
                    for idx_p, candle in post_candles.iterrows():
                        if candle['low'] <= htf_low and candle['close'] > o_fvg_high:
                            fvg_high, fvg_low = o_fvg_high, o_fvg_low
                            fvg_idx = i
                            fvg_type = "BULLISH_INVERSE"
                            found_ifvg = True
                            chosen_tf = tf
                            break
                if found_ifvg: break
            if found_ifvg: break

        if df_ltf.empty or not found_ifvg: return None

        current_price = float(df_ltf['close'].iloc[-1])
        fvg_mid = (fvg_high + fvg_low) / 2.0

        trade_signal = "VÁRAKOZÁS"
        entry_price = fvg_mid
        sl = htf_high if fvg_type == "BEARISH_INVERSE" else htf_low
        tp = entry_price - (abs(entry_price - sl) * 3.5) if fvg_type == "BEARISH_INVERSE" else entry_price + (abs(entry_price - sl) * 3.5)

        # 3. LÉPÉS: PONTOS VISSZATESZT ÉS IRÁNYBA MOZDULÁS ELLENŐRZÉSE (A jelzés leadásához)
        # Megnézzük a legfrissebb gyertyákat az iFVG kialakulása után
        retest_df = df_ltf.iloc[fvg_idx+4:]
        if not retest_df.empty:
            if fvg_type == "BEARISH_INVERSE":
                # Alulról visszatesztelte a lila CE vonalat, és azóta lefelé mozdult el
                if retest_df['high'].max() >= (fvg_mid * 0.998) and current_price < fvg_mid:
                    trade_signal = "SHORT / SELL"
            elif fvg_type == "BULLISH_INVERSE":
                # Felülről visszatesztelte a lila CE vonalat, és azóta felfelé mozdult el
                if retest_df['low'].min() <= (fvg_mid * 1.002) and current_price > fvg_mid:
                    trade_signal = "LONG / BUY"

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": chosen_tf, "fvg_idx": fvg_idx
        }
    except:
        return None

# --- AUTOMATA FOLYAMATOS MEGJELENÍTŐ RENDSZER ---
st.subheader("🕵️‍♂️ Élő Kétirányú Piacszkenner (Minden Adat Egymás Alatt)")

# ÚJ FRISSÍTÉS: A csúszka maximumát felemeltem 250-re, hogy az összes párt át tudd nézni!
scan_depth = st.slider("Átvizsgálandó top aktív párok száma:", min_value=10, max_value=250, value=60, step=10)

active_signals = []
scan_placeholder = st.empty()

target_pairs = filtered_symbols[:scan_depth]
for pair in target_pairs:
    scan_placeholder.text(f"Piac pásztázása... Ellenőrzés: {pair}")
    res = analyze_pair(pair)
    if res and "VÁRAKOZÁS" not in res["trade_signal"]:
        active_signals.append((pair, res))
    time.sleep(0.02) # Gyorsított mintavétel a sok párhoz

scan_placeholder.empty()

# Kirajzolási fázis egymás alá
if active_signals:
    for idx, (pair, res) in enumerate(active_signals):
        df_ltf = res["df_ltf"]
        length = len(df_ltf)
        clean_name = pair.split(':')[0]

        # A) FEJLÉC KÁRTYA
        st.markdown(f"""
            <div class="signal-header">
                <h3 style='margin:0; font-size:16px;'>🔥 {clean_name} &nbsp;|&nbsp; Idősík: {res['chosen_tf']} &nbsp;|&nbsp; Irány: {res['trade_signal']}</h3>
            </div>
        """, unsafe_allow_html=True)

        # B) TRADINGVIEW STÍLUSÚ GRAFIKON (Idővonalhoz kötött, nem torzítja az Y-tengelyt)
        fig = go.Figure()
        
        fig.add_trace(go.Candlestick(
            x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'],
            increasing_line_color='#089981', decreasing_line_color='#f23645',
            increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Ár"
        ))
        
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*length, name="HTF High Liq", line=dict(color='#26a69a', width=1.5)))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*length, name="HTF Low Liq", line=dict(color='#ef5350', width=1.5)))
        
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*length, name="Belépő", line=dict(color='#29b6f6', width=2)))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*length, name="SL", line=dict(color='#ff1744', width=1.5, dash='dash')))
        fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp"]]*length, name="TP", line=dict(color='#00e676', width=1.5)))

        # A sárga iFVG doboz és a lila szaggatott vonal pontos berajzolása
