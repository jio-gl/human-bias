"""
herding_mania.py

A Price Compression / Herding Strategy that checks ALL USDT pairs on Binance Spot:
1) Finds symbols where short MA is significantly above long MA (indicating mania).
2) Also checks RSI overbought levels.
3) Ranks "manic" symbols by how extreme the mania is.
4) Buys/Shorts top mania symbols; optionally sells others.

Caution:
- "Short" on Spot is just a SELL call unless you have margin/futures.
- This is a naive example. Real usage needs robust error handling, position management, etc.
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

# Strategy parameters
INTERVAL = Client.KLINE_INTERVAL_15MINUTE
SHORT_WINDOW = 5
LONG_WINDOW  = 25
MANIA_FACTOR = 1.20         # e.g., short MA must be 20% above long MA
RSI_OVERBOUGHT = 75         # RSI threshold for mania
MIN_VOLUME     = 200_000    # min quote volume to consider
TRADE_QUANTITY_USD = 100    # how many USDT to allocate per mania symbol
TOP_N          = 3          # how many mania symbols to trade at once
SLEEP_TIME     = 300        # seconds between full scans (e.g. 5 min)

STABLE_BASES = {"USDC","BUSD","TUSD","DAI","PAX","USDP","EUR","GBP","AUD","UST",
                "FDUSD","EURI","AEUR"}  # adjust as needed

# (Optional) exit logic: simple TP/SL for demonstration
TAKE_PROFIT_PCT = 0.10  # e.g., +10%
STOP_LOSS_PCT   = 0.05  # e.g., -5%


# ------------------------------------------------------
# 1) Fetch All Tickers
# ------------------------------------------------------
def get_all_tickers_info():
    """Return a DataFrame of 24h stats for all Binance symbols."""
    tickers_24h = client.get_ticker()
    df = pd.DataFrame(tickers_24h)
    
    # Convert numeric columns
    numeric_cols = ["volume", "quoteVolume", "priceChangePercent", 
                    "lastPrice", "highPrice", "lowPrice"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ------------------------------------------------------
# 2) Filter & Select Candidate Symbols
# ------------------------------------------------------
def filter_usdt_pairs(df, quote_symbol="USDT", min_quote_vol=MIN_VOLUME):
    """
    Filter for:
      - symbols ending with quote_symbol
      - exclude stablecoins
      - min volume
    Returns a list of symbol names.
    """
    df = df[df["symbol"].str.endswith(quote_symbol)]
    df = df[df["quoteVolume"] > min_quote_vol]

    # exclude stablecoin bases
    df["base_asset"] = df["symbol"].str[:-len(quote_symbol)]
    df = df[~df["base_asset"].isin(STABLE_BASES)]
    
    return df["symbol"].unique().tolist()


# ------------------------------------------------------
# 3) Fetch Klines & Compute Mania Indicators
# ------------------------------------------------------
def get_klines_df(symbol, interval=INTERVAL, limit=50):
    """Fetch klines for a given symbol and return a DataFrame with numeric columns."""
    try:
        raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(raw, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","quote_volume","trades",
            "taker_base_vol","taker_quote_vol","ignore"
        ])
        for col in ["open","high","low","close","volume","quote_volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except:
        return pd.DataFrame()  # in case of error


def calculate_mania_indicators(df, short_win=SHORT_WINDOW, long_win=LONG_WINDOW, rsi_period=14):
    """
    Return a dict with mania-related metrics:
      - ma_short, ma_long, mania_ratio (ma_short / (ma_long * MANIA_FACTOR))
      - rsi
      - last_close
    Return None if df is too small or can't compute.
    """
    if len(df) < max(short_win, long_win, rsi_period):
        return None
    
    # sort by time (in case)
    df = df.sort_values(by="open_time")
    df["ma_short"] = df["close"].rolling(short_win).mean()
    df["ma_long"]  = df["close"].rolling(long_win).mean()
    
    # RSI
    df["change"] = df["close"].diff()
    df["gain"]   = np.where(df["change"]>0, df["change"], 0)
    df["loss"]   = np.where(df["change"]<0, -df["change"],0)
    df["avg_gain"] = df["gain"].rolling(rsi_period).mean()
    df["avg_loss"] = df["loss"].rolling(rsi_period).mean()
    df["rs"] = df["avg_gain"] / (df["avg_loss"] + 1e-9)
    df["rsi"] = 100 - (100/(1+df["rs"]))
    
    latest = df.iloc[-1]
    ma_s = latest["ma_short"]
    ma_l = latest["ma_long"]
    rsi_val = latest["rsi"]
    last_close = latest["close"]
    
    if (ma_l is None) or (ma_l <= 0):
        mania_ratio = 0
    else:
        mania_ratio = ma_s / (ma_l * MANIA_FACTOR)  # how far above mania threshold we are
    
    return {
        "ma_short": ma_s,
        "ma_long": ma_l,
        "mania_ratio": mania_ratio,   # > 1 means mania threshold exceeded
        "rsi": rsi_val,
        "close": last_close
    }


def assess_mania_score(man_dict, mania_factor=MANIA_FACTOR, rsi_over=RSI_OVERBOUGHT):
    """
    Convert the mania indicators into a single mania 'score'.
    Example logic:
      - If mania_ratio > 1 => partial score
      - If rsi >= rsi_over => partial score
    Return a numeric mania_score. Higher => more manic.
    """
    if man_dict is None:
        return 0
    
    ratio_score = 0
    rsi_score   = 0
    
    # mania_ratio > 1 => the short MA is above mania_factor * long MA
    if man_dict["mania_ratio"] > 1:
        ratio_score = man_dict["mania_ratio"] - 1  # how far above 1 we are
    
    if man_dict["rsi"] >= rsi_over:
        rsi_score = (man_dict["rsi"] - rsi_over)/10.0  # small scaling
    
    return ratio_score + rsi_score


# ------------------------------------------------------
# 4) Main Bot Logic
# ------------------------------------------------------
def herding_mania_bot():
    """
    - Every cycle:
      1) Fetch all ticker info -> filter for USDT pairs, volume, etc.
      2) For each candidate, fetch klines, compute mania indicators.
      3) Compute a mania_score.
      4) Pick top N mania symbols.
      5) Place trades (LONG if mania forming, SHORT if mania is extremely overbought).
         (Naive example: if mania_ratio>1 but rsi<overbought => "LONG",
                         if mania_ratio>1 and rsi>overbought => "SHORT")
      6) (Optional) manage existing positions, sell those not manic, etc.
    - Sleep, repeat.
    """
    # We'll do a naive approach: every cycle, flatten any existing positions
    # except the top mania picks. Then buy/short the top picks equally.
    
    while True:
        try:
            print("[INFO] Fetching all ticker info ...")
            all_df = get_all_tickers_info()
            # filter to USDT pairs
            candidates = filter_usdt_pairs(all_df, "USDT", MIN_VOLUME)
            
            mania_rows = []
            print(f"[INFO] Found {len(candidates)} candidate USDT pairs.")
            
            for sym in candidates:
                kl_df = get_klines_df(sym, INTERVAL, limit=50)
                man_ind = calculate_mania_indicators(kl_df)
                mania_score = assess_mania_score(man_ind)
                
                if man_ind is not None:
                    mania_rows.append({
                        "symbol": sym,
                        "mania_score": mania_score,
                        "ma_short": man_ind["ma_short"],
                        "ma_long":  man_ind["ma_long"],
                        "rsi":      man_ind["rsi"],
                        "close":    man_ind["close"]
                    })
            
            # make DataFrame
            mania_df = pd.DataFrame(mania_rows)
            mania_df = mania_df.sort_values("mania_score", ascending=False)
            
            # pick top N
            top_df = mania_df.head(TOP_N)
            print("\n[DEBUG] Top mania symbols:")
            print(top_df[["symbol","mania_score","ma_short","ma_long","rsi","close"]])
            
            top_symbols = top_df["symbol"].tolist()
            
            # SELL everything not in top_symbols (or no mania)
            flatten_others(top_symbols, "USDT")
            
            # For each top symbol, decide LONG or SHORT
            for _, row in top_df.iterrows():
                sym  = row["symbol"]
                sc   = row["mania_score"]
                ma_s = row["ma_short"]
                ma_l = row["ma_long"]
                rsi_v= row["rsi"]
                price= row["close"]
                
                # Decide LONG or SHORT:
                # Example:
                # if mania_ratio>1 but RSI<overbought => "LONG"
                # if mania_ratio>1 and RSI>=overbought => "SHORT"
                # mania_ratio = (ma_s / (ma_l * MANIA_FACTOR))
                mania_ratio = (ma_s / (ma_l * MANIA_FACTOR)) if (ma_l>0) else 0
                
                # Check if we already hold some of this symbol (spot "long" position)
                # or if we hold a "short" (not trivial in spot). For simplicity, assume we do not hold.
                if mania_ratio>1:
                    if rsi_v < RSI_OVERBOUGHT:
                        # mania forming => LONG
                        buy_amount = TRADE_QUANTITY_USD / price
                        buy_amount = round(buy_amount, 6)
                        print(f"[TRADE] LONG mania: Buying {buy_amount} of {sym} at ~{price}.")
                        place_spot_order(sym, SIDE_BUY, buy_amount)
                    else:
                        # mania Overdone => SHORT (spot = SELL)
                        # naive approach: we pretend we hold some of it, or we do margin in real usage
                        sell_amount = TRADE_QUANTITY_USD / price
                        sell_amount = round(sell_amount, 6)
                        print(f"[TRADE] SHORT mania: 'Selling' {sell_amount} of {sym} at ~{price}.")
                        place_spot_order(sym, SIDE_SELL, sell_amount)
                else:
                    print(f"[SKIP] {sym} mania_ratio={mania_ratio:.2f} < 1, no mania trade.")
            
            print("[INFO] Cycle complete. Sleeping...")
            time.sleep(SLEEP_TIME)
        
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(SLEEP_TIME)


# ------------------------------------------------------
# 5) Helpers to Flatten Non-Mania Positions & Place Orders
# ------------------------------------------------------
def flatten_others(keep_symbols, quote_symbol="USDT"):
    """
    Sell all spot holdings that are NOT in keep_symbols.
    """
    try:
        acct = client.get_account()
        bals = acct["balances"]
        for b in bals:
            asset = b["asset"]
            free_amt = float(b["free"])
            if free_amt <= 0 or asset == quote_symbol:
                continue
            
            pair = asset + quote_symbol
            # if not in keep_symbols => sell
            if pair not in keep_symbols:
                qty = round(free_amt, 6)
                if qty>0:
                    print(f"[FLATTEN] Selling {qty} of {pair} (not in mania list).")
                    place_spot_order(pair, SIDE_SELL, qty)
    except Exception as e:
        print(f"[FLATTEN ERROR] {e}")


def place_spot_order(symbol, side, quantity):
    """Wrapper for placing a SPOT market order."""
    try:
        q_str = f"{quantity:.6f}"
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=q_str
        )
        print(f"[{side}] Placed market order on {symbol}, qty={q_str}.")
        # optional: store order info, handle partial fills, etc.
    except Exception as e:
        print(f"[ORDER ERROR] {symbol} {side} {quantity}: {e}")


# ------------------------------------------------------
# 6) Main Execution
# ------------------------------------------------------
if __name__ == "__main__":
    herding_mania_bot()
