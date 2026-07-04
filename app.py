def check_confluence(df, idx):
    # 1. RSI Szűrő: Short esetén 60 felett, Long esetén 40 alatt legyen (fordulás gyanúja)
    rsi = df['rsi'].iloc[idx]
    
    # 2. Volumen Szűrő: A fordulós gyertya volumene legyen átlagon felüli (nagy pénz mozgott)
    avg_vol = df['volume'].rolling(20).mean().iloc[idx]
    volume_confirm = df['volume'].iloc[idx] > (avg_vol * 1.5)
    
    return rsi, volume_confirm

# Az analyze_pair függvényen belül:
# ... (miután megtaláltad a best_fvg-t)
    
    rsi, vol_ok = check_confluence(df_ltf, best_fvg["idx"])
    
    # SZIGORÚ SZŰRŐ: Csak akkor adunk jelet, ha az indikátorok is megerősítik!
    is_short = (trade_signal == "SHORT / SELL" and rsi > 55 and vol_ok)
    is_long = (trade_signal == "LONG / BUY" and rsi < 45 and vol_ok)
    
    if is_short or is_long:
        return # Ez a valid setup!
    else:
        return None # EZ A TRIMMELÉS: Ha nincs indikátor megerősítés, nem szemeteli tele a képernyőt!
