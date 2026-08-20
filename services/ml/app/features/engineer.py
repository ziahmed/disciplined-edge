"""
Feature engineering — port your notebook's engineer_features() here.

Pure pandas/numpy indicators (SMA/EMA/RSI/MACD/Bollinger/ATR/OBV/Stochastic/
Fibonacci) + volatility + fundamentals join + market context + calendar.
Kept as a stub so the service imports cleanly before the port.
"""

from __future__ import annotations

import pandas as pd


def engineer_features(bars: pd.DataFrame, meta: dict | None = None) -> pd.DataFrame:
    """Return a model-ready feature frame for one security. TODO: port notebook."""
    raise NotImplementedError("Port engineer_features() from the notebook.")
