import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *

# ============== CONFIGURATION =========================
API_KEY = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"

# Trading parameters
SYMBOL = "ETHUSDT"  # Example
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
SHORT_WINDOW = 5
LONG_WINDOW = 15
PULLBACK_PCT = 0.003  # e.g., 0.3% from recent high/low
TRADE_QUANTITY = 0.01  # example: 0.01 ETH
SLEEP_TIME = 60  # seconds between checks

# Behavior: risk-averse on wins, risk-seeking on losses (asymmetry)
# This example tries to close winners quickly if it hits a small TP,
# but will hold losers longer or use a bigger stop-loss.

TAKE_PROFIT_PCT = 0.005  # e.g. +0.5%
STOP_LOSS_PCT = 0.015    # e.g. -1.5% (larger than the take-profit for asymmetry)

# ======================================================


client = Client(API_KEY, API_SECRET)

# ------------------------------------------------------
# 1) Utility: Fetch Klines
# ------------------------------------------------------
def get_klines(symbol=SYMBOL, interval=INTERVAL, limit=50):
    """Fetch OHLCV data from Binance and return as a pandas DataFrame."""
    raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_vol", "taker_quote_vol", "ignore"
    ])
    # Convert numeric columns
    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Convert times
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    return df


# ------------------------------------------------------
# 2) Logic: Momentum + Pullback
# ------------------------------------------------------
def generate_signal(df, short_window=SHORT_WINDOW, long_window=LONG_WINDOW, pullback_pct=PULLBACK_PCT):
    """
    Identify uptrends/downtrends via MAs:
      - If short MA > long MA => uptrend. 
        => Wait for a dip of 'pullback_pct' from recent high to go long.
      - If short MA < long MA => downtrend.
        => Wait for a bounce of 'pullback_pct' from recent low to go short.
    Returns "LONG", "SHORT", or None.
    """
    df["ma_short"] = df["close"].rolling(short_window).mean()
    df["ma_long"] = df["close"].rolling(long_window).mean()

    recent_close = df["close"].iloc[-1]
    short_ma = df["ma_short"].iloc[-1]
    long_ma = df["ma_long"].iloc[-1]

    # Rolling window highs/lows for reference
    recent_high = df["high"].rolling(long_window).max().iloc[-1]
    recent_low = df["low"].rolling(long_window).min().iloc[-1]

    # Check uptrend/downtrend
    if short_ma > long_ma:
        # Uptrend. Check if we have a pullback from the recent high.
        if (recent_high - recent_close) / recent_high >= pullback_pct:
            return "LONG"
    elif short_ma < long_ma:
        # Downtrend. Check if we have a bounce from the recent low.
        if (recent_close - recent_low) / recent_low >= pullback_pct:
            return "SHORT"
    
    return None


# ------------------------------------------------------
# 3) Placing Orders + Tracking Positions
# ------------------------------------------------------
def place_market_order(symbol, side, quantity):
    """
    Place a market order (Spot).
    For a real short, you'd need margin or futures. 
    Here we just show how to place a buy or sell on spot.
    """
    try:
        qty_str = f"{quantity:.6f}"  # round to avoid Binance precision errors
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=qty_str
        )
        print(f"[{side}] Market order placed for {symbol}, qty={qty_str}: {order}")
        return order
    except Exception as e:
        print(f"Order failed ({side} {symbol} {quantity}): {e}")
        return None


def get_symbol_ticker(symbol=SYMBOL):
    """Get the current price for a symbol."""
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])


# ------------------------------------------------------
# 4) Main Bot
#    Incorporates an asymmetric approach to winners vs. losers:
#    - Quick TP if in small profit
#    - Larger SL if in loss, to mimic 'risk-seeking on losses'
# ------------------------------------------------------
def momentum_pullback_bot():
    position_side = None  # "LONG" or "SHORT" or None
    entry_price = 0.0
    
    while True:
        try:
            # 1) Fetch klines
            df = get_klines()
            
            # 2) Generate signal
            signal = generate_signal(df)
            print(f"[INFO] Signal: {signal}")

            # 3) Check if we have an existing position
            if position_side is None:
                # If no position, see if we should open one
                if signal == "LONG":
                    print("[BOT] Going LONG.")
                    order = place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                    if order:
                        position_side = "LONG"
                        entry_price = get_symbol_ticker(SYMBOL)
                
                elif signal == "SHORT":
                    print("[BOT] Going SHORT (selling).")
                    # In Spot, "SHORT" might just mean selling a coin you hold,
                    # but let's assume we hold some of it. 
                    order = place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                    if order:
                        position_side = "SHORT"
                        entry_price = get_symbol_ticker(SYMBOL)

            else:
                # 4) If we DO have a position, check if we should exit
                current_price = get_symbol_ticker(SYMBOL)
                change_pct = (current_price - entry_price) / entry_price
                if position_side == "LONG":
                    if change_pct >= TAKE_PROFIT_PCT:
                        # Quick take-profit for winners
                        print(f"[BOT] Hit TAKE PROFIT for LONG at {change_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0
                    elif change_pct <= -STOP_LOSS_PCT:
                        # Larger stop-loss for losers (risk-seeking)
                        print(f"[BOT] Hit STOP LOSS for LONG at {change_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_SELL, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0

                elif position_side == "SHORT":
                    # For a real short, we'd buy back. On spot, might not apply 1:1
                    # but let's do the same logic with the reverse sign.
                    # If we "short" by selling, to exit, we might "buy" the same qty.
                    # Check P&L: If short from entry_price, PnL is (entry_price - current_price).
                    short_pnl_pct = (entry_price - current_price) / entry_price
                    if short_pnl_pct >= TAKE_PROFIT_PCT:
                        print(f"[BOT] Hit TAKE PROFIT for SHORT at {short_pnl_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0
                    elif short_pnl_pct <= -STOP_LOSS_PCT:
                        print(f"[BOT] Hit STOP LOSS for SHORT at {short_pnl_pct*100:.2f}%. Exiting.")
                        place_market_order(SYMBOL, SIDE_BUY, TRADE_QUANTITY)
                        position_side = None
                        entry_price = 0.0

            time.sleep(SLEEP_TIME)

        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(SLEEP_TIME)


if __name__ == "__main__":
    momentum_pullback_bot()
