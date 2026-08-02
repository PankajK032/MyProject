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
import os
import sys
import urllib.parse
import urllib.request
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


def generate_html_report(df: pd.DataFrame, total_screened: int, run_date: str) -> str:
    """Render results as a small, self-contained HTML report - no JS, no
    external data calls at view-time - suitable for GitHub Pages. Fonts
    load from Google Fonts at view-time (fine for a real hosted page)."""

    def fmt(v, suffix=""):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return f"{v}{suffix}"

    sprockets = "".join("<span></span>" for _ in range(10))

    if df.empty:
        section = """
        <div class="empty">
          <p class="empty-tag">NO SIGNALS TODAY</p>
          <p>No stock cleared the bar on this run. That means the rules found
          nothing worth flagging - not that something broke. Check back after
          the next run.</p>
        </div>"""
        count_line = f"0 of {total_screened} stocks cleared the bar"
    else:
        cards = []
        for _, r in df.iterrows():
            cards.append(f"""
        <div class="card">
          <div class="card-top">
            <span class="ticker">{r['ticker']}</span>
            <span class="score">{int(r['score'])}/{int(r['max_score'])}</span>
          </div>
          <div class="levels">
            <div class="level stop"><div class="label">Stop-loss</div><div class="value">\u20b9{fmt(r.get('stop_loss'))}</div></div>
            <div class="level"><div class="label">Buy</div><div class="value">\u20b9{fmt(r.get('close'))}</div></div>
            <div class="level target"><div class="label">Target</div><div class="value">\u20b9{fmt(r.get('target'))}</div></div>
          </div>
          <div class="fundamentals">
            <span>RSI {fmt(r.get('rsi'))}</span>
            <span>P/E {fmt(r.get('pe'))}</span>
            <span>ROE {fmt(r.get('roe_pct'), '%')}</span>
            <span>D/E {fmt(r.get('debt_to_equity'))}</span>
          </div>
        </div>""")
        section = f'<div class="cards">{"".join(cards)}</div>'
        count_line = f"{len(df)} of {total_screened} stocks cleared the bar"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NSE Swing Screen</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper: #F7F8F3; --stripe: #E9EEE2; --ink: #1C2B22;
    --ink-muted: #5B6B5E; --green: #1F7A4D; --rust: #A13D2B; --rule: #C9D2C0;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: 'Inter', system-ui, sans-serif; padding: 0 0 4rem;
  }}
  .masthead {{ padding: 2.5rem 1.25rem 1.75rem; text-align: center; border-bottom: 1px solid var(--rule); }}
  .sprockets {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 1.5rem; }}
  .sprockets span {{ width: 6px; height: 6px; border-radius: 50%; background: var(--rule); }}
  .masthead h1 {{
    font-family: 'JetBrains Mono', monospace; font-size: 1.3rem; letter-spacing: 0.08em;
    text-transform: uppercase; margin: 0 0 0.6rem; font-weight: 700;
  }}
  .masthead .meta {{ font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--ink-muted); }}
  .rule-note {{ max-width: 460px; margin: 1.1rem auto 0; font-size: 0.8rem; color: var(--ink-muted); line-height: 1.55; }}
  .cards {{ max-width: 480px; margin: 1.5rem auto 0; padding: 0 1.25rem; display: flex; flex-direction: column; gap: 12px; }}
  .card {{ background: #fff; border: 1px solid var(--rule); border-radius: 10px; padding: 1rem 1.1rem; }}
  .card:nth-child(even) {{ background: var(--stripe); }}
  .card-top {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.8rem; }}
  .ticker {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 1.05rem; letter-spacing: 0.02em; }}
  .score {{ font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--ink-muted); }}
  .levels {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 0.7rem; }}
  .level {{ text-align: center; }}
  .level .label {{ font-size: 0.63rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-muted); margin-bottom: 2px; }}
  .level .value {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.95rem; }}
  .level.stop .value {{ color: var(--rust); }}
  .level.target .value {{ color: var(--green); }}
  .fundamentals {{
    display: flex; gap: 14px; font-size: 0.72rem; color: var(--ink-muted);
    border-top: 1px dashed var(--rule); padding-top: 0.6rem;
    font-family: 'JetBrains Mono', monospace; flex-wrap: wrap;
  }}
  .empty {{ max-width: 420px; margin: 3rem auto 0; padding: 0 1.25rem; text-align: center; color: var(--ink-muted); line-height: 1.6; }}
  .empty-tag {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; letter-spacing: 0.05em; color: var(--ink); }}
  .footer {{
    max-width: 480px; margin: 2.5rem auto 0; padding: 1rem 1.25rem 0; font-size: 0.72rem;
    color: var(--ink-muted); line-height: 1.6; border-top: 1px solid var(--rule);
  }}
</style>
</head>
<body>
  <div class="masthead">
    <div class="sprockets">{sprockets}</div>
    <h1>NSE Swing Screen</h1>
    <div class="meta">{run_date} IST &middot; {count_line}</div>
    <div class="rule-note">Target is always set 2x farther from the buy price than the stop-loss (2:1 reward-to-risk). Score out of 9: 6 technical checks plus 3 fundamental sanity checks.</div>
  </div>
  {section}
  <div class="footer">
    Mechanical rule-based screen, not financial advice. Not a SEBI-registered adviser - verify independently before risking money. Fundamentals are rough, free-data sanity checks, not full research.
  </div>
</body>
</html>"""


def format_telegram_summary(df: pd.DataFrame, total_screened: int, run_date: str, max_lines: int = 15) -> str:
    """Plain-text (HTML-lite) summary suitable for a Telegram message.
    Capped at max_lines stocks so a big pass-count can never exceed
    Telegram's 4096-character message limit."""
    header = f"<b>NSE Swing Screen</b> \u2014 {run_date} IST"
    if df.empty:
        return f"{header}\n0 of {total_screened} stocks cleared the bar today. No signals, nothing to act on."

    shown = df.head(max_lines)
    parts = [header, f"{len(df)} of {total_screened} stocks cleared the bar:"]
    for _, r in shown.iterrows():
        parts.append(
            f"\n<b>{r['ticker']}</b>  ({int(r['score'])}/{int(r['max_score'])})\n"
            f"Buy \u20b9{r['close']}  |  SL \u20b9{r['stop_loss']}  |  Target \u20b9{r['target']}"
        )
    if len(df) > max_lines:
        parts.append(f"\n+ {len(df) - max_lines} more \u2014 see the full report on GitHub.")
    parts.append("\nMechanical rule-based screen, not financial advice.")
    return "\n".join(parts)


def send_telegram_message(text: str) -> None:
    """Send a message via a Telegram bot, if TELEGRAM_BOT_TOKEN and
    TELEGRAM_CHAT_ID are set as environment variables. Silently skips
    (with a printed note) if not configured, and never raises - a failed
    notification should never cause the screen itself to fail."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set) - skipping notification.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()

    try:
        request = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=15) as resp:
            resp.read()
        print("Telegram notification sent.")
    except Exception as exc:
        print(f"Telegram notification failed (results are still saved to CSV/HTML): {exc}")


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

    if not results.empty:
        print(results.to_string())
    else:
        print("No stocks met the minimum score this run. Try a lower --min-score.")

    out_path = args.out or f"swing_screen_{datetime.now():%Y%m%d_%H%M}.csv"
    results.to_csv(out_path)
    print(f"\nSaved {len(results)} result(s) to {out_path}")

    html = generate_html_report(results, len(tickers), datetime.now().strftime("%d %b %Y, %H:%M"))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote index.html (open it in a browser, or publish via GitHub Pages)")

    telegram_text = format_telegram_summary(results, len(tickers), datetime.now().strftime("%d %b %Y, %H:%M"))
    send_telegram_message(telegram_text)


if __name__ == "__main__":
    main()
