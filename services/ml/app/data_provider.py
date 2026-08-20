"""
data_provider.py — single source of truth for price history (hybrid routing).

ONE function, get_history(), routes by exchange:
  * NASDAQ / US symbols  -> Twelve Data  (licensed, reliable, no more 400s)
  * SGX symbols ('.SI')  -> yfinance     (free fallback; occasional 400s tolerated)

Returns the same DataFrame shape the app already expects: Open/High/Low/Close/
Volume, datetime index, chronological. Swapping SGX to a licensed provider later
(e.g. EODHD) = editing only the _sgx branch here. Nothing else in the app changes.

SETUP:
  pip install requests yfinance
  set TWELVEDATA_API_KEY=your_key_here     (in the terminal, NOT in this file)
"""

from __future__ import annotations

import os
import requests
import pandas as pd

_TD_BASE = "https://api.twelvedata.com/time_series"


def _from_twelvedata(symbol: str, start: str, outputsize: int) -> pd.DataFrame:
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        raise RuntimeError("Set TWELVEDATA_API_KEY in your environment first.")
    params = {"symbol": symbol, "interval": "1day", "outputsize": outputsize,
              "start_date": start, "apikey": key, "order": "ASC"}
    data = requests.get(_TD_BASE, params=params, timeout=30).json()
    if isinstance(data, dict) and data.get("status") == "error":
        raise RuntimeError(f"Twelve Data error for '{symbol}': {data.get('message')}")
    if "values" not in data or not data["values"]:
        raise RuntimeError(f"No data returned for '{symbol}'.")
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").set_index("datetime")
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    return df[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]]


def _from_yfinance(symbol: str, start: str) -> pd.DataFrame:
    import yfinance as yf
    raw = yf.download(symbol, start=start, auto_adjust=True, progress=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"No data returned for '{symbol}' (yfinance).")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return raw[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in raw.columns]]


def get_history(symbol: str, start: str = "2020-01-01", outputsize: int = 5000) -> pd.DataFrame:
    """Daily OHLCV, oldest-first. SGX ('.SI') -> yfinance; everything else ->
    Twelve Data. Raises on failure so callers handle bad tickers honestly."""
    if symbol.upper().endswith(".SI"):
        return _from_yfinance(symbol, start)          # Singapore: free fallback for now
    return _from_twelvedata(symbol, start, outputsize)  # NASDAQ/US: licensed, reliable