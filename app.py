# --- MÓDOSÍTOTT STRATÉGIA MOTOR ---
def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        
        # 1. HTF Likviditás (Marad 1h/4h)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        # 2. LTF Elemzés - DINAMIKUS VÁLTÁS
        # Ha az ár a zónában van, 1 percesre váltunk a pontosságért
        current_price_probe = exch.fetch_ticker(clean_symbol)['last']
        chosen_tf = '1m' if (current_price_probe >= htf_high * 0.998 or current_price_probe <= htf_low * 1.002) else '15m'
        
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=chosen_tf, limit=80)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        df_ltf['rsi'] = calculate_rsi(df_ltf['close'])
        
        length = len(df_ltf)
        current_price = float(df_ltf['close'].iloc[-1])
        current_rsi = float(df_ltf['rsi'].iloc[-1])

        # A többi logika (FVG keresés, SL/TP számítás) változatlan marad...
        # (Ide másold be a kódod eredeti 3., 4., és 5. pontját)
        
        # ... a végén pedig a return-nél frissítsd a chosen_tf-et:
        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": chosen_tf, "fvg_idx": fvg_idx,
            "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except Exception:
        return None
