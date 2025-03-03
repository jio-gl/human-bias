# Human-Bias Python Strategies

This repository contains **experimental trading strategies** implemented in Python that attempt to exploit various **human biases** in financial markets. All examples use the [**Binance**](https://www.binance.com/) API (via the `python-binance` library) to demonstrate automated trading techniques. These strategies are for **educational purposes only**—they are **not** financial advice, and they carry significant risks if used in live markets.

---

## 1. Overview

We explore three primary strategies, each inspired by a **well-known human or behavioral bias**:

1. **Risk‑Bias Strategy (`risk_bias.py`)**  
   - Formerly described as “Momentum + Pullback (Profit from Quick Profit-Taking).”  
   - Exploits the tendency of traders to **sell winners too quickly** (risk‑averse in gains) and **hold losing trades** (risk‑seeking in losses).  
   - Buys on small dips (in an uptrend) or shorts on small bounces (in a downtrend), then applies an **asymmetric exit** (quick take‑profit vs. larger stop‑loss).

2. **Price Compression / Herding Strategy**  
   - Looks for assets whose prices have “compressed” future upside into the present due to crowd mania.  
   - Short potential “blow‑off tops” once the crowd’s expectation seems overstretched, or ride early mania with tight stops.  

3. **Beauty Contest Strategy (`beauty.py`)**  
   - Attempts to pick assets **not** based on fundamentals alone, but on what the **crowd** thinks the “prettiest” coins will be.  
   - Focuses on **momentum + volume** or other popularity indicators (e.g., social media), aiming to catch short‑term hype.  

---

## 2. Prerequisites

1. **Python 3.7+** installed  
2. **Binance API Keys** (with Spot trading enabled)  
3. `pip install python-binance pandas numpy`

> **Note:** Always secure your API keys. Do **not** commit them to public repositories.

---

## 3. Code Structure

- **`get_all_tickers_info()`**  
  Fetches 24‑hour ticker stats (price changes, volumes, etc.) for all symbols on Binance.
- **`compute_beauty_score(df, alpha=0.5)`**  
  Calculates a “beauty_score” for each symbol based on **(alpha × priceChangePercent) + ((1−alpha) × log(volume))**.  
  - By default, it **filters out** symbols with negative returns.  
  - Uses **log(volume)** to keep large numbers on a comparable scale.
- **`select_top_symbols(df, quote_symbol="USDT", top_n=5, min_volume=100_000)`**  
  - Filters out stablecoins and low‑volume pairs.  
  - Sorts by **beauty_score** in descending order.  
  - Returns the top N symbols. Also prints debug info (the top 30 or 100 for transparency).
- **`beauty_contest_bot(quote_symbol="USDT", top_n=5, trade_capital_usdt=100)`**  
  - Main loop that:  
    1. Fetches ticker data  
    2. Computes the beauty score  
    3. Selects the top N symbols  
    4. Buys them equally with your specified capital  
    5. (Optionally) sells everything else that isn’t in the top picks  
    6. Waits and repeats (by default, after an hour)
- **`sell_non_top_positions(top_symbols, quote_symbol="USDT")`**  
  - Sells any spot positions you hold that are **not** in the top symbols list, converting them back to USDT.  

---

## 4. The “Beauty Contest” Strategy (`beauty.py`)

John Maynard Keynes likened markets to a **“newspaper beauty contest,”** where success requires guessing **not** what you personally find pretty, but what you believe the **majority** of other participants will find pretty. Translated into modern crypto markets, this means:

- **We aren’t purely picking “fundamentally strong” coins.**  
- **We’re picking coins that the crowd (i.e., other traders) will likely push higher** in the short term, often due to hype or FOMO.

### Key Components

1. **24h Price Change**  
   - A proxy for short‑term momentum or hype.  
   - Coins with higher positive returns often get more attention, attracting even more buyers.

2. **Volume (Log-Scaled)**  
   - Measures market interest and liquidity.  
   - Taking the logarithm ensures we don’t let extremely high volumes dominate everything.

3. **Beauty Score**  
   - **Score = α×(Price Change %) + (1−α)×(Log Volume)**  
   - Higher = more “attractive” to the crowd right now.  
   - We sort the entire symbol universe by this score, pick the top 5, 10, or 20.

4. **Filtering Out Negative Changes**  
   - We remove symbols whose 24h changes are negative.  
   - Our aim is to only ride momentum in coins that are already trending up.

---

## 5. Usage

1. **Clone or Download** this repo.
2. **Install dependencies**:  
   ```bash
   pip install python-binance pandas numpy
   ```
3. **Edit the code** to:
   - Insert your **Binance API key** and **secret**.  
   - Adjust parameters (like `top_n`, `trade_capital_usdt`, or `time.sleep(3600)` for different intervals).  
4. **Run** the bot:
   ```bash
   python beauty.py
   ```
   By default, it will loop every hour, buying the top picks and selling any non‑top holdings.

> **Always test with small capital or on a testnet** if you can. Consider building in more robust error‑handling or risk management (e.g., stop‑losses).

---

## 6. Risk-Bias Strategy (`risk_bias.py`)

A script that **buys small dips** in an uptrend or **shorts small bounces** in a downtrend. It then **exits winners quickly** (risk‑averse in gains) but **holds losing trades longer** (risk‑seeking in losses), thus featuring **asymmetric risk**.  
- **Entry**: Compare short vs. long moving averages to identify trend; wait for a small pullback or bounce to confirm the entry.  
- **Exit**: Rapid take‑profit on small gains, but a larger stop‑loss for losers, reflecting the common human bias of **“Let me see if it recovers!”**  

> *Adapt for margin/futures if you want a true short. On spot alone, shorting requires you to already hold the asset or use margin endpoints.*

---

## 7. Disclaimer

- **No Financial Advice**: These strategies are purely experimental. They can **lose money**.  
- **Volatile Markets**: Crypto markets can have large and sudden price movements, magnifying risk.  
- **Use at Own Risk**: You are responsible for your trades. Test thoroughly before using real funds.  

---

## 8. License & Contributions

- The code in this repository is provided under an [MIT License](https://opensource.org/licenses/MIT).  
- Contributions and improvements are welcome—feel free to submit pull requests or open issues.

