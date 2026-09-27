import pandas as pd
import numpy as np
import os
import requests

# --- Telegram Bot Configuration (Using GitHub Secrets) ---
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_alert(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram Error: BOT_TOKEN or CHAT_ID environment variable is missing.")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    if len(message) > 4000:
        messages = [message[i:i+4000] for i in range(0, len(message), 4000)]
    else:
        messages = [message]
        
    for msg in messages:
        payload = {
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print("Telegram message sent successfully.")
            else:
                print(f"Telegram API Error ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"Telegram Connection Error: {e}")

def fetch_binance_klines(symbol, timeframe='1h', limit=150):
    clean_symbol = symbol.replace('/', '')
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={clean_symbol}&interval={timeframe}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, list):
            return None
        
        ohlcv = []
        for row in data:
            ohlcv.append([
                int(row[0]),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5])
            ])
        return ohlcv
    except Exception as e:
        print(f"API Error for {symbol} [{timeframe}]: {e}")
        return None

def find_order_blocks(df):
    obs = []
    for i in range(2, len(df) - 2):
        o = df['open'].iloc[i]
        c = df['close'].iloc[i]
        h = df['high'].iloc[i]
        l = df['low'].iloc[i]
        
        # Bullish OB formed by strong imbalance move
        if c < o and df['close'].iloc[i+1] > df['high'].iloc[i]:
            obs.append({'type': 'Bullish OB 🟢', 'top': h, 'bottom': l})
        # Bearish OB formed by strong imbalance move
        elif c > o and df['close'].iloc[i+1] < df['low'].iloc[i]:
            obs.append({'type': 'Bearish OB 🔴', 'top': h, 'bottom': l})
    return obs

def run_screener():
    symbols = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 
        'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'MATIC/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 'ETC/USDT', 
        'XLM/USDT', 'BCH/USDT', 'APT/USDT', 'ICP/USDT', 'FIL/USDT', 'LDO/USDT', 'ARB/USDT', 
        'OP/USDT', 'INJ/USDT', 'SUI/USDT', 'SEI/USDT', 'TIA/USDT', 'RENDER/USDT', 'FET/USDT', 'AGIX/USDT', 
        'GRT/USDT', 'MKR/USDT', 'AAVE/USDT', 'SNX/USDT', 'CRV/USDT', 'COMP/USDT', 'DYDX/USDT', 
        'GMX/USDT', 'PENDLE/USDT', 'STX/USDT', 'IMX/USDT', 'MANA/USDT', 'SAND/USDT', 'AXS/USDT', 'GALA/USDT', 
        'ENJ/USDT', 'CHZ/USDT', 'FLOW/USDT', 'KAVA/USDT', 'EOS/USDT', 'XTZ/USDT', 'THETA/USDT', 
        'EGLD/USDT', 'ROSE/USDT', 'ZIL/USDT', 'ONE/USDT', 'ALGO/USDT', 'HBAR/USDT', 'QNT/USDT', 
        'PEPE/USDT', 'SHIB/USDT', 'FLOKI/USDT', 'BONK/USDT', 'WIF/USDT', 'BOME/USDT', 'MEME/USDT', 'ORDI/USDT', 
        'SATS/USDT', 'RATS/USDT', 'JUP/USDT', 'PYTH/USDT', 'PORTAL/USDT', 'MAVIA/USDT', 'ACE/USDT', 'NFP/USDT'
    ]
    
    symbols = list(dict.fromkeys(symbols))
    timeframes = ['15m', '1h', '4h']
    
    # Store signals separately by timeframe
    tf_results = {'15m': [], '1h': [], '4h': []}

    for symbol in symbols:
        for tf in timeframes:
            try:
                ohlcv = fetch_binance_klines(symbol, timeframe=tf, limit=150)
                if ohlcv is None or len(ohlcv) < 50:
                    continue
                    
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                curr_price = df['close'].iloc[-1]
                
                obs = find_order_blocks(df)
                if not obs:
                    continue
                
                # Take the most recent valid OB
                latest_ob = obs[-1]
                top = latest_ob['top']
                bottom = latest_ob['bottom']
                ob_type = latest_ob['type']
                
                # 20% proximity check
                if curr_price < bottom:
                    dist = ((bottom - curr_price) / curr_price) * 100
                    if dist <= 20.0:
                        tf_results[tf].append(f"• *{symbol}*: {ob_type} (Near: {dist:.1f}%)")
                elif curr_price > top:
                    dist = ((curr_price - top) / top) * 100
                    if dist <= 20.0:
                        tf_results[tf].append(f"• *{symbol}*: {ob_type} (Near: {dist:.1f}%)")
                else:
                    tf_results[tf].append(f"• *{symbol}*: ⚡ *INSIDE {ob_type}*")
                    
            except Exception as e:
                print(f"Error for {symbol} on {tf}: {e}")

    # Build formatted message with separate sections for each timeframe
    report_message = "📊 *Order Block Proximity Alerts (20% Range)*\n"
    
    for tf in timeframes:
        report_message += f"\n----------------------------------\n"
        report_message += f"⏰ *Timeframe: {tf}*\n"
        report_message += f"----------------------------------\n"
        if tf_results[tf]:
            # Show up to 12 items per timeframe to fit Telegram limit cleanly
            report_message += "\n".join(tf_results[tf][:12]) + "\n"
        else:
            report_message += "_No coins within 20% range._\n"

    send_telegram_alert(report_message)

if __name__ == "__main__":
    run_screener()
