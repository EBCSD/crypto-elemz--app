def analyze_pair(pair_symbol):
    try:
        clean_symbol = pair_symbol.split(':')[0] if ':' in pair_symbol else pair_symbol
        
        # 1. HTF Likviditás (Változatlan)
        htf_1h = exch.fetch_ohlcv(clean_symbol, timeframe='1h', limit=48)
        htf_4h = exch.fetch_ohlcv(clean_symbol, timeframe='4h', limit=24)
        if not htf_1h or not htf_4h: return None
        
        df_1h = pd.DataFrame(htf_1h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(htf_4h, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        htf_high = max(float(df_1h['high'].iloc[:-2].max()), float(df_4h['high'].iloc[:-2].max()))
        htf_low = min(float(df_1h['low'].iloc[:-2].min()), float(df_4h['low'].iloc[:-2].min()))

        # --- PRECISION MODE LOGIKA (EZ AZ EGYETLEN ÚJ RÉSZ) ---
        last_ticker = exch.fetch_ticker(clean_symbol)
        current_price = last_ticker['last']
        
        # Ha az ár a HTF High/Low 0.2%-os körzetében van, precíziós módba kapcsolunk
        chosen_tf = '1m' if (current_price >= htf_high * 0.998 or current_price <= htf_low * 1.002) else '15m'
        # --------------------------------------------------------

        # 2. LTF Elemzés (A chosen_tf változót használjuk)
        ltf_ohlcv = exch.fetch_ohlcv(clean_symbol, timeframe=chosen_tf, limit=60)
        if not ltf_ohlcv: return None
        df_ltf = pd.DataFrame(ltf_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df_ltf['time'] = pd.to_datetime(df_ltf['time'], unit='ms')
        df_ltf['rsi'] = calculate_rsi(df_ltf['close'])
        
        length = len(df_ltf)
        current_price = float(df_ltf['close'].iloc[-1])
        current_rsi = float(df_ltf['rsi'].iloc[-1])

        # A további kód (3, 4, 5. pont) maradhat teljesen változatlanul az eredeti kódodban, 
        # csak győződj meg róla, hogy a 'chosen_tf' értéket átadod a visszatérési értékben:
        
        # ... (az eredeti kódod 3, 4, 5. pontja maradjon itt) ...

        return {
            "df_ltf": df_ltf, "htf_high": htf_high, "htf_low": htf_low, "current_price": current_price,
            "fvg_high": fvg_high, "fvg_low": fvg_low, "fvg_mid": fvg_mid, "entry_price": entry_price,
            "sl": sl, "tp": tp, "trade_signal": trade_signal, "chosen_tf": chosen_tf, "fvg_idx": fvg_idx, # <--- Itt a chosen_tf
            "leverage": leverage_suggestion, "rr": round(rr_ratio, 1)
        }
    except Exception as e:
        return None
