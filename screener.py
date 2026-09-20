import json
import urllib.request
import time
import os

TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

TARGET_COINS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 
    'ADAUSDT', 'AVAXUSDT', 'NEARUSDT', 'LINKUSDT', 'DOTUSDT', 
    'SUIUSDT', 'APTUSDT', 'DOGEUSDT', 'PEPEUSDT', 'SHIBUSDT',
    'RENDERUSDT', 'FETUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT',
    'TIAUSDT', 'SEIUSDT', 'WIFUSDT', 'ONDOUSDT', 'GALAUSDT'
]

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram Token or Chat ID missing in Secrets!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            pass
    except Exception as e:
        print(f"⚠️ Telegram Alert Error: {e}")

def fetch_klines(symbol, interval, limit=100):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return [{
                'open': float(item[1]),
                'high': float(item[2]),
                'low': float(item[3]),
                'close': float(item[4]),
                'volume': float(item[5])
            } for item in data]
    except Exception as e:
        print(f"⚠️ Fetching error for {symbol} ({interval}): {e}")
        return None

def analyze_htf_smc_structure(klines):
    if not klines or len(klines) < 30:
        return "SIDEWAYS"
        
    swing_highs, swing_lows = [], []
    for i in range(2, len(klines) - 2):
        if (klines[i]['high'] > klines[i-1]['high']) and (klines[i]['high'] > klines[i-2]['high']) and \
           (klines[i]['high'] > klines[i+1]['high']) and (klines[i]['high'] > klines[i+2]['high']):
            swing_highs.append(klines[i]['high'])
            
        if (klines[i]['low'] < klines[i-1]['low']) and (klines[i]['low'] < klines[i-2]['low']) and \
           (klines[i]['low'] < klines[i+1]['low']) and (klines[i]['low'] < klines[i+2]['low']):
            swing_lows.append(klines[i]['low'])
            
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
            return "UPTREND"
        elif swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
            return "DOWNTREND"
            
    latest_price = klines[-1]['close']
    if swing_highs and latest_price > swing_highs[-1]:
        return "UPTREND"
    elif swing_lows and latest_price < swing_lows[-1]:
        return "DOWNTREND"
        
    return "SIDEWAYS"

def find_unmitigated_15m_obs(klines_15m):
    bullish_obs, bearish_obs = [], []
    total_candles = len(klines_15m)
    start_idx = max(5, total_candles - 30)
    
    for i in range(start_idx, total_candles - 3):
        ob_candle, impulse_candle, fvg_candle = klines_15m[i], klines_15m[i+1], klines_15m[i+2]
        
        if (ob_candle['close'] < ob_candle['open']) and (impulse_candle['close'] > impulse_candle['open']) and (impulse_candle['close'] > ob_candle['high']):
            if fvg_candle['low'] > ob_candle['high']:
                is_unmitigated = all(klines_15m[j]['low'] > ob_candle['high'] for j in range(i + 3, total_candles - 1))
                if is_unmitigated:
                    bullish_obs.append({'high': ob_candle['high'], 'low': ob_candle['low']})

        if (ob_candle['close'] > ob_candle['open']) and (impulse_candle['close'] < impulse_candle['open']) and (impulse_candle['close'] < ob_candle['low']):
            if fvg_candle['high'] < ob_candle['low']:
                is_unmitigated = all(klines_15m[j]['high'] < ob_candle['low'] for j in range(i + 3, total_candles - 1))
                if is_unmitigated:
                    bearish_obs.append({'high': ob_candle['high'], 'low': ob_candle['low']})

    return bullish_obs, bearish_obs

def calculate_intraday_levels(direction, current_price, ob):
    if direction == "BULLISH":
        entry = current_price
        sl = ob['low'] * 0.999
        risk = entry - sl
        return entry, sl, entry + (risk * 2), entry + (risk * 3)
    else:
        entry = current_price
        sl = ob['high'] * 1.001
        risk = sl - entry
        return entry, sl, entry - (risk * 2), entry - (risk * 3)

def run_daytrading_screener():
    alerts_found = 0
    for symbol in TARGET_COINS:
        klines_4h = fetch_klines(symbol, '4h')
        klines_1h = fetch_klines(symbol, '1h')
        klines_15m = fetch_klines(symbol, '15m')
        
        if not klines_4h or not klines_1h or not klines_15m:
            continue

        trend_4h = analyze_htf_smc_structure(klines_4h)
        trend_1h = analyze_htf_smc_structure(klines_1h)
        current_price = klines_15m[-1]['close']

        if trend_4h == "UPTREND" and trend_1h == "UPTREND":
            htf_status, trend_direction = "4H + 1H UPTREND 📈", "BULLISH"
        elif trend_4h == "DOWNTREND" and trend_1h == "DOWNTREND":
            htf_status, trend_direction = "4H + 1H DOWNTREND 📉", "BEARISH"
        else:
            continue

        bullish_obs, bearish_obs = find_unmitigated_15m_obs(klines_15m)
        target_obs = bullish_obs if trend_direction == "BULLISH" else bearish_obs
        
        for ob in target_obs:
            if ob['low'] <= current_price <= ob['high']:
                entry, sl, tp1, tp2 = calculate_intraday_levels(trend_direction, current_price, ob)
                emoji = "🟢 LONG" if trend_direction == "BULLISH" else "🔴 SHORT"
                
                signal_msg = (
                    f"<b>⚡ DAY TRADING SMC ALERT</b>\n\n"
                    f"🎯 <b>Coin:</b> #{symbol} ({emoji})\n"
                    f"🔥 <b>Trend:</b> {htf_status}\n"
                    f"⏱️ <b>Setup:</b> 15m Fresh OB + FVG\n\n"
                    f"📍 <b>Entry Price:</b> {entry:.4f}\n"
                    f"🛑 <b>Stop Loss (SL):</b> {sl:.4f}\n"
                    f"🎯 <b>Take Profit 1 (1:2 RR):</b> {tp1:.4f}\n"
                    f"🚀 <b>Take Profit 2 (1:3 RR):</b> {tp2:.4f}\n\n"
                    f"📦 <b>15m Zone:</b> [{ob['low']:.4f} - {ob['high']:.4f}]"
                )
                send_telegram_alert(signal_msg)
                alerts_found += 1
                break

    print(f"Scan complete. Total Alerts Sent: {alerts_found}")

if __name__ == "__main__":
    run_daytrading_screener()
