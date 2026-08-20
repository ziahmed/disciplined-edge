"""
Market-data providers. Phase 1 can use yfinance for backfill; move to a paid
feed (Polygon/Alpha Vantage for NASDAQ, SGX for STI) before launch.

Stubbed so the service imports cleanly.
"""

from __future__ import annotations

import pandas as pd


def load_price_bars(symbol: str, exchange: str) -> pd.DataFrame:
    """Read OHLCV from Postgres/price_bars (preferred) or a provider. TODO."""
    raise NotImplementedError("Wire to price_bars table or a data provider.")
