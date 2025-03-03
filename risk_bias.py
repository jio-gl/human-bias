"""
risk_bias.py

A contrarian "Risk-Bias" strategy that does the OPPOSITE of the typical human bias:
- Let winners run (a larger take-profit)
- Cut losers quickly (a tighter stop-loss)

Signal Logic:
- Uptrend if short MA > long MA => buy small dips (pullbacks).
- Downtrend if short MA < long MA => short small bounces (spot code sim; real short requires margin/futures).
- Exit logic => small SL (quick to exit losers), bigger TP (ride winners).
"""

import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *

# ---------------- Configuration ----------------
API_KEY = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"
client = Client(API_KEY, API_SECRET)

SYMBOL = "ETHUSDT"
INTERVAL = Client.KLINE_INTERVAL_5MINUTE

SHORT_WINDOW = 5    # short-term MA
LONG_WINDOW  = 15   # long-term MA
PULLBACK_PCT = 0.003  # e.g., 0.3% from recent high/low as entry trigger

TRADE_QUANTITY = 0.01   # e.g., 0.01 ETH
SLEEP_TIME     = 60      # seconds between loop checks

# "Against the crowd" exit logic: bigger TP, smaller SL
TAKE_PROFIT_PCT = 0.05   # e.g., +5%
STOP_LOSS_PCT   = 0.01   # e.g., -1%

# ------------------------------------------------


def get_klines(symbol=SYMBOL, interval=INTERVAL, limit=50):
    """Fetch recent OHLCV data from Binance and return as a DataFrame."""
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_vol", "taker_quote_vol", "ignore"
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    return df


def generate_signal(df, short_window=SHORT_WINDOW, long_window=LONG_WINDOW, pullback_pct=PULLBACK_PCT):
    """
    Decide whether to go LONG or SHORT based on MAs + a pullback threshold.
    - If short MA > long MA => uptrend => wait for pullback from recent high.
    - If short MA < long MA => downtrend => wait for bounce from recent low.
    Returns "LONG", "SHORT", or None.
    """
    df["ma_short"] = df["close"].rolling(short_window).mean()
    df["ma_long"]  = df["close"].rolling(long_window).mean()

    short_ma = df["ma_short"].iloc[-1]
    long_ma  = df["ma_long"].iloc[-1]
    recent_close = df["close"].iloc[-1]

    # rolling highs/lows
    recent_high = df["high"].rolling(long_window).max().iloc[-1]
    recent_low  = df["low"].rolling(long_window).min().iloc[-1]

    if short_ma > long_ma:
        print(f"[INFO] Uptrend. Recent high: {recent_high}, recent close: {recent_close}, pullback_pct: {pullback_pct}")
        # Uptrend. Check if we have a small dip from the recent high
        if (recent_high - recent_close) / recent_high >= pullback_pct:
            return "LONG"

    elif short_ma < long_ma:
        print(f"[INFO] Downtrend. Recent low: {recent_low}, recent close: {recent_close}, pullback_pct: {pullback_pct}")
        # Downtrend. Check if we have a small bounce from the recent low
        if (recent_close - recent_low) / recent_low >= pullback_pct:
            return "SHORT"

    return None


def place_market_order(symbol, side, quantity):
    """Place a market order in SPOT (for real shorting, use margin/futures)."""
    try:
        qty_str = f"{quantity:.6f}"
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=qty_str
        )
        print(f"[{side}] Order placed for {symbol}, quantity={qty_str}. Response:")
        print(order)
        return order
    except Exception as e:
        print(f"Order failed for {symbol} ({side} {quantity}): {e}")
        return None


def get_current_price(symbol=SYMBOL):
    """Get the latest spot price."""
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])


def risk_bias_bot():
    """
    Main loop. 
    - If no position => check signal => enter LONG or SHORT.
    - If in position => use contrarian risk approach:
        * small stop-loss 
        * bigger take-profit
    """
    position_side = None  # "LONG" or "SHORT" or None
    entry_price   = 0.0

    while True:
        try:
            df = get_klines()
            signal = generate_signal(df)
            print(f"[INFO] Current signal: {signal}")

            current_price = get_current_price(SYMBOL)

            if position_side is None:
                # No position, see if we want to open one
                if signal == "LONG":
                    print("[BOT] Going LONG (buy).")
                    order = place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                    if order:
                        position_side = "LONG"
                        entry_price   = current_price

                elif signal == "SHORT":
                    # Spot short means you either hold the asset or use margin
                    # We'll just simulate a short by a 'sell' on spot 
                    print("[BOT] Going SHORT (sell).")
                    order = place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                    if order:
                        position_side = "SHORT"
                        entry_price   = current_price

            else:
                # Manage existing position with contrarian risk approach
                if position_side == "LONG":
                    # Price move from entry
                    change_pct = (current_price - entry_price) / entry_price

                    # If up >= TAKE_PROFIT_PCT => take profit
                    if change_pct >= TAKE_PROFIT_PCT:
                        print(f"[BOT] LONG take-profit at +{change_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                        position_side = None
                        entry_price   = 0.0

                    # If down <= -STOP_LOSS_PCT => cut loser
                    elif change_pct <= -STOP_LOSS_PCT:
                        print(f"[BOT] LONG stop-loss at {change_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                        position_side = None
                        entry_price   = 0.0

                elif position_side == "SHORT":
                    # For a short, profit = (entry_price - current_price)
                    short_pnl_pct = (entry_price - current_price) / entry_price

                    # If short_pnl_pct >= TAKE_PROFIT_PCT => we are up enough => buy to exit
                    if short_pnl_pct >= TAKE_PROFIT_PCT:
                        print(f"[BOT] SHORT take-profit at +{short_pnl_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                        position_side = None
                        entry_price   = 0.0

                    # If short_pnl_pct <= -STOP_LOSS_PCT => cut loser
                    elif short_pnl_pct <= -STOP_LOSS_PCT:
                        print(f"[BOT] SHORT stop-loss at {short_pnl_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                        position_side = None
                        entry_price   = 0.0

            time.sleep(SLEEP_TIME)

        except Exception as ex:
            print(f"[ERROR] {ex}")
            time.sleep(SLEEP_TIME)


if __name__ == "__main__":
    risk_bias_bot()
