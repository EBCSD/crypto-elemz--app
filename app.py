import streamlit as st
import pandas as pd
import ccxt

# 1. INITIALIZÁLÁS
@st.cache_resource
def get_exchange():
    return ccxt.bitget({'enableRateLimit': True})

exch = get_exchange()

# 2. HELPER FÜGGVÉNYEK
def get_data(symbol, timeframe, limit=50):
    try:
        ohlcv = exch.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    except:
        return None

def find_ifvg_in_df(df, swept_high, swept_low):
    # iFVG logika: Itt keressük a gap-et
    for i in range(len(df) - 10, len(df) - 2):
        if swept_high and df['low'].iloc[i+2] > df['high'].iloc[i]:
            return {"fvg_high": df['low'].iloc[i+2], "fvg_low": df['high'].iloc[i], "type": "SHORT"}
        if swept_low and df['high'].iloc[i+2] < df['low'].iloc[i]:
            return {"fvg_high": df['low'].iloc[i], "fvg_low": df['high'].iloc[i+2], "type": "LONG"}
    return None

# 3. FŐ ANALYZER (Itt volt a hiba, hogy a swept_high/low nem volt definiálva)
def analyze_advanced(symbol):
    df_1h = get_data(symbol, '1h', 20)
    if df_1h is None: return None
    
    # HTF Szintek definiálása
    htf_high = df_1h['high'].max()
    htf_low = df_1h['low'].min()
    current_price = df_1h['close'].iloc[-1]
    
    swept_high = current_price >= htf_high
    swept_low = current_price <= htf_low
    
    # LTF "Deep Dive"
    df_ltf = get_data(symbol, '5m', 30)
    if df_ltf is None: return None
    
    fvg = find_ifvg_in_df(df_ltf, swept_high, swept_low)
    
    if fvg:
        return fvg
    return None

# 4. UI MEGJELENÍTÉS
st.title("⚡ ALGO ICT PRO - ANALYZER")
run_scanner = st.sidebar.checkbox("Szkennelés")
symbols = ['BTC/USDT', 'ETH/USDT', 'LUMIA/USDT', '1INCH/USDT', 'ASTR/USDT']

if run_scanner:
    for sym in symbols:
        result = analyze_advanced(sym)
        if result:
            st.success(f"Találat: {sym} | Irány: {result['type']}")
            st.write(f"Zóna: {result['fvg_low']} - {result['fvg_high']}")
        else:
            st.text(f"{sym}: Nincs érvényes setup.")
