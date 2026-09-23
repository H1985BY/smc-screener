from functools import wraps
import pandas as pd
import numpy as np
from pandas import DataFrame, Series
from datetime import datetime
import ccxt
import telebot

# --- Telegram Bot Configuration ---
TOKEN = "8324901108:AAHb6wVr2Ta8hfC0a5ZlPnG_z_SGwUlop34"
CHAT_ID = "6172553941"

bot = telebot.TeleBot(TOKEN)

def send_telegram_alert(message):
    try:
        bot.send_message(CHAT_ID, message, parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram Error: {e}")

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
        return pd.concat([
            pd.Series(np.nan, index=ohlc.index, name="OB"),
            pd.Series(np.nan, index=ohlc.index, name="Top"),
            pd.Series(np.nan, index=ohlc.index, name="Bottom"),
            pd.Series(np.nan, index=ohlc.index, name="OBVolume"),
            pd.Series(np.nan, index=ohlc.index, name="MitigatedIndex"),
            pd.Series(np.nan, index=ohlc.index, name="Percentage"),
        ], axis=1)

    @classmethod
    def liquidity(cls, ohlc: DataFrame, swing_highs_lows: DataFrame, range_percent: float = 0.01) -> Series:
        return pd.concat([
            pd.Series(np.nan, index=ohlc.index, name="Liquidity"),
            pd.Series(np.nan, index=ohlc.index, name="Level"),
            pd.Series(np.nan, index=ohlc.index, name="EndIndex"),
            pd.Series(np.nan, index=ohlc.index, name="SweptIndex"),
        ], axis=1)

# --- Screener & Main Execution Logic ---
def run_screener():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT']
    exchange = ccxt.binance()
    
    signal_found = False
    report_message = "📊 *SMC Screener Report*\n\n"

    for symbol in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            fvg_df = smc.fvg(df)
            last_fvg = fvg_df['FVG'].iloc[-2] if not fvg_df.empty else np.nan
            
            if not np.isnan(last_fvg):
                signal_found = True
                signal_type = "🟢 Bullish" if last_fvg == 1 else "🔴 Bearish"
                report_message += f"• *{symbol}*: {signal_type} FVG Signal Detected!\n"
                
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

    if signal_found:
        send_telegram_alert(report_message)
    else:
        send_telegram_alert("ℹ️ *SMC Screener Scan Completed:* No trading signals found at this moment.")

if __name__ == "__main__":
    run_screener()
