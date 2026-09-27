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

def fetch_binance_klines(symbol, timeframe='4h', limit=150):
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

def find_extreme_order_blocks(df):
    obs = []
    for i in range(2, len(df) - 2):
        o = df['open'].iloc[i]
        c = df['close'].iloc[i]
        h = df['high'].iloc[i]
        l = df['low'].iloc[i]
        
        # Bullish Extreme OB formed by strong displacement move
        if c < o and df['close'].iloc[i+1] > df['high'].iloc[i]:
            obs.append({'type': 'Bullish Extreme OB 🟢', 'top': h, 'bottom': l})
        # Bearish Extreme OB formed by strong displacement move
        elif c > o and df['close'].iloc[i+1] < df['low'].iloc[i]:
            obs.append({'type': 'Bearish Extreme OB 🔴', 'top': h, 'bottom': l})
    return obs

def run_screener():
    # Top liquid symbols focusing on Higher Timeframe extremes
    symbols = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'BNB/USDT', 'XRP/USDT', 
        'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'APT/USDT', 'ARB/USDT', 
        'OP/USDT', 'SUI/USDT', 'TIA/USDT', 'RENDER/USDT', 'FET/USDT', 'INJ/USDT'
    ]
    
    symbols = list(dict.fromkeys(symbols))
    timeframes = ['1h', '4h', '1d']
    
    # Separate results for 1h, 4h, and 1d
    tf_results = {'1h': [], '4h': [], '1d': []}

    for symbol in symbols:
        for tf in timeframes:
            try:
                ohlcv = fetch_binance_klines(symbol, timeframe=tf, limit=150)
                if ohlcv is None or len(ohlcv) < 50:
                    continue
                    
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                curr_price = df['close'].iloc[-1]
                
                obs = find_extreme_order_blocks(df)
                if not obs:
                    continue
                
                # Take the most recent Extreme OB
                latest_ob = obs[-1]
                top = latest_ob['top']
                bottom = latest_ob['bottom']
                ob_type = latest_ob['type']
                
                # Strict proximity check for extreme zones (within 4% range or touching)
                if curr_price < bottom:
                    dist = ((bottom - curr_price) / curr_price) * 100
                    if dist <= 4.0:
                        tf_results[tf].append(f"• *{symbol}*: {ob_type} (Near: {dist:.1f}%)")
                elif curr_price > top:
                    dist = ((curr_price - top) / top) * 100
                    if dist <= 4.0:
                        tf_results[tf].append(f"• *{symbol}*: {ob_type} (Near: {dist:.1f}%)")
                else:
                    tf_results[tf].append(f"• *{symbol}*: ⚡ *INSIDE {ob_type}*")
                    
            except Exception as e:
                print(f"Error for {symbol} on {tf}: {e}")

    # Build formatted message separated by Higher Timeframes
    report_message = "🔥 *Higher Timeframe Extreme Zone Screener*\n"
    
    for tf in timeframes:
        report_message += f"\n----------------------------------\n"
        report_message += f"⏰ *Timeframe: {tf}*\n"
        report_message += f"----------------------------------\n"
        if tf_results[tf]:
            report_message += "\n".join(tf_results[tf][:10]) + "\n"
        else:
            report_message += "_No coins at extreme zones._\n"

    send_telegram_alert(report_message)

if __name__ == "__main__":
    run_screener()
