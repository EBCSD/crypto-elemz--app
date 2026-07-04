def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        
        # 1. HTF Likviditás (változatlan)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        if not htf_1h: return None
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = float(df_1h['high'].iloc[:-2].max())
        htf_low = float(df_1h['low'].iloc[:-2].min())

        # 2. LTF Drill-Down (Itt a változtatás: 15m helyett 5m-et használunk a sebességért)
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe='5m', limit=60)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        df_ltf['rsi'] = calculate_rsi(df_ltf['close'])
        
        current_price = float(df_ltf['close'].iloc[-1])
        current_rsi = float(df_ltf['rsi'].iloc[-1])
        
        # 3. Érvényesítési logika
        # Csak akkor keressünk FVG-t, ha az ár közel van a HTF szintekhez
        is_near_high = current_price >= (htf_high * 0.998)
        is_near_low = current_price <= (htf_low * 1.002)
        
        if not (is_near_high or is_near_low): return None

        # ... (Itt tartsd meg a korábbi FVG kereső ciklusodat az 'i'-vel) ...
        # A logika ugyanaz marad, de mivel 5 perces az df_ltf, 
        # az FVG dobozod sokkal közelebb lesz az "igazi" fordulóponthoz.

        # ... (A return értékednél írd át a chosen_tf-et "5m"-re) ...
        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, 
            "current_price": current_price, "fvg_high": fvg_high, 
            "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, 
            "chosen_tf": "5m", "fvg_idx": fvg_idx, # <--- Itt 5m-re állítottuk
            "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except Exception as e:
        return None
