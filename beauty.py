import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *

API_KEY = "YOUR_BINANCE_API_KEY"
API_SECRET = "YOUR_BINANCE_API_SECRET"
client = Client(API_KEY, API_SECRET)

def get_current_positions(quote_symbol="USDT"):
    """
    Retrieves current balances from the Spot account and composes a list of
    (symbol_pair, free_amount, locked_amount).
    
    For example, if you have 0.5 BTC and your quote is USDT, this returns
    ("BTCUSDT", free_amount, locked_amount).
    
    * Skips stablecoins like USDT & BUSD (since you probably want to keep them as 'cash').
    * In production, also skip dust balances, or handle them carefully.
    """
    account_info = client.get_account()
    balances = account_info["balances"]
    
    holdings = []
    for b in balances:
        asset = b["asset"]
        free = float(b["free"])
        locked = float(b["locked"])
        total = free + locked
        
        # Skip if no meaningful amount
        if total == 0:
            continue
        
        # Optionally skip stablecoins 
        if asset in ["USDT", "BUSD"]:
            continue
        
        # Construct a trading pair to sell into the quote symbol if it exists
        symbol_pair = asset + quote_symbol
        holdings.append((symbol_pair, free, locked))
    
    return holdings


def place_market_order(symbol, side, quantity):
    """Place a market order on Binance Spot."""
    try:
        # Round quantity to avoid 'invalid quantity' errors
        qty_str = f"{quantity:.6f}"
        
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=qty_str
        )
        print(f"[{side}] Order placed for {symbol}: {order}")
    except Exception as e:
        print(f"Order failed for {symbol} ({side} {quantity}): {e}")




def get_all_tickers_info():
    """
    Fetch 24hr ticker data for all symbols on Binance.
    Returns a DataFrame with symbol, volume, priceChangePercent, lastPrice, etc.
    """
    tickers_24h = client.get_ticker()
    df = pd.DataFrame(tickers_24h)
    
    # Convert numeric columns
    numeric_cols = [
        "volume", "priceChangePercent", "lastPrice", 
        "highPrice", "lowPrice", "quoteVolume"
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    return df

def compute_beauty_score(df, alpha=0.5):
    """
    1) Filter out negative price changes (if desired).
    2) Compute log volume for better scaling.
    3) Combine priceChangePercent + log(volume) into a weighted score.
    
    :param df: DataFrame with columns:
               ['symbol','priceChangePercent','quoteVolume',...]
    :param alpha: Weight for price change in the final score.
                  e.g., alpha=0.5 means 50% price change, 50% volume factor.
    :return: Updated DataFrame with 'beauty_score' column. 
             Note that rows with negative price changes are removed.
    """

    # --- (1) Optionally remove negative price changes ---
    df = df[df["priceChangePercent"] > 0]  # Keep only coins with positive 24h change

    # --- (2) Log-scale the volume to keep it on a similar range ---
    df["volume_log"] = np.log10(df["quoteVolume"] + 1)  # +1 to avoid log(0)

    # --- (3) Weighted sum: alpha * priceChange + (1 - alpha) * volume_log ---
    #     PriceChangePercent might be something like +5.0 or +12.3.
    #     volume_log might be anywhere from 3.0 to 9.0, etc.
    df["beauty_score"] = alpha * df["priceChangePercent"] + (1 - alpha) * df["volume_log"]

    return df


def select_top_symbols(df, quote_symbol="USDT", top_n=5, min_volume=100_000):
    """
    1) Filter for trading pairs that end with quote_symbol (e.g., 'USDT').
    2) Filter out pairs with very low volume.
    3) Exclude stablecoin base assets (USDC, EUR, etc.).
    4) Sort by beauty_score descending, pick the top_n.
    5) Print debug info (top 30 and then top_n).
    """
    # 1) Keep only symbols ending with quote_symbol
    df = df[df["symbol"].str.endswith(quote_symbol)]
    
    # 2) Filter out low-volume pairs
    df = df[df["quoteVolume"] > min_volume]
    
    # 3) Exclude stablecoins from the base asset
    #    (Adjust this set as needed to include any you want to exclude.)
    stable_bases = {"USDC","BUSD","TUSD","DAI","PAX","USDP","EUR","GBP","AUD","UST","FDUSD","EURI","AEUR"}
    # Derive the 'base_asset' by removing the length of quote_symbol from 'symbol'
    df["base_asset"] = df["symbol"].str[:-len(quote_symbol)]
    df = df[~df["base_asset"].isin(stable_bases)]
    
    # 4) Sort by highest beauty_score
    df = df.sort_values("beauty_score", ascending=False)
    
    # 5) Print debug info
    print("\n[DEBUG] All relevant symbols sorted by beauty_score (top 30 shown):")
    print(
        df[["symbol", "base_asset", "priceChangePercent", "quoteVolume", "beauty_score"]]
        .head(100)
        .to_string(index=False)
    )
    
    top_symbols = df["symbol"].head(top_n).tolist()
    
    print(f"\n[DEBUG] Top {top_n} by beauty_score:")
    print(
        df[["symbol", "base_asset", "priceChangePercent", "quoteVolume", "beauty_score"]]
        .head(top_n)
        .to_string(index=False)
    )
    
    return top_symbols



def beauty_contest_bot(quote_symbol="USDT", top_n=5, trade_capital_usdt=100):
    """
    - Each iteration:
      1. Get data for all symbols.
      2. Compute beauty scores.
      3. Select top N.
      4. Buy those N with equal split of 'trade_capital_usdt'.
      5. (Optional) Sell positions not in top N (see example below).
      6. Sleep and repeat.
    """
    while True:
        try:
            # 1) Fetch all ticker info
            df = get_all_tickers_info()
            
            # 2) Compute Beauty Scores
            df = compute_beauty_score(df)
            
            # 3) Select top N & debug print
            top_symbols = select_top_symbols(df, quote_symbol=quote_symbol, top_n=top_n)
            
            # 4) Buy each of the top symbols
            #    (This is a naive example using a fixed portion of 'trade_capital_usdt')
            for symbol in top_symbols:
                last_price = df.loc[df["symbol"] == symbol, "lastPrice"].values[0]
                if last_price > 0:
                    qty = (trade_capital_usdt / top_n) / last_price
                    # round quantity to a reasonable decimal to avoid order errors
                    qty = round(qty, 6)
                    print(f"Buying {qty} {symbol} at ~{last_price} USDT.")
                    place_market_order(symbol, SIDE_BUY, qty)
            
            # 5) (Optional) Sell everything that is NOT in top_symbols
            sell_non_top_positions(top_symbols, quote_symbol)
            
            # 6) Sleep
            time.sleep(3600)  # e.g. 1 hour
            
        except Exception as e:
            print(f"Error in beauty_contest_bot loop: {e}")
            time.sleep(60)


def sell_non_top_positions(top_symbols, quote_symbol="USDT"):
    """
    Example function to sell spot positions that are not in top_symbols.
    1) Fetch current balances.
    2) Construct the symbol with `quote_symbol` (e.g. 'BTCUSDT') for each asset.
    3) If the symbol is not in top_symbols, sell the entire balance.
    """
    try:
        account_info = client.get_account()
        balances = account_info["balances"]
        
        for asset_data in balances:
            asset = asset_data["asset"]
            free_amt = float(asset_data["free"])
            
            # Skip if no free balance or if it's the quote currency (e.g., USDT)
            if free_amt <= 0 or asset == quote_symbol:
                continue
            
            pair = asset + quote_symbol
            # If pair not in top_symbols, let's sell
            if pair not in top_symbols:
                # Sell entire free_amt
                # (Must ensure quantity is within Binance's min trade size.)
                sell_qty = round(free_amt, 6)
                if sell_qty > 0:
                    print(f"Selling {sell_qty} {pair} (not in top_symbols).")
                    place_market_order(pair, SIDE_SELL, sell_qty)
    except Exception as e:
        print(f"Error in sell_non_top_positions: {e}")


if __name__ == "__main__":
    beauty_contest_bot(
        quote_symbol="USDT",
        top_n=20,
        trade_capital_usdt=500  # say we allocate $500 total
    )
