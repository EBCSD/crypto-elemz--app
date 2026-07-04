import streamlit as st
import pandas as pd
import ccxt
import plotly.graph_objects as go
import time
import numpy as np

# --- RSI INDIKÁTOR SZÁMÍTÁSA ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

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

# --- ÚJ STRATÉGIA MOTOR: HTF SWEEP + PONTOS iFVG RETEST + RSI ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        
        # 1. HTF Likviditás
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        # 2. LTF Elemzés
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='15m', limit=50)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        df_ltf['rsi'] = calculate_rsi(df_ltf['close'])
        
        length = len(df_ltf)
        current_price = float(df_ltf['close'].iloc[-1])
        current_rsi = float(df_ltf['rsi'].iloc[-1])

        ltf_recent_high = df_ltf['high'].max()
        ltf_recent_low = df_ltf['low'].min()
        swept_htf_high = ltf_recent_high >= (htf_high * 0.999)
        swept_htf_low = ltf_recent_low <= (htf_low * 1.001)

        fvg_candidates = []

        # 3. AZ ÖSSZES iFVG VISSZATESZT KERESÉSE
        # Sokkal szélesebb spektrumban keresünk, egészen az utolsó előtti gyertyáig
        for i in range(max(0, length - 40), length - 2): 
            
            # --- BEARISH INVERSE FVG SETUP (SHORT) ---
            if swept_htf_high and df_ltf['low'].iloc[i+2] > df_ltf['high'].iloc[i]:
                fvg_bot = float(df_ltf['high'].iloc[i])
                fvg_top = float(df_ltf['low'].iloc[i+2])
                
                # Zárt az ár az FVG alatt?
                if any(df_ltf['close'].iloc[i+3:] < fvg_bot):
                    # Visszateszt
                    if fvg_bot <= current_price <= fvg_top:
                        if current_rsi < 55:
                            fvg_candidates.append({
                                "type": "SHORT / SELL", "fvg_high": fvg_top, "fvg_low": fvg_bot, "idx": i
                            })

            # --- BULLISH INVERSE FVG SETUP (LONG) ---
            elif swept_htf_low and df_ltf['high'].iloc[i+2] < df_ltf['low'].iloc[i]:
                fvg_top = float(df_ltf['low'].iloc[i])
                fvg_bot = float(df_ltf['high'].iloc[i+2])
                
                # Zárt az ár az FVG felett?
                if any(df_ltf['close'].iloc[i+3:] > fvg_top):
                    # Visszateszt
                    if fvg_bot <= current_price <= fvg_top:
                        if current_rsi > 45:
                            fvg_candidates.append({
                                "type": "LONG / BUY", "fvg_high": fvg_top, "fvg_low": fvg_bot, "idx": i
                            })

        # NINCS TALÁLAT
        if not fvg_candidates: return None

        # 4. A LEGJOBB iFVG KIVÁLASZTÁSA (A FORDULÓPONTHOZ LEGKÖZELEBBI!)
        short_candidates = [c for c in fvg_candidates if c["type"] == "SHORT / SELL"]
        long_candidates = [c for c in fvg_candidates if c["type"] == "LONG / BUY"]

        if short_candidates:
            # Ha SHORT, a legmagasabb iFVG kell (amelyik a csúcson alakult ki)
            best_fvg = max(short_candidates, key=lambda x: x["fvg_high"])
        elif long_candidates:
            # Ha LONG, a legalacsonyabb iFVG kell (amelyik a völgyben alakult ki)
            best_fvg = min(long_candidates, key=lambda x: x["fvg_low"])
        else:
            return None

        fvg_high = best_fvg["fvg_high"]
        fvg_low = best_fvg["fvg_low"]
        fvg_idx = best_fvg["idx"]
        trade_signal = best_fvg["type"]

        fvg_mid = (fvg_high + fvg_low) / 2.0
        entry_price = current_price
        
        # 5. Kockázatkezelés (Szoros SL az iFVG szélén, 1:3 RR)
        if trade_signal == "SHORT / SELL":
            sl = fvg_high * 1.002
            tp = entry_price - (abs(entry_price - sl) * 3.0)
        else:
            sl = fvg_low * 0.998
            tp = entry_price + (abs(entry_price - sl) * 3.0)

        risk_dist = abs(entry_price - sl)
        reward_dist = abs(tp - entry_price)
        rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0

        sl_percent = (risk_dist / entry_price) if entry_price > 0 else 0.01
        calculated_leverage = int((risk_percent / 100.0) / sl_percent) if sl_percent > 0 else 1
        leverage_suggestion = max(1, min(calculated_leverage, 10))

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": "15m", "fvg_idx": fvg_idx,
            "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except Exception as e:
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

    # Pontosan rajzolt FVG doboz
    if res["fvg_high"] > 0 and res["fvg_idx"] is not None:
        s_idx = int(res["fvg_idx"])
        e_idx = int(min(s_idx + 25, length - 1))
        bx = [df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[e_idx], df_ltf['time'].iloc[e_idx], df_ltf['time'].iloc[s_idx], df_ltf['time'].iloc[s_idx]]
        by = [res["fvg_high"], res["fvg_high"], res["fvg_low"], res["fvg_low"], res["fvg_high"]]
        # Kiemelt színnel, hogy egyértelmű legyen, hol van
        fig.add_trace(go.Scatter(x=bx, y=by, fill="toself", fillcolor="rgba(255, 214, 0, 0.15)", line=dict(color='#ffd600', width=1.5), showlegend=False))

    y_pad = (df_ltf['high'].max() - df_ltf['low'].min()) * 0.15
    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=400, paper_bgcolor='#131722', plot_bgcolor='#131722', margin=dict(l=10, r=55, t=10, b=10), showlegend=False, yaxis=dict(side="right", range=[df_ltf['low'].min() - y_pad, max(df_ltf['high'].max(), res["htf_high"]) + y_pad], gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)), xaxis=dict(gridcolor="#2a2e39", zeroline=False, tickfont=dict(color="#848e9c", size=10)))
    
    st.plotly_chart(fig, use_container_width=True, key=f"chart_render_{unique_id}")
    st.write(f"🟢 **BESZÁLÓ ÁR:** ${res['entry_price']:.5f} | 🔴 **STOP LOSS ÁR (SL):** ${res['sl']:.5f} | 🔵 **TAKE PROFIT ÁR (TP):** ${res['tp']:.5f}")
    st.write(f"⚙️ **JAVASOLT TŐKEÁTTÉTEL:** {res['leverage']}x (Max 10x) | 📊 **R:R ARÁNY / AKTUÁLIS ÁR:** 1:{res['rr']} | ${res['current_price']:.5f}")
    st.markdown("---")

# --- FŐ VEZÉRLŐ LOGIKA ---
if run_scanner:
    st.subheader("🕵️‍♂️ ALGO ICT PRO Élő Automata Piacszkenner")
    scan_placeholder = st.empty()
    for idx, pair in enumerate(filtered_symbols):
        display_name = str(pair).split(':')[0] if ':' in str(pair) else str(pair)
        scan_placeholder.text(f"Piac átfésülése ({idx+1}/{len(filtered_symbols)}): {display_name} - Likviditás / iFVG keresése...")
        res = analyze_pair(pair)
        if res: 
            render_signal_block(display_name, res, f"scan_mode_{idx}")
        time.sleep(0.01)
    scan_placeholder.empty()

if not run_scanner:
    st.subheader("🎯 Kézi Elemzés és Egyedi Keresés")
    lumia_index = filtered_symbols.index("LUMIA/USDT") if "LUMIA/USDT" in filtered_symbols else 0
    selected_pair = st.selectbox("Válassz ki egy konkrét párt az azonnali elemzéshez:", filtered_symbols, index=lumia_index)
    manual_res = analyze_pair(selected_pair)
    if manual_res: 
        render_signal_block(selected_pair, manual_res, "manual_mode")
    if not manual_res: 
        st.info(f"A(z) {selected_pair} páron jelenleg nincs HTF Sweep -> Pontos iFVG Visszateszt setup.")
