# Kesz_Alkalmazas
import streamlit as st

st.set_page_config(page_title="ICT Crypto Bot", layout="wide", initial_sidebar_state="collapsed")
st.title("🏹 ICT Liquidity & Leverage Assistant")

st.markdown("### 💰 Kockázat & Tőke Pozíciótervező")
st.write("Számold ki a pontos pozícióméretedet és áttételedet a trade megnyitása előtt:")

col_toke, col_kock, col_sl = st.columns(3)
with col_toke:
    total_balance = st.number_input("Teljes Kereskedési Tőkéd ($):", min_value=10, value=1000, step=50)
with col_kock:
    risk_percent = st.slider("Megengedett kockázat (%):", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
with col_sl:
    sl_percent = st.number_input("Tervezett Stop Loss távolság (%-ban):", min_value=0.1, max_value=20.0, value=2.0, step=0.5)

# Matematikai kalkulátor futtatása
max_loss_usd = total_balance * (risk_percent / 100)
sl_decimal = sl_percent / 100
position_size_usd = max_loss_usd / sl_decimal

# Biztonságos áttétel meghatározása (max 50x)
recommended_leverage = int(0.8 / sl_decimal) if sl_decimal > 0 else 1
recommended_leverage = max(1, min(recommended_leverage, 50))
required_margin = position_size_usd / recommended_leverage

# Eredmények doboz
cc1, cc2, cc3 = st.columns(3)
cc1.metric("Kockáztatott összeg", f"${max_loss_usd:,.2f}")
cc2.metric("Javasolt Tőkeáttétel", f"{recommended_leverage}x")
cc3.metric("Megnyitandó méret", f"${position_size_usd:,.2f} (Margin: ${required_margin:,.2f})")

st.markdown("---")
st.markdown("### 📊 Élő TradingView Piacfigyelő & Bitget Szűrő")
st.write("A telefonod böngészője blokkolja a beágyazott táblázatokat. Kattints az alábbi gombra a teljes, élő, szűrt TradingView Kripto Screener megnyitásához, ahol azonnal látod a Bitget párokat és az indikátorokat:")

# Biztonságos, közvetlen link gomb a TradingView hivatalos Kripto Szűrőjéhez
st.link_button("📈 Élő TradingView Kripto Szűrő Megnyitása", "https://tradingview.com", use_container_width=True)

 
             
    
    


            
        
                
        
        
