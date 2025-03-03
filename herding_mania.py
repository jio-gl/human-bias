"""
herding_mania.py

A Price Compression / Herding Strategy for Binance Spot:
- Detect "mania" or "price compression" based on short MA vs. long MA, RSI, or volume surges.
- Optionally ride the mania if it is still strong.
- Attempt to short or exit if mania shows signs of exhaustion ("blow-off top").

IMPORTANT: 
1) For real short-selling, use Margin or Futures API calls.
2) This code is just a demonstration, not guaranteed to be profitable.
3) Always handle risk properly and test with small amounts or testnet first.
"""

import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *

# --------------------- CONFIG ---------------------
API_KEY = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"

client = Client(API_KEY, API_SECRET)

SYMBOL = "ETHUSDT"             # The pair to trade
INTERVAL = Client.KLINE_INTERVAL_15MINUTE
SHORT_WINDOW = 5               # For mania detection
LONG_WINDOW = 25
MANIA_FACTOR = 1.20            # e.g. short MA must be 20% above long MA
RSI_OVERBOUGHT = 75            # RSI threshold for mania
TRADE_QUANTITY = 0.01          # e.g. 0.01 ETH
POLLING_DELAY = 60             # seconds between checks

def get_klines(symbol=SYMBOL, interval=INTERVAL, limit=100):
    """
    Fetch kline (OHLCV) data from Binance and return as a DataFrame.
    """
    raw_klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw_klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_vol", "taker_quote_vol", "ignore"
    ])
    # Convert columns to numeric
    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # Convert times
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    return df

def calculate_indicators(df, short_window=SHORT_WINDOW, long_window=LONG_WINDOW, rsi_period=14):
    """
    Adds short MA, long MA, and RSI to the DataFrame.
    - short MA: rolling mean of close over 'short_window'
    - long MA : rolling mean of close over 'long_window'
    - RSI: standard 14-day formula
    """
    df = df.copy()
    df["MA_short"] = df["close"].rolling(short_window).mean()
    df["MA_long"] = df["close"].rolling(long_window).mean()

    # Compute RSI
    df["change"] = df["close"].diff()
    df["gain"] = np.where(df["change"] > 0, df["change"], 0)
    df["loss"] = np.where(df["change"] < 0, -df["change"], 0)
    df["avg_gain"] = df["gain"].rolling(rsi_period).mean()
    df["avg_loss"] = df["loss"].rolling(rsi_period).mean()
    df["rs"] = df["avg_gain"] / (df["avg_loss"] + 1e-9)  # avoid div by zero
    df["RSI"] = 100 - (100 / (1 + df["rs"]))

    return df

def detect_herding_signal(df, mania_factor=MANIA_FACTOR, rsi_overbought=RSI_OVERBOUGHT):
    """
    Detect mania and potential short/exit signal based on:
    1) short MA far above long MA (e.g., > mania_factor * long MA)
    2) RSI over a certain threshold (like 75/80)
    3) Optional volume check or price stalling

    Returns:
      - "LONG"  if mania is forming, we might ride it (short MA crossing above long MA).
      - "SHORT" if mania is overdone and stalling => short or exit.
      - None    if no trade signal.
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2]  # previous row

    ma_short = latest["MA_short"]
    ma_long = latest["MA_long"]
    rsi_val = latest["RSI"]
    close_price = latest["close"]
    
    # 1) Check mania condition: short MA is mania_factor above long MA
    if ma_long > 0 and (ma_short > ma_long * mania_factor):
        # 2) Also check RSI
        if rsi_val >= rsi_overbought:
            # If we see price stalling or reversing below short MA => short
            # e.g. if close_price < ma_short, let's call it a "SHORT" signal
            if close_price < ma_short:
                return "SHORT"
        else:
            # mania might still be forming => "LONG" if we just crossed above
            if (prev["MA_short"] < prev["MA_long"] * mania_factor) and (ma_short > ma_long * mania_factor):
                return "LONG"

    return None

def place_market_order(symbol, side, quantity):
    """
    Place a market order (SPOT).
    For real short selling, you must use MARGIN or FUTURES endpoints.
    """
    try:
        qty_str = f"{quantity:.6f}"  # 6 decimal places
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=qty_str
        )
        print(f"[{side}] Market order placed for {symbol}, qty={qty_str}. Order response:")
        print(order)
        return order
    except Exception as e:
        print(f"Order failed for {symbol} ({side} {quantity}): {e}")
        return None

def get_current_price(symbol=SYMBOL):
    """Return the current price from the Binance ticker."""
    data = client.get_symbol_ticker(symbol=symbol)
    return float(data["price"])

def herding_mania_bot():
    """
    Main loop:
      1) Fetch data & compute indicators
      2) Check signal from detect_herding_signal
      3) Decide whether to go LONG, SHORT or do nothing
      4) If you have an open position, manage it (TP, SL, or exit logic)
      
    NOTE: This is a naive example. In real usage, you'd track your open positions,
          use a more robust exit strategy, etc.
    """
    position_side = None  # "LONG" or "SHORT"
    entry_price = 0.0

    # (Optional) define some exit rules
    TAKE_PROFIT_PCT = 0.10  # e.g., +10%
    STOP_LOSS_PCT   = 0.05  # e.g., -5%

    while True:
        try:
            # 1) Fetch data
            df = get_klines()
            df = calculate_indicators(df)

            # 2) Check mania signals
            signal = detect_herding_signal(df)
            print(f"[INFO] Detected signal: {signal}")

            current_price = get_current_price(SYMBOL)

            if position_side is None:
                # 3) If no position, see if we want to open one
                if signal == "LONG":
                    print("[BOT] Opening LONG position (buy).")
                    order = place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                    if order:
                        position_side = "LONG"
                        entry_price = current_price

                elif signal == "SHORT":
                    # For a real short, you need margin or futures
                    # Here we simulate "SHORT" by just selling if we hold, 
                    # or ignoring if we have no holdings. 
                    # Or do margin logic if you want a real short.
                    print("[BOT] Opening SHORT position (spot SELL).")
                    order = place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                    if order:
                        position_side = "SHORT"
                        entry_price = current_price

            else:
                # 4) If in a position, manage it
                price_move = (current_price - entry_price) / entry_price

                if position_side == "LONG":
                    # If up more than TP, exit
                    if price_move >= TAKE_PROFIT_PCT:
                        print(f"[BOT] LONG TAKE-PROFIT reached: {price_move*100:.2f}%")
                        place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0
                    # If down more than SL, exit
                    elif price_move <= -STOP_LOSS_PCT:
                        print(f"[BOT] LONG STOP-LOSS reached: {price_move*100:.2f}%")
                        place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0

                elif position_side == "SHORT":
                    # For a real short, PnL is (entry_price - current_price)
                    # Let's define short_move as:
                    short_move = (entry_price - current_price) / entry_price
                    if short_move >= TAKE_PROFIT_PCT:
                        print(f"[BOT] SHORT TAKE-PROFIT reached: {short_move*100:.2f}%")
                        # On spot, to exit a short you would 'buy' the asset.
                        place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0
                    elif short_move <= -STOP_LOSS_PCT:
                        print(f"[BOT] SHORT STOP-LOSS reached: {short_move*100:.2f}%")
                        place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0

            time.sleep(POLLING_DELAY)

        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(POLLING_DELAY)


if __name__ == "__main__":
    herding_mania_bot()
