from functools import wraps
import pandas as pd
import numpy as np
from pandas import DataFrame, Series
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

def inputvalidator(input_="ohlc"):
    def dfcheck(func):
        @wraps(func)
        def wrap(*args, **kwargs):
            args = list(args)
            i = 0 if isinstance(args[0], pd.DataFrame) else 1
            args[i] = args[i].rename(columns={c: c.lower() for c in args[i].columns})
            inputs = {
                "o": "open",
                "h": "high",
                "l": "low",
                "c": kwargs.get("column", "close").lower(),
                "v": "volume",
            }
            if inputs["c"] != "close":
                kwargs["column"] = inputs["c"]
            for l in input_:
                if inputs[l] not in args[i].columns:
                    raise LookupError('Must have a dataframe column named "{0}"'.format(inputs[l]))
            return func(*args, **kwargs)
        return wrap
    return dfcheck

def apply(decorator):
    def decorate(cls):
        for attr in cls.__dict__:
            if callable(getattr(cls, attr)):
                setattr(cls, attr, decorator(getattr(cls, attr)))
        return cls
    return decorate

@apply(inputvalidator(input_="ohlc"))
class smc:
    __version__ = "0.0.27"

    @classmethod
    def swing_highs_lows(cls, ohlc: DataFrame, swing_length: int = 5) -> Series:
        swing_length *= 2
        swing_highs_lows = np.where(
            ohlc["high"] == ohlc["high"].shift(-(swing_length // 2)).rolling(swing_length).max(), 1,
            np.where(ohlc["low"] == ohlc["low"].shift(-(swing_length // 2)).rolling(swing_length).min(), -1, np.nan)
        )
        level = np.where(~np.isnan(swing_highs_lows), np.where(swing_highs_lows == 1, ohlc["high"], ohlc["low"]), np.nan)
        return pd.concat([
            pd.Series(swing_highs_lows, name="HighLow"),
            pd.Series(level, name="Level")
        ], axis=1)

    @classmethod
    def ob(cls, ohlc: DataFrame, swing_highs_lows: DataFrame, close_mitigation: bool = False) -> Series:
        ob = np.where(
            (swing_highs_lows["HighLow"] == -1) & (ohlc["close"] < ohlc["open"]), 
            -1, 
            np.where((swing_highs_lows["HighLow"] == 1) & (ohlc["close"] > ohlc["open"]), 1, np.nan)
        )
        top = np.where(~np.isnan(ob), ohlc["high"], np.nan)
        bottom = np.where(~np.isnan(ob), ohlc["low"], np.nan)
        volume = np.where(~np.isnan(ob), ohlc["volume"], np.nan)
        
        mitigated_index = np.zeros(len(ohlc), dtype=np.int32)
        for i in np.where(~np.isnan(ob))[0]:
            mask = np.zeros(len(ohlc), dtype=np.bool_)
            if ob[i] == 1:
                if close_mitigation:
                    mask = ohlc["close"][i + 1 :] > top[i]
                else:
                    mask = ohlc["high"][i + 1 :] > top[i]
            elif ob[i] == -1:
                if close_mitigation:
                    mask = ohlc["close"][i + 1 :] < bottom[i]
                else:
                    mask = ohlc["low"][i + 1 :] < bottom[i]
            if np.any(mask):
                mitigated_index[i] = np.argmax(mask) + i + 1

        mitigated_index = np.where(np.isnan(ob), np.nan, mitigated_index)
        return pd.concat([
            pd.Series(ob, name="OB"),
            pd.Series(top, name="Top"),
            pd.Series(bottom, name="Bottom"),
            pd.Series(volume, name="OBVolume"),
            pd.Series(mitigated_index, name="MitigatedIndex")
        ], axis=1)

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
    timeframes = ['15m', '1h', '4h', '1d']
    
    report_message = f"🎯 *Order Block Proximity Screener ({len(symbols)} Coins)*\n\n"
    total_signals = 0

    for symbol in symbols:
        coin_signals = []
        for tf in timeframes:
            try:
                ohlcv = fetch_binance_klines(symbol, timeframe=tf, limit=150)
                if ohlcv is None or len(ohlcv) < 50:
                    continue
                    
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                shl = smc.swing_highs_lows(df, swing_length=5)
                ob_df = smc.ob(df, shl)
                
                curr_price = df['close'].iloc[-1]
                tf_signals = []
                
                # Get recent unmitigated or active OBs
                active_obs = ob_df[ob_df['MitigatedIndex'].isna()].tail(5)
                if active_obs.empty:
                    active_obs = ob_df.tail(5)
                
                for idx, ob in active_obs.iterrows():
                    top = ob['Top']
                    bottom = ob['Bottom']
                    if pd.isna(top) or pd.isna(bottom):
                        continue
                        
                    # Calculate distance percentage from current price to OB zone
                    if curr_price < bottom:
                        dist = ((bottom - curr_price) / curr_price) * 100
                        if dist <= 3.0: # Within 3% range
                            ob_type = f"🟢 Bullish OB (Near: {dist:.1f}%)"
                            if ob_type not in tf_signals:
                                tf_signals.append(ob_type)
                    elif curr_price > top:
                        dist = ((curr_price - top) / top) * 100
                        if dist <= 3.0: # Within 3% range
                            ob_type = f"🔴 Bearish OB (Near: {dist:.1f}%)"
                            if ob_type not in tf_signals:
                                tf_signals.append(ob_type)
                    else:
                        # Price is directly inside the OB zone!
                        ob_type = "⚡ *INSIDE OB ZONE*"
                        if ob_type not in tf_signals:
                            tf_signals.append(ob_type)
                
                if tf_signals:
                    coin_signals.append(f"_{tf}_: {', '.join(tf_signals)}")
                    
            except Exception as e:
                print(f"Error processing {symbol} on {tf}: {e}")
                
        if coin_signals:
            report_message += f"• *{symbol}* -> " + " | ".join(coin_signals) + "\n"
            total_signals += 1

    if total_signals == 0:
        report_message += "_No coins within 3% proximity of OB zones right now._\n"

    report_message += f"\n_Scan completed successfully._"
    send_telegram_alert(report_message)

if __name__ == "__main__":
    run_screener()
