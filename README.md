# Human-Bias Python Strategies

This repository contains **experimental trading strategies** implemented in Python that attempt to exploit various **human biases** in financial markets. All examples use the [**Binance**](https://www.binance.com/) API (via the `python-binance` library) to demonstrate automated trading techniques. These strategies are for **educational purposes only**—they are **not** financial advice, and they carry significant risks if used in live markets.

---

## 1. Overview

We explore three primary strategies, each inspired by a **well-known human or behavioral bias**:

1. **Risk‑Bias Strategy (`risk_bias.py`)**  
   - Formerly described as “Momentum + Pullback (Profit from Quick Profit-Taking).”  
   - Exploits the tendency of traders to **sell winners too quickly** (risk‑averse in gains) and **hold losing trades** (risk‑seeking in losses).  
   - Buys on small dips (in an uptrend) or shorts on small bounces (in a downtrend), then applies an **asymmetric exit** (quick take‑profit vs. larger stop‑loss).

2. **Price Compression / Herding Strategy (`herding_mania.py`)**  
   - Identifies assets whose prices have “compressed” future upside into the present (crowd mania).  
   - **Short** potential “blow‑off tops” once the market’s expectation appears overstretched, or **ride early mania** with tight stops.  
   - Uses indicators like moving averages, RSI, or volume spikes to detect mania and time entries/exits.

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

## Risk-Bias Strategy (`risk_bias.py`)

A script that **buys small dips** in an uptrend or **shorts small bounces** in a downtrend. It then **exits winners quickly** (risk‑averse in gains) but **holds losing trades longer** (risk‑seeking in losses), thus featuring **asymmetric risk**.

### Key Components

1. **Trend Detection**  
   - Compare short vs. long moving averages (e.g., 5 vs. 15 periods).  
   - **Uptrend** if short MA > long MA, **Downtrend** otherwise.

2. **Pullback / Bounce Entry**  
   - In an uptrend, wait for a **small dip** from the recent high.  
   - In a downtrend, wait for a **small bounce** off the recent low.

3. **Asymmetric Exit**  
   - **Quick Take‑Profit**: If the trade moves slightly in your favor, exit early (reflecting “don’t lose those gains!”).  
   - **Wider Stop‑Loss**: If it goes against you, hold longer in hopes it recovers (reflecting “it might come back!”).

> *Adapt for margin/futures if you want a true short. On spot alone, shorting requires you to already hold the asset or use margin endpoints.*

---

## Price Compression / Herding Strategy (`herding_mania.py`)

In this approach, we look for **“mania”** or **“bubble”** conditions where future upside seems **compressed** into the current price due to **crowd excitement**:

### Key Components

1. **Mania Detection**  
   - Short‑term MA is significantly above the long‑term MA (e.g., 20%+).  
   - **RSI** or other momentum oscillator is in overbought territory.

2. **Ride Early Mania**  
   - If indicators suggest the mania is still building—price is rising fast, RSI not yet extreme—open a **long** position to catch further upside.

3. **Short Blow‑Off Tops**  
   - Once RSI is high and price stalls below the short MA, open a **short** or exit your position, anticipating a sharp correction.

> *For a true short position, you need **margin** or **futures**. Spot trades alone can’t short unless you already hold the asset.*

---

## The “Beauty Contest” Strategy (`beauty.py`)

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

## 8. Disclaimer

- **No Financial Advice**: These strategies are purely experimental. They can **lose money**.  
- **Volatile Markets**: Crypto markets can have large and sudden price movements, magnifying risk.  
- **Use at Own Risk**: You are responsible for your trades. Test thoroughly before using real funds.  

---

## 9. License & Contributions

- The code in this repository is provided under an [MIT License](https://opensource.org/licenses/MIT).  
- Contributions and improvements are welcome—feel free to submit pull requests or open issues.

