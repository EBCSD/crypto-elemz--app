# 1. Optimalizáljuk az adatgyűjtést (cache-elés)
@st.cache_data(ttl=60) # A cache 60 másodpercig tárolja az adatot
def get_data_fast(symbol, timeframe):
    try:
        return exch.fetch_ohlcv(symbol, timeframe=timeframe, limit=20)
    except:
        return None

# 2. Egyszerűsítsd a szkennert (ne akarjon 100 párat egyszerre kiszámolni)
if run_scanner:
    st.subheader("🕵️‍♂️ Piacfigyelő aktív...")
    # Csak az első 20 legfontosabb párt nézze, ne az összeset
    for pair in filtered_symbols[:20]: 
        res = analyze_pair(pair)
        if res:
            render_signal_block(pair, res, pair)
        # Ha nem talál, ne írjon ki semmit, csak lépjen tovább
