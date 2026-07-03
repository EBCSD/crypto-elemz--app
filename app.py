       import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from tradingview_screener import Query, col

# Mobilbarát, gyári stabil konfiguráció
st.set_page_config(page_title="ICT Crypto Bot", layout="wide", initial_sidebar_state="collapsed")

st.title("🏹 ICT Liquidity & Leverage Assistant")

# Oldalsáv a beállításoknak
st.sidebar.header("⚙️ Beállítások")
exchange = st.sidebar.selectbox("Tőzsde:", ["BITGET", "BINANCE", "BYBIT", "OKX"])
market_type = st.sidebar.radio("Piac:", ["Futures", "Spot"])

st.markdown("### 💰 Kockázat & Tőke Beállítások")
col_toke, col_kock = st.columns(2)
with col_toke:
    total_balance = st.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000, step=50)
with col_kock:
    risk_percent = st.slider("Megengedett kockázat tradenként (%):", min_value=0.5, max_value=5.0, value=1.0, step=0.5)

# Adatlekérés a TradingView API-ból
@st.cache_data(ttl=30)
def get_crypto_data(exch):
    q = (Query()
         .set_markets('crypto')
         .where(col('exchange') == exch)
         .select('name', 'close', 'volume', 'high', 'low', 'high|1h', 'low|1h', 'EMA20', 'ATR', 'RSI'))
    return q.get_results()

try:
    df = get_crypto_data(exchange)
    
    if market_type == "Futures":
        df = df[df['name'].str.contains('PERP|USDT|USD!', case=False, na=False)]
    else:
        df = df[~df['name'].str.contains('PERP', case=False, na=False)]
    
    pairs = df['name'].tolist()
    selected_pair = st.selectbox("🎯 Válassz kriptopárt elemzésre:", pairs if pairs else ["Nincs elérhető adat"])

    if selected_pair and pairs:
        coin = df[df['name'] == selected_pair].iloc
        
        price = float(coin['close'])
        ltf_high, ltf_low = float(coin['high']), float(coin['low'])
        htf_high, htf_low = float(coin['high|1h']), float(coin['low|1h'])
        atr = float(coin['ATR']) if pd.notna(coin['ATR']) else (price * 0.01)
        ema20 = float(coin['EMA20']) if pd.notna(coin['EMA20']) else price
        
        # Stratégia ellenőrzése
        trade_signal = "VÁRAKOZÁS"
        if ltf_low <= htf_low and price > ema20:
            trade_signal = "LONG / BUY"
            entry = price
            sl = htf_low - (0.2 * atr)
            tp = htf_high
        elif ltf_high >= htf_high and price < ema20:
            trade_signal = "SHORT / SELL"
            entry = price
            sl = htf_high + (0.2 * atr)
            tp = ltf_low

        # Kártyák megjelenítése
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktuális Ár", f"${price:,.4f}")
        c2.metric("Jelzés", trade_signal)
        c3.metric("Kockáztatott összeg", f"${(total_balance * (risk_percent/100)):,.2f}")

        if trade_signal != "VÁRAKOZÁS":
            st.markdown("### ⚡ Számított Pozíció és Optimális Áttétel")
            
            sl_distance_percent = abs(entry - sl) / entry
            max_loss_usd = total_balance * (risk_percent / 100)
            position_size_usd = max_loss_usd / sl_distance_percent
            
            recommended_leverage = int(0.8 / sl_distance_percent)
            recommended_leverage = max(1, min(recommended_leverage, 50))
            required_margin = position_size_usd / recommended_leverage

            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.success(f"**Belépő:** ${entry:,.4f}\n\n**Stop Loss:** ${sl:,.4f}\n\n**Take Profit:** ${tp:,.4f}")
            with cc2:
                st.warning(f"**Javasolt Tőkeáttétel:** {recommended_leverage}x\n\n*(Biztonságos méretezés)*")
            with cc3:
                st.info(f"**Tőzsdén megnyitandó méret:** ${position_size_usd:,.2f}\n\n**Szükséges tőke (Margin):** ${required_margin:,.2f}")
                
            rrr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
            st.metric("Kockázat/Nyereség arány (RRR)", f"1 : {rrr:.2f}")
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[1, 2, 3], y=[entry, entry, entry], name="Belépő", line=dict(color='cyan', width=2)))
            fig.add_trace(go.Scatter(x=[1, 2, 3], y=[sl, sl, sl], name="Stop Loss", line=dict(color='red', dash='dash')))
            fig.add_trace(go.Scatter(x=[1, 2, 3], y=[tp, tp, tp], name="Take Profit", line=dict(color='green', width=2)))
            fig.update_layout(title="Pozíciós Szintek", template="plotly_dark", height=250)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("⏳ Jelenleg nincs aktív intézményi sweep a páron. Várunk a likviditás kiszedésére.")

except Exception as e:
    st.error(f"Adatlekérési hiba történt: {e}")
     
