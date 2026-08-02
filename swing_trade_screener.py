"""
NSE Swing Trade Screener
=========================
A rule-based TECHNICAL screener for Indian (NSE) stocks, tuned for swing
trading (holding period: a few days to a few weeks).

WHAT THIS DOES
--------------
1. Downloads daily price/volume history for a list of NSE stocks via yfinance
2. Computes trend, momentum, and volume indicators (SMA, RSI, MACD, ATR)
3. Pulls a few basic fundamentals per stock (P/E, ROE, debt-to-equity)
4. Scores each stock against a combined technical + fundamental rule set
   (0-9: 6 technical checks + 3 fundamental sanity checks)
5. For stocks that pass your score threshold, calculates a suggested
   stop-loss and target using ATR (volatility) and a 2:1 reward:risk ratio
6. Saves a ranked shortlist, with the raw P/E, ROE, and debt figures shown
   alongside the score, to a CSV file

THIS IS NOT FINANCIAL ADVICE
-----------------------------
This is a mechanical filter over public price and fundamentals data. It
knows nothing about news, sector context, results season, or your personal
risk tolerance. It WILL produce false signals - that's true of every
rule-based system, always paper-trade or size small while you validate it.
Treat the output as a shortlist for further research, never as an
instruction to buy or sell. Trading involves real risk of loss, including
losing more than the "stop-loss" if a stock gaps down. The author is not a
SEBI-registered investment adviser and this script is not investment advice.

THE FUNDAMENTAL CHECKS ARE ROUGH, NOT A FULL ANALYSIS
--------------------------------------------------------
They come from yfinance's free data feed (Yahoo Finance), which has
inconsistent coverage for NSE stocks - some fields will be missing (None)
for smaller/less-covered names, which simply fails that one check rather
than crashing. The three checks are deliberately simple sanity filters
(is it profitable at a sane valuation, is it reasonably profitable, is
debt manageable) - not a real fundamental research process. See a proper
source (Screener.in, annual reports) before trusting any single number.

SETUP
-----
    pip install -r requirements.txt

USAGE
-----
    python swing_trade_screener.py
    python swing_trade_screener.py --min-score 5
    python swing_trade_screener.py --tickers my_stocks.csv --period 2y

By default this screens a built-in list of the 50 largest/most liquid NSE
stocks - a reasonable starting universe for swing trading, since very
illiquid stocks are hard to enter/exit cleanly at your intended price.
Index constituents change over time, so treat DEFAULT_TICKERS as a
starting point, not a guaranteed-current index list.

To screen a bigger universe ("all" NSE stocks), pass your own list:
    python swing_trade_screener.py --tickers all_nse_equity.csv
Get the full official list from the NSE website (Market Data > Securities
Available For Trading) and save the symbol column as a one-column CSV
(no header, no .NS suffix needed - the script adds it).
"""

import argparse
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None  # allow the file to be imported for testing without the dependency


NSE_SUFFIX = ".NS"

# The 50 largest/most liquid NSE names (roughly Nifty 50) - trimmed down
# from a longer list so a full run finishes faster. Not a guaranteed-current
# index list - verify against niftyindices.com if exact constituents matter,
# or supply your own (bigger or smaller) list with --tickers.
DEFAULT_TICKERS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR",
    "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK",
    "BAJFINANCE", "ASIANPAINT", "MARUTI", "TITAN", "SUNPHARMA",
    "ULTRACEMCO", "WIPRO", "NESTLEIND", "HCLTECH", "ADANIENT",
    "TATASTEEL", "TATAMOTORS", "POWERGRID", "NTPC", "ONGC", "M&M",
    "JSWSTEEL", "BAJAJFINSV", "TECHM", "INDUSINDBK", "GRASIM", "CIPLA",
    "DRREDDY", "EICHERMOT", "BRITANNIA", "DIVISLAB", "HEROMOTOCO",
    "COALINDIA", "BPCL", "HINDALCO", "SBILIFE", "HDFCLIFE", "APOLLOHOSP",
    "TATACONSUM", "ADANIPORTS", "BAJAJ-AUTO", "UPL", "LTIM",
]


def load_ticker_list(path: Optional[str]) -> List[str]:
    """Load NSE symbols from a one-column CSV, or fall back to the default list."""
    if not path:
        return DEFAULT_TICKERS
    df = pd.read_csv(path, header=None)
    col = df.iloc[:, 0].astype(str).str.strip().str.upper()
    return [t for t in col.tolist() if t and t != "NAN"]


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["SMA20"] = out["Close"].rolling(20).mean()
    out["SMA50"] = out["Close"].rolling(50).mean()
    out["RSI14"] = compute_rsi(out["Close"], 14)
    ema12 = out["Close"].ewm(span=12, adjust=False).mean()
    ema26 = out["Close"].ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACDSignal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["ATR14"] = compute_atr(out["High"], out["Low"], out["Close"], 14)
    out["VolAvg20"] = out["Volume"].rolling(20).mean()
    out["SwingHigh20"] = out["Close"].rolling(20).max()
    return out


def fetch_fundamentals(yf_ticker: str) -> Dict[str, Any]:
    """Fetch a few basic fundamental fields via yfinance's .info.
    Returns {} on any failure so a missing/broken fundamentals fetch
    never crashes the technical screen - it just fails those 3 checks."""
    try:
        info = yf.Ticker(yf_ticker).info or {}
    except Exception:
        return {}
    return {
        "pe": info.get("trailingPE"),
        "roe": info.get("returnOnEquity"),  # raw fraction, e.g. 0.15 = 15%
        # yfinance reports debtToEquity pre-scaled by 100 (e.g. 150.0 means
        # a real debt/equity ratio of 1.5) - NOT a raw ratio like the others.
        "debt_to_equity": info.get("debtToEquity"),
    }


def fundamental_criteria(fund: Dict[str, Any]) -> Dict[str, bool]:
    pe = fund.get("pe")
    roe = fund.get("roe")
    de = fund.get("debt_to_equity")
    return {
        "profitable_reasonable_pe": bool(pe is not None and 0 < pe < 50),
        "healthy_roe_above_12pct": bool(roe is not None and roe > 0.12),
        "manageable_debt_to_equity": bool(de is not None and de < 150),
    }


def score_stock(df: pd.DataFrame, fundamentals: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Apply the combined technical + fundamental rule set to the most
    recent bar. Returns None if there isn't enough history yet, or if
    nothing matched."""
    needed = ["SMA50", "RSI14", "MACD", "MACDSignal", "ATR14"]
    if len(df) < 60 or df[needed].iloc[-1].isna().any():
        return None

    last = df.iloc[-1]
    recent = df.iloc[-6:-1]  # the 5 bars before today

    criteria = {
        "uptrend_vs_sma50": bool(last["Close"] > last["SMA50"]),
        "sma20_above_sma50": bool(last["SMA20"] > last["SMA50"]),
        "rsi_in_range_45_68": bool(45 <= last["RSI14"] <= 68),
        "macd_above_signal": bool(last["MACD"] > last["MACDSignal"]),
        "macd_recent_crossover": bool((recent["MACD"] <= recent["MACDSignal"]).any()),
        "volume_above_avg": bool(pd.notna(last["VolAvg20"]) and last["Volume"] > 1.1 * last["VolAvg20"]),
    }
    fund = fundamentals or {}
    criteria.update(fundamental_criteria(fund))

    score = sum(criteria.values())
    if score == 0:
        return None

    entry = float(last["Close"])
    atr = float(last["ATR14"]) if pd.notna(last["ATR14"]) else None
    if not atr or atr <= 0:
        return None

    stop_loss = round(entry - 1.5 * atr, 2)
    risk = entry - stop_loss
    target = round(entry + 2.0 * risk, 2)
    resistance = float(last["SwingHigh20"]) if pd.notna(last["SwingHigh20"]) else None

    pe = fund.get("pe")
    roe = fund.get("roe")
    de = fund.get("debt_to_equity")

    return {
        "score": score,
        "max_score": len(criteria),
        "close": round(entry, 2),
        "rsi": round(float(last["RSI14"]), 1),
        "pe": round(pe, 1) if pe is not None else None,
        "roe_pct": round(roe * 100, 1) if roe is not None else None,
        "debt_to_equity": round(de / 100, 2) if de is not None else None,
        "stop_loss": stop_loss,
        "target": target,
        "reward_risk": round((target - entry) / risk, 2) if risk > 0 else None,
        "resistance_20d": round(resistance, 2) if resistance else None,
        "criteria_met": ", ".join(k for k, v in criteria.items() if v),
    }


def run_screen(tickers: List[str], period: str, min_score: int) -> pd.DataFrame:
    if yf is None:
        sys.exit("yfinance is not installed. Run: pip install -r requirements.txt")

    yf_tickers = [t + NSE_SUFFIX for t in tickers]
    print(f"Downloading {len(tickers)} stocks (period={period}) - this can take a minute...")
    raw = yf.download(
        tickers=yf_tickers, period=period, group_by="ticker",
        auto_adjust=True, threads=True, progress=False,
    )

    print("Fetching fundamentals (P/E, ROE, debt) - this adds a per-stock "
          "network call, so it's the slower part of the run...")
    rows = []
    for ticker, yf_ticker in zip(tickers, yf_tickers):
        try:
            df = raw if len(yf_tickers) == 1 else raw[yf_ticker].dropna(how="all")
            if df is None or df.empty:
                continue
            ind = compute_indicators(df)
            fund = fetch_fundamentals(yf_ticker)
            result = score_stock(ind, fund)
            if result and result["score"] >= min_score:
                rows.append({"ticker": ticker, **result})
        except Exception as exc:
            print(f"  skipped {ticker}: {exc}")

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    out = out.sort_values(["score", "rsi"], ascending=[False, False]).reset_index(drop=True)
    out.index = out.index + 1
    return out


def main():
    parser = argparse.ArgumentParser(description="NSE swing-trade technical screener (educational, not financial advice)")
    parser.add_argument("--tickers", help="CSV file with one NSE symbol per row (no .NS suffix needed)")
    parser.add_argument("--period", default="1y", help="History window for yfinance, e.g. 6mo, 1y, 2y (default 1y)")
    parser.add_argument("--min-score", type=int, default=6, help="Minimum rule-score out of 9 (6 technical + 3 fundamental) to include (default 6)")
    parser.add_argument("--out", default=None, help="Output CSV path (default: timestamped file)")
    args = parser.parse_args()

    tickers = load_ticker_list(args.tickers)
    results = run_screen(tickers, args.period, args.min_score)

    print("\n" + "=" * 72)
    print("MECHANICAL TECHNICAL SCREEN ONLY - NOT FINANCIAL ADVICE.")
    print("Verify independently before risking money. Markets can lose you money.")
    print("=" * 72 + "\n")

    if results.empty:
        print("No stocks met the minimum score this run. Try a lower --min-score.")
        return

    print(results.to_string())

    out_path = args.out or f"swing_screen_{datetime.now():%Y%m%d_%H%M}.csv"
    results.to_csv(out_path)
    print(f"\nSaved {len(results)} result(s) to {out_path}")


if __name__ == "__main__":
    main()
