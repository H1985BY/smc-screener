import json
import urllib.request
import time
import os

TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")

# 31 Fundamental & High-Volume Unique Coins
TARGET_COINS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 
    'ADAUSDT', 'AVAXUSDT', 'NEARUSDT', 'LINKUSDT', 'DOTUSDT', 
    'SUIUSDT', 'APTUSDT', 'DOGEUSDT', 'PEPEUSDT', 'SHIBUSDT',
    'RENDERUSDT', 'FETUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT',
    'TIAUSDT', 'SEIUSDT', 'WIFUSDT', 'ONDOUSDT', 'GALAUSDT',
    'ATOMUSDT', 'UNIUSDT', 'MATICUSDT', 'ICPUSDT', 'LTCUSDT', 'ETCUSDT'
]
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
    try:
        with urllib.request.urlopen(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10) as response:
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

def luxalgo_market_structure(klines):
    """LuxAlgo Style BOS & CHoCH / Trend Detection"""
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
            trend = "BULLISH"
        elif swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
            trend = "BEARISH"
            
    return trend, recent_high, recent_low

def luxalgo_order_blocks_and_fvg(klines_15m):
    """LuxAlgo Style OB + FVG Confluence Zones Mapping"""
    bullish_boxes, bearish_boxes = [], []
    total = len(klines_15m)
    start_idx = max(5, total - 40)
    
    for i in range(start_idx, total - 3):
        ob = klines_15m[i]
        impulse = klines_15m[i+1]
        fvg = klines_15m[i+2]
        
        # Bullish OB (Last bearish candle before impulsive break of structure)
        if (ob['close'] < ob['open']) and (impulse['close'] > impulse['open']) and (impulse['close'] > ob['high']):
            if fvg['low'] > ob['high']: # FVG Imbalance confirmed
                unmitigated = all(k['low'] > ob['high'] for k in klines_15m[i+3:-1])
                current = klines_15m[-1]
                in_zone = (ob['low'] <= current['low'] <= fvg['low']) or (ob['low'] <= current['close'] <= fvg['low'])
                
                if unmitigated and in_zone:
                    bullish_boxes.append({
                        'ob_high': ob['high'], 'ob_low': ob['low'],
                        'fvg_top': fvg['low'], 'fvg_bottom': ob['high']
                    })

        # Bearish OB (Last bullish candle before impulsive drop)
        if (ob['close'] > ob['open']) and (impulse['close'] < impulse['open']) and (impulse['close'] < ob['low']):
            if fvg['high'] < ob['low']: # FVG Imbalance confirmed
                unmitigated = all(k['high'] < ob['low'] for k in klines_15m[i+3:-1])
                current = klines_15m[-1]
                in_zone = (fvg['high'] <= current['high'] <= ob['high']) or (fvg['high'] <= current['close'] <= ob['high'])
                
                if unmitigated and in_zone:
                    bearish_boxes.append({
                        'ob_high': ob['high'], 'ob_low': ob['low'],
                        'fvg_top': ob['low'], 'fvg_bottom': fvg['high']
                    })

    return bullish_boxes, bearish_boxes

def check_luxalgo_triggers(klines_5m, direction):
    """5m Confirmation similar to LuxAlgo multi-timeframe precision"""
    if not klines_5m or len(klines_5m) < 10:
        return True
    last_c = klines_5m[-1]
    prev_c = klines_5m[-2]
    if direction == "BULLISH":
        return last_c['close'] > last_c['open'] or (prev_c['close'] < prev_c['open'] and last_c['close'] > prev_c['high'])
    else:
        return last_c['close'] < last_c['open'] or (prev_c['close'] > prev_c['open'] and last_c['close'] < prev_c['low'])

def run_luxalgo_screener():
    alerts = 0
    for symbol in TARGET_COINS:
        k4h = fetch_klines(symbol, '4h')
        k1h = fetch_klines(symbol, '1h')
        k15m = fetch_klines(symbol, '15m')
        k5m = fetch_klines(symbol, '5m')
        
        if not k4h or not k1h or not k15m or not k5m:
            continue

        trend_4h, h_4h, l_4h = luxalgo_market_structure(k4h)
        trend_1h, _, _ = luxalgo_market_structure(k1h)
        current_price = k15m[-1]['close']
        
        bullish_zones, bearish_zones = luxalgo_order_blocks_and_fvg(k15m)

        # 1. LUXALGO ACTIVE DAY TRADING (Fast execution on 15m OB+FVG reaction)
        for zone in bullish_zones + bearish_zones:
            is_bull = zone in bullish_zones
            direction = "BULLISH" if is_bull else "BEARISH"
            
            if not check_luxalgo_triggers(k5m, direction):
                continue
                
            if is_bull:
                entry = current_price
                sl = zone['ob_low'] * 0.994
                risk = entry - sl
                if risk <= 0: continue
                tp = entry + (risk * 2.8) # High RR target
                rr = (tp - entry) / risk
                if rr < 1.8: continue
                
                msg = (
                    f"🟢 <b>[LUXALGO SMC] DAY LONG SIGNAL</b>\n\n"
                    f"🎯 <b>Asset:</b> #{symbol}\n"
                    f"📍 <b>Entry:</b> {entry:.4f}\n"
                    f"🛑 <b>Stop Loss:</b> {sl:.4f}\n"
                    f"🎯 <b>Take Profit:</b> {tp:.4f}\n"
                    f"⚖️ <b>Risk/Reward:</b> 1:{rr:.2f}\n"
                    f"📦 <b>OB + FVG Zone:</b> {zone['ob_low']:.4f} - {zone['ob_high']:.4f}"
                )
                send_telegram_alert(msg)
                alerts += 1
                break
            else:
                entry = current_price
                sl = zone['ob_high'] * 1.006
                risk = sl - entry
                if risk <= 0: continue
                tp = entry - (risk * 2.8)
                rr = (entry - tp) / risk
                if rr < 1.8: continue
                
                msg = (
                    f"🔴 <b>[LUXALGO SMC] DAY SHORT SIGNAL</b>\n\n"
                    f"🎯 <b>Asset:</b> #{symbol}\n"
                    f"📍 <b>Entry:</b> {entry:.4f}\n"
                    f"🛑 <b>Stop Loss:</b> {sl:.4f}\n"
                    f"🎯 <b>Take Profit:</b> {tp:.4f}\n"
                    f"⚖️ <b>Risk/Reward:</b> 1:{rr:.2f}\n"
                    f"📦 <b>OB + FVG Zone:</b> {zone['ob_low']:.4f} - {zone['ob_high']:.4f}"
                )
                send_telegram_alert(msg)
                alerts += 1
                break

        # 2. LUXALGO PRO SWING (Strict HTF 4H/1H alignment + Premium/Discount filter)
        if trend_4h == trend_1h and trend_4h != "SIDEWAYS":
            swing_dir = "BULLISH" if trend_4h == "BULLISH" else "BEARISH"
            zones = bullish_zones if swing_dir == "BULLISH" else bearish_zones
            
            for zone in zones:
                # Premium/Discount check: Longs only in lower half, Shorts in upper half
                equilibrium = (h_4h + l_4h) / 2
                if swing_dir == "BULLISH" and current_price > equilibrium: continue
                if swing_dir == "BEARISH" and current_price < equilibrium: continue
                
                if swing_dir == "BULLISH":
                    entry = current_price
                    sl = zone['ob_low'] * 0.993
                    risk = entry - sl
                    if risk <= 0: continue
                    tp = h_4h # Target HTF Swing High liquidity
                    rr = (tp - entry) / risk
                    if rr < 2.0: continue
                    
                    msg = (
                        f"⚡ <b>[LUXALGO PRO] SWING LONG SETUP</b>\n\n"
                        f"🔥 <b>Asset:</b> #{symbol}\n"
                        f"📊 <b>HTF Trend:</b> {trend_4h} (Discount Zone)\n"
                        f"📍 <b>Entry:</b> {entry:.4f}\n"
                        f"🛑 <b>Stop Loss:</b> {sl:.4f}\n"
                        f"🎯 <b>Liquidity TP:</b> {tp:.4f}\n"
                        f"⚖️ <b>Risk/Reward:</b> 1:{rr:.2f}"
                    )
                    send_telegram_alert(msg)
                    alerts += 1
                    break
                else:
                    entry = current_price
                    sl = zone['ob_high'] * 1.007
                    risk = sl - entry
                    if risk <= 0: continue
                    tp = l_4h # Target HTF Swing Low liquidity
                    rr = (entry - tp) / risk
                    if rr < 2.0: continue
                    
                    msg = (
                        f"⚡ <b>[LUXALGO PRO] SWING SHORT SETUP</b>\n\n"
                        f"🔥 <b>Asset:</b> #{symbol}\n"
                        f"📊 <b>HTF Trend:</b> {trend_4h} (Premium Zone)\n"
                        f"📍 <b>Entry:</b> {entry:.4f}\n"
                        f"🛑 <b>Stop Loss:</b> {sl:.4f}\n"
                        f"🎯 <b>Liquidity TP:</b> {tp:.4f}\n"
                        f"⚖️ <b>Risk/Reward:</b> 1:{rr:.2f}"
                    )
                    send_telegram_alert(msg)
                    alerts += 1
                    break

    print(f"LuxAlgo Scan Complete. Alerts Sent: {alerts}")

if __name__ == "__main__":
    run_luxalgo_screener()
