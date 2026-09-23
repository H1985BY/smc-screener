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
    
    # Split message if it exceeds Telegram's 4000 character limit
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
    def fvg(cls, ohlc: DataFrame, join_consecutive=False) -> Series:
        fvg = np.where(
            (
                (ohlc["high"].shift(1) < ohlc["low"].shift(-1))
                & (ohlc["close"] > ohlc["open"])
            )
            | (
                (ohlc["low"].shift(1) > ohlc["high"].shift(-1))
                & (ohlc["close"] < ohlc["open"])
            ),
            np.where(ohlc["close"] > ohlc["open"], 1, -1),
            np.nan,
        )
        top = np.where(~np.isnan(fvg), np.where(ohlc["close"] > ohlc["open"], ohlc["low"].shift(-1), ohlc["low"].shift(1)), np.nan)
        bottom = np.where(~np.isnan(fvg), np.where(ohlc["close"] > ohlc["open"], ohlc["high"].shift(1), ohlc["high"].shift(-1)), np.nan)
        
        mitigated_index = np.zeros(len(ohlc), dtype=np.int32)
        for i in np.where(~np.isnan(fvg))[0]:
            mask = np.zeros(len(ohlc), dtype=np.bool_)
            if fvg[i] == 1:
                mask = ohlc["low"][i + 2 :] <= top[i]
            elif fvg[i] == -1:
                mask = ohlc["high"][i + 2 :] >= bottom[i]
            if np.any(mask):
                mitigated_index[i] = np.argmax(mask) + i + 2

        mitigated_index = np.where(np.isnan(fvg), np.nan, mitigated_index)
        return pd.concat([
            pd.Series(fvg, name="FVG"),
            pd.Series(top, name="Top"),
            pd.Series(bottom, name="Bottom"),
            pd.Series(mitigated_index, name="MitigatedIndex")
        ], axis=1)

    @classmethod
    def swing_highs_lows(cls, ohlc: DataFrame, swing_length: int = 50) -> Series:
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

    @classmethod
    def liquidity(cls, ohlc: DataFrame, swing_highs_lows: DataFrame, range_percent: float = 0.01) -> Series:
        liquidity = np.where(swing_highs_lows["HighLow"] == 1, 1, np.where(swing_highs_lows["HighLow"] == -1, -1, np.nan))
        level = swing_highs_lows["Level"]
        
        end_index = np.zeros(len(ohlc), dtype=np.int32)
        swept_index = np.zeros(len(ohlc), dtype=np.int32)
        
        for i in np.where(~np.isnan(liquidity))[0]:
            if liquidity[i] == 1:
                mask = ohlc["high"][i + 1 :] > level[i]
                if np.any(mask):
                    swept_index[i] = np.argmax(mask) + i + 1
            elif liquidity[i] == -1:
                mask = ohlc["low"][i + 1 :] < level[i]
                if np.any(mask):
                    swept_index[i] = np.argmax(mask) + i + 1

        end_index = np.where(np.isnan(liquidity), np.nan, end_index)
        swept_index = np.where(np.isnan(liquidity) | (swept_index == 0), np.nan, swept_index)

        return pd.concat([
            pd.Series(liquidity, name="Liquidity"),
            pd.Series(level, name="Level"),
            pd.Series(end_index, name="EndIndex"),
            pd.Series(swept_index, name="SweptIndex")
        ], axis=1)

    @classmethod
    def bos(cls, ohlc: DataFrame, swing_highs_lows: DataFrame) -> Series:
        bos = np.where(
            (swing_highs_lows["HighLow"] == 1) & (ohlc["close"] > swing_highs_lows["Level"].shift()), 1,
            np.where((swing_highs_lows["HighLow"] == -1) & (ohlc["close"] < swing_highs_lows["Level"].shift()), -1, 0)
        )
        level = np.where(bos != 0, swing_highs_lows["Level"], np.nan)
        return pd.concat([
            pd.Series(bos, name="BOS"),
            pd.Series(level, name="Level")
        ], axis=1)

    @classmethod
    def choch(cls, ohlc: DataFrame, swing_highs_lows: DataFrame) -> Series:
        choch = np.where(
            (swing_highs_lows["HighLow"] == 1) & (ohlc["close"] > swing_highs_lows["Level"].shift()), 1,
            np.where((swing_highs_lows["HighLow"] == -1) & (ohlc["close"] < swing_highs_lows["Level"].shift()), -1, 0)
        )
        level = np.where(choch != 0, swing_highs_lows["Level"], np.nan)
        return pd.concat([
            pd.Series(choch, name="CHOCH"),
            pd.Series(level, name="Level")
        ], axis=1)

def fetch_binance_klines(symbol, timeframe='1h', limit=100):
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
        print(f"API Error for {symbol}: {e}")
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
    
    report_message = f"📊 *SMC Setup Screener Report ({len(symbols)} Coins)*\n\n"
    scanned_count = 0

    for symbol in symbols:
        try:
            ohlcv = fetch_binance_klines(symbol, timeframe='1h', limit=100)
            if ohlcv is None or len(ohlcv) < 50:
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            scanned_count += 1
            
            shl = smc.swing_highs_lows(df)
            fvg_df = smc.fvg(df)
            ob_df = smc.ob(df, shl)
            liq_df = smc.liquidity(df, shl)
            bos_df = smc.bos(df, shl)
            choch_df = smc.choch(df, shl)
            
            last_fvg = fvg_df['FVG'].iloc[-2] if not fvg_df.empty else np.nan
            last_ob = ob_df['OB'].iloc[-2] if not ob_df.empty else np.nan
            last_liq = liq_df['Liquidity'].iloc[-2] if not liq_df.empty else np.nan
            last_bos = bos_df['BOS'].iloc[-2] if not bos_df.empty else 0
            last_choch = choch_df['CHOCH'].iloc[-2] if not choch_df.empty else 0
            
            signal_text = []
            if not np.isnan(last_fvg) and last_fvg != 0:
                signal_text.append("🟢 Bullish FVG" if last_fvg == 1 else "🔴 Bearish FVG")
            if not np.isnan(last_ob) and last_ob != 0:
                signal_text.append("🟢 Bullish OB" if last_ob == 1 else "🔴 Bearish OB")
            if not np.isnan(last_liq) and last_liq != 0:
                signal_text.append("⚡ Liquidity")
            if last_bos != 0:
                signal_text.append("📈 Bullish BOS" if last_bos == 1 else "📉 Bearish BOS")
            if last_choch != 0:
                signal_text.append("🔄 Bullish CHoCH" if last_choch == 1 else "🔄 Bearish CHoCH")
                
            if signal_text:
                report_message += f"• *{symbol}* : {', '.join(signal_text)}\n"
                
        except Exception as e:
            print(f"Error processing {symbol}: {e}")

    report_message += f"\n_Successfully scanned {scanned_count} coins._"
    send_telegram_alert(report_message)

if __name__ == "__main__":
    run_screener()
