import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time

# 1. ALAPBEÁLLÍTÁSOK ÉS STRUKTÚRA
st.set_page_config(page_title="ALGO ICT PRO", layout="wide", initial_sidebar_state="collapsed")
st.title("⚡ ALGO ICT PRO V2")
st.caption("Advanced Institutional Liquidity Terminal | Powered by Bitget")

st.sidebar.header("🎛️ Vezérlőpult")
exchange_id = st.sidebar.selectbox("1. Válassz Tőzsdét:", ["bitget", "binance", "bybit", "okx"])
market_type = st.sidebar.radio("2. Kereskedési mód:", ["Futures", "Spot"])

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kockázatkezelés")
total_balance = st.sidebar.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000)
risk_percent = st.sidebar.slider("Kockázat (%):", min_value=0.5, max_value=100.0, value=5.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Keresési Mód")
run_scanner = st.sidebar.checkbox("Automata Piacszkenner Indítása", value=True)

# API Inicializálás
exch = getattr(ccxt, exchange_id)({
    'enableRateLimit': True,
    'options': {'defaultType': 'future' if market_type == "Futures" else 'spot'}
})
exch.load_markets()

@st.cache_data(ttl=120)
def get_active_markets():
    try:
        tickers = exch.fetch_tickers()
        pairs = []
        for sym, t in tickers.items():
            if 'USDT' in sym and '/' in sym:
                pairs.append(sym)
        return sorted(list(set(pairs)))
    except:
        return sorted(list(set([s for s in exch.markets.keys() if 'USDT' in s])))

filtered_symbols = get_active_markets()

# VALÓDI LUMIA-STÍLUSÚ INVERZ FVG STRATÉGIAI MOTOR
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':') if ':' in pair_symbol else pair_symbol
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='15m', limit=45)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        length = len(df_ltf)

        fvg_high, fvg_low, fvg_mid = 0.0, 0.0, 0.0
        found_ifvg = False
        fvg_idx = 0
        fvg_type = "NONE"

        # SZIGORÍTÁS A KÉPED ALAPJÁN: iFVG szűrés megfelelő sorrendben
        for i in range(2, length - 5):
            # 1. SHORT MINTA (Mint a LUMIA képeden): Eredetileg medve FVG, amit ÁTÜTÖTTEK felfelé, majd jött a felső söprés
            if df_ltf['low'].iloc[i] > df_ltf['high'].iloc[i+2]:
                o_high = float(df_ltf['low'].iloc[i])
                o_low = float(df_ltf['high'].iloc[i+2])
                
                post_df = df_ltf.iloc[i+3:]
                was_inversed = post_df['close'].max() > o_high # Testtel átütötte felfelé (Inverzió)
                was_swept = post_df['high'].max() >= htf_high # Ezután kisöpörte a HTF likviditást fentről
                
                if was_inversed and was_swept:
                    fvg_high, fvg_low = o_high, o_low
                    fvg_idx = i
                    fvg_type = "BEARISH_INVERSE" # Ebből lesz a short visszateszt
                    found_ifvg = True
                    break
                    
            # 2. LONG MINTA (A short tökéletes ellentéte): Eredetileg bika FVG, amit LETÖRTEK, majd jött az alsó söpörgetés
            elif df_ltf['high'].iloc[i] < df_ltf['low'].iloc[i+2]:
                o_high = float(df_ltf['low'].iloc[i+2])
                o_low = float(df_ltf['high'].iloc[i])
                
                post_df = df_ltf.iloc[i+3:]
                was_inversed = post_df['close'].min() < o_low # Testtel letörte lefelé (Inverzió)
                was_swept = post_df['low'].min() <= htf_low # Ezután kisöpörte a lenti HTF likviditást
                
                if was_inversed and was_swept:
                    fvg_high, fvg_low = o_high, o_low
                    fvg_idx = i
                    fvg_type = "BULLISH_INVERSE" # Ebből lesz a long visszateszt
                    found_ifvg = True
                    break

        if not found_ifvg: return None
        
        current_price = float(df_ltf['close'].iloc[-1])
        fvg_mid = (fvg_high + fvg_low) / 2.0
        entry_price = fvg_mid
        
        # FIXÁLT PONTOS SZINTEK: Shortnál az SL a HTF csúcs, a TP lenn van. Longnál fordítva.
        if fvg_type == "BEARISH_INVERSE":
            sl = htf_high
            tp = entry_price - (abs(entry_price - sl) * 3.5)
        else:
            sl = htf_low
            tp = entry_price + (abs(entry_price - sl) * 3.5)

        # Szigorú minimum 1:3 RR szűrés
        risk_dist = abs(entry_price - sl)
        reward_dist = abs(tp - entry_price)
        rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
        if rr_ratio < 3.0: return None

        # Tőkeáttétel javaslat (Max 10x)
        sl_percent = (risk_dist / entry_price) if entry_price > 0 else 0.01
        calculated_leverage = int((risk_percent / 100.0) / sl_percent) if sl_percent > 0 else 1
        leverage_suggestion = max(1, min(calculated_leverage, 10))

        # ÉLES JELZÉS: Csak akkor jelez, ha az aktuális ár éppen a sárga doboz határain belül/CE vonalon van!
        trade_signal = "VÁRAKOZÁS"
        if fvg_type == "BEARISH_INVERSE" and current_price >= (fvg_low * 0.998) and current_price <= (fvg_high * 1.002):
            trade_signal = "SHORT / SELL"
        elif fvg_type == "BULLISH_INVERSE" and current_price <= (fvg_high * 1.002) and current_price >= (fvg_low * 0.998):
            trade_signal = "LONG / BUY"

        if trade_signal == "VÁRAKOZÁS": return None

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": "15m", "fvg_idx": fvg_idx,
            "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except:
        return None

# KÉPERNYŐ RAJZOLÓ MODUL
def render_signal_block(display_name, res, unique_id):
    df_ltf = res["df_ltf"]
    length = len(df_ltf)
    st.subheader(f"🔥 {display_name} | Idősík: {res['chosen_tf']} | Irány: {res['trade_signal']}")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_ltf['time'], open=df_ltf['open'], high=df_ltf['high'], low=df_ltf['low'], close=df_ltf['close'], increasing_line_color='#089981', decreasing_line_color='#f23645', increasing_fillcolor='#089981', decreasing_fillcolor='#f23645', name="Ár"))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_high"]]*length, name="HTF High", line=dict(color='#26a69a', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["htf_low"]]*length, name="HTF Low", line=dict(color='#ef5350', width=1.5)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["entry_price"]]*length, name="Belépő", line=dict(color='#29b6f6', width=2)))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["sl"]]*length, name="SL", line=dict(color='#ff1744', width=1.5, dash='dash')))
    fig.add_trace(go.Scatter(x=df_ltf['time'], y=[res["tp"]]*length, name="TP", line=dict(color='#00e676', width=1.5)))

    if res["fvg_high"] > 0 and res["fvg_idx"] is not None:
        s_idx = int(res["fvg_idx"])
        e_idx = length - 1 # Kivisszük a legutolsó gyertyáig, pont mint a TradingView dobozod!
        bx = [df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[e_idx], df_ltf['time'].iloc[e_idx], df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[s_idx]]
        by = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
        fig.add_trace(go.Scatter(x=bx, y=by, fill="toself", fillcolor="rgba(255, 214, 0, 0.04)", line=dict(color='#ffd600', width=1.5), showlegend=False))
        fig.add_trace(go.Scatter(x=[df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[e_idx]], y=[res["fvg_mid"], res["fvg_mid"]], line=dict(color='#e040fb', width=2, dash='dash'), showlegend=False))

    y_pad = (df_ltf['high'].max() - df_ltf['low'].min()) * 0.15
    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=400, paper_bgcolor='#131722', plot_bgcolor='#131722', margin=dict(l=10, r=55, t=10, b=10), showlegend=False, yaxis=dict(side="right", range=[df_ltf['low'].min() - y_pad, max(df_ltf['high'].max(), res["htf_high"]) + y_pad], gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)), xaxis=dict(gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)))
    st.plotly_chart(fig, use_container_width=True, key=f"chart_render_{unique_id}")
    st.write(f"🟢 **BESZÁLÓ ÁR (CE 50%):** ${res['entry_price']:.5f} | 🔴 **STOP LOSS ÁR (SL):** ${res['sl']:.5f} | 🔵 **TAKE PROFIT ÁR (TP):** ${res['tp']:.5f}")
    st.write(f"⚙️ **JAVASOLT TŐKEÁTTÉTEL:** {res['leverage']}x (Max 10x) | 📊 **R:R ARÁNY / AKTUÁLIS ÁR:** 1:{res['rr']} | ${res['current_price']:.5f}")
    st.markdown("---")

# --- FŐ VEZÉRLŐ LOGIKA ---
if run_scanner:
    st.subheader("🕵️‍♂️ ALGO ICT PRO Élő Automata Piacszkenner")
    scan_placeholder = st.empty()
    for idx, pair in enumerate(filtered_symbols):
        display_name = str(pair).split(':') if ':' in str(pair) else str(pair)
        scan_placeholder.text(f"Piac átfésülése ({idx+1}/{len(filtered_symbols)}): {display_name}")
        res = analyze_pair(pair)
        if res: 
