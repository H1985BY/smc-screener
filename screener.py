import json
import urllib.request
import time
import os

TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

# Binance fundamental & top volume coins list expanded
TARGET_COINS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 
    'ADAUSDT', 'AVAXUSDT', 'NEARUSDT', 'LINKUSDT', 'DOTUSDT', 
    'SUIUSDT', 'APTUSDT', 'DOGEUSDT', 'PEPEUSDT', 'SHIBUSDT',
    'RENDERUSDT', 'FETUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT',
    'TIAUSDT', 'SEIUSDT', 'WIFUSDT', 'ONDOUSDT', 'GALAUSDT',
    'ATOMUSDT', 'UNIUSDT', 'NEARUSDT', 'MATICUSDT', 'ICPUSDT',
    'LTCUSDT', 'ETCUSDT', 'NEARUSDT', 'ATOMUSDT', 'NEARUSDT'
]
# Remove duplicates if any
TARGET_COINS = list(set(TARGET_COINS))

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
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
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
        return "SIDEWAYS", 0, 0
        
    swing_highs, swing_lows = [], []
    for i in range(2, len(klines) - 2):
        if (klines[i]['high'] > klines[i-1]['high']) and (klines[i]['high'] > klines[i-2]['high']) and \
           (klines[i]['high'] > klines[i+1]['high']) and (klines[i]['high'] > klines[i+2]['high']):
            swing_highs.append(klines[i]['high'])
            
        if (klines[i]['low'] < klines[i-1]['low']) and (klines[i]['low'] < klines[i-2]['low']) and \
           (klines[i]['low'] < klines[i+1]['low']) and (klines[i]['low'] < klines[i+2]['low']):
            swing_lows.append(klines[i]['low'])
            
    recent_high = max([c['high'] for c in klines[-50:]]) if len(klines) >= 50 else max(c['high'] for c in klines)
    recent_low = min([c['low'] for c in klines[-50:]]) if len(klines) >= 50 else min(c['low'] for c in klines)
    
    trend = "SIDEWAYS"
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
            trend = "UPTREND"
        elif swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
            trend = "DOWNTREND"
            
    return trend, recent_high, recent_low

def find_ob_with_fvg(klines_15m):
    bullish_setups, bearish_setups = [], []
    total_candles = len(klines_15m)
    start_idx = max(5, total_candles - 35)
    
    for i in range(start_idx, total_candles - 3):
        ob_candle, impulse_candle, fvg_candle = klines_15m[i], klines_15m[i+1], klines_15m[i+2]
        
        # Bullish OB + FVG Check
        if (ob_candle['close'] < ob_candle['open']) and (impulse_candle['close'] > impulse_candle['open']) and (impulse_candle['close'] > ob_candle['high']):
            if fvg_candle['low'] > ob_candle['high']:
                fvg_zone = {'top': fvg_candle['low'], 'bottom': ob_candle['high']}
                was_unmitigated = all(klines_15m[j]['low'] > ob_candle['high'] for j in range(i + 3, total_candles - 1))
                last_candle = klines_15m[-1]
                is_first_touch = (ob_candle['low'] <= last_candle['low'] <= fvg_zone['top']) or \
                                 (ob_candle['low'] <= last_candle['close'] <= fvg_zone['top'])
                
                if was_unmitigated and is_first_touch:
                    bullish_setups.append({
                        'ob_high': ob_candle['high'], 
                        'ob_low': ob_candle['low'],
                        'fvg_top': fvg_zone['top'],
                        'fvg_bottom': fvg_zone['bottom']
                    })

        # Bearish OB + FVG Check
        if (ob_candle['close'] > ob_candle['open']) and (impulse_candle['close'] < impulse_candle['open']) and (impulse_candle['close'] < ob_candle['low']):
            if fvg_candle['high'] < ob_candle['low']:
                fvg_zone = {'top': ob_candle['low'], 'bottom': fvg_candle['high']}
                was_unmitigated = all(klines_15m[j]['high'] < ob_candle['low'] for j in range(i + 3, total_candles - 1))
                last_candle = klines_15m[-1]
                is_first_touch = (fvg_zone['bottom'] <= last_candle['high'] <= ob_candle['high']) or \
                                 (fvg_zone['bottom'] <= last_candle['close'] <= ob_candle['high'])
                
                if was_unmitigated and is_first_touch:
                    bearish_setups.append({
                        'ob_high': ob_candle['high'], 
                        'ob_low': ob_candle['low'],
                        'fvg_top': fvg_zone['top'],
                        'fvg_bottom': fvg_zone['bottom']
                    })

    return bullish_setups, bearish_setups

def check_5m_pullback_confirmation(klines_5m, direction):
    """
    Pro Pullback Logic: Checks if 5m BOS occurred and price is currently pulling back 
    to retest the local discount/premium zone before continuation.
    """
    if not klines_5m or len(klines_5m) < 20:
        return False
        
    recent_candles = klines_5m[-15:]
    current_close = klines_5m[-1]['close']
    
    if direction == "BULLISH":
        # Check if recent structure broke high, and current candle is pulling back slightly (retest)
        local_high = max(c['high'] for c in recent_candles[:-4])
        has_bos = any(c['close'] > local_high for c in recent_candles[-4:-1])
        is_pullbacking = current_close < recent_candles[-2]['high'] # Pullback retrace candle
        return has_bos and is_pullbacking
    else:
        # Check bearish break and pullback
        local_low = min(c['low'] for c in recent_candles[:-4])
        has_bos = any(c['close'] < local_low for c in recent_candles[-4:-1])
        is_pullbacking = current_close > recent_candles[-2]['low']
        return has_bos and is_pullbacking

def calculate_pro_levels(direction, current_price, setup, recent_high, recent_low):
    equilibrium = (recent_high + recent_low) / 2
    
    if direction == "BULLISH" and current_price > equilibrium:
        return None, None, None, None, "REJECT_PREMIUM"
    if direction == "BEARISH" and current_price < equilibrium:
        return None, None, None, None, "REJECT_DISCOUNT"

    if direction == "BULLISH":
        entry = current_price
        sl = setup['ob_low'] * 0.997 # Safe buffer below OB
        risk = entry - sl
        if risk <= 0:
            return None, None, None, None, "INVALID_RISK"
        
        tp = recent_high if recent_high > entry + (risk * 2) else entry + (risk * 3)
        rr = (tp - entry) / risk
        if rr < 1.8:
            return None, None, None, None, "LOW_RR"
            
        return entry, sl, tp, rr, "VALID"
    else:
        entry = current_price
        sl = setup['ob_high'] * 1.003
        risk = sl - entry
        if risk <= 0:
            return None, None, None, None, "INVALID_RISK"
            
        tp = recent_low if recent_low < entry - (risk * 2) else entry - (risk * 3)
        rr = (entry - tp) / risk
        if rr < 1.8:
            return None, None, None, None, "LOW_RR"
            
        return entry, sl, tp, rr, "VALID"

def run_daytrading_screener():
    alerts_found = 0
    for symbol in TARGET_COINS:
        klines_4h = fetch_klines(symbol, '4h')
        klines_1h = fetch_klines(symbol, '1h')
        klines_15m = fetch_klines(symbol, '15m')
        klines_5m = fetch_klines(symbol, '5m')
        
        if not klines_4h or not klines_1h or not klines_15m or not klines_5m:
            continue

        trend_4h, high_4h, low_4h = analyze_htf_smc_structure(klines_4h)
        trend_1h, _, _ = analyze_htf_smc_structure(klines_1h)
        current_price = klines_15m[-1]['close']

        if trend_4h == "UPTREND" and trend_1h == "UPTREND":
            htf_status, trend_direction = "4H + 1H UPTREND 📈", "BULLISH"
        elif trend_4h == "DOWNTREND" and trend_1h == "DOWNTREND":
            htf_status, trend_direction = "4H + 1H DOWNTREND 📉", "BEARISH"
        else:
            continue

        bullish_setups, bearish_setups = find_ob_with_fvg(klines_15m)
        target_setups = bullish_setups if trend_direction == "BULLISH" else bearish_setups
        
        for setup in target_setups:
            if not check_5m_pullback_confirmation(klines_5m, trend_direction):
                continue

            entry, sl, tp, rr, status = calculate_pro_levels(trend_direction, current_price, setup, high_4h, low_4h)
            if status != "VALID":
                continue

            zone_type = "Discount Zone 🟢 (Valid for Long)" if trend_direction == "BULLISH" else "Premium Zone 🔴 (Valid for Short)"
            emoji = "🟢 LONG" if trend_direction == "BULLISH" else "🔴 SHORT"
            
            signal_msg = (
                f"<b>⚡ PRO SMC PULLBACK + FVG SETUP</b>\n\n"
                f"🎯 <b>Coin:</b> #{symbol} ({emoji})\n"
                f"🔥 <b>Trend:</b> {htf_status}\n"
                f"📍 <b>Market Zone:</b> {zone_type}\n\n"
                f"📍 <b>Retest Entry:</b> {entry:.4f}\n"
                f"🛑 <b>Stop Loss:</b> {sl:.4f}\n"
                f"🎯 <b>Take Profit (Liquidity):</b> {tp:.4f}\n"
                f"⚖️ <b>Risk-to-Reward:</b> 1:{rr:.2f}\n\n"
                f"📦 <b>15m OB Zone:</b> [{setup['ob_low']:.4f} - {setup['ob_high']:.4f}]\n"
                f"⚖️ <b>FVG Imbalance:</b> [{setup['fvg_bottom']:.4f} - {setup['fvg_top']:.4f}]"
            )
            send_telegram_alert(signal_msg)
            alerts_found += 1
            break

    print(f"Scan complete. Pro Pullback Alerts Sent: {alerts_found}")

if __name__ == "__main__":
    run_daytrading_screener()
