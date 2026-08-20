"""
train_model.py  —  Build link #1 of the live pipeline.

Trains your XGBoost model on ASML's real history using the SAME leak-free
features you validated, then SAVES it to disk so the server can load it.

The model currently lives only in your notebook's memory and vanishes when the
kernel stops. This script writes it to a file that persists.

WHAT IT SAVES (one bundle, so the server can't accidentally use mismatched parts):
  - the trained model
  - the exact feature list, IN ORDER (critical: the server must feed features
    in the same order the model trained on, or it predicts garbage)
  - the out-of-sample error (used later to size the confidence band)
  - the measured IC / direction accuracy (so the card shows real numbers)

HOW TO RUN (from services/ml, with your .venv active):
    pip install yfinance scikit-learn xgboost joblib pandas numpy
    python train_model.py

It writes:  services/ml/artifacts/ASML.joblib
"""
#pip install yfinance

from __future__ import annotations

import os
import numpy as np
import pandas as pd
import yfinance as yf
import joblib
from xgboost import XGBRegressor

# ── config: keep IDENTICAL to your notebook so training matches validation ──
TICKER       = "ASML"
START        = "2020-01-01"
TARGET_DAYS  = 1          # next-day return (fwd_ret_1)
ARTIFACT_DIR = "artifacts"

# The leak-free, stationary feature set you validated. ORDER MATTERS.
STATIONARY_CORE = [
    "rsi_14", "stoch_k", "stoch_d", "bb_pctb", "macd_hist",
    "fib_dist_382", "fib_dist_500", "fib_dist_618",
    "hist_vol_20", "hist_vol_60",
    # NOTE: excess_ret_qqq, vix_corr_20, sector_ret need QQQ/VIX/sector data.
    # For this FIRST link we use only the single-ticker features so the script
    # runs from one download. We add market-context features in a later link.
    "dow", "month", "quarter",
]


def rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def stoch(high, low, close, n=14):
    ll, hh = low.rolling(n).min(), high.rolling(n).max()
    return 100 * (close - ll) / (hh - ll).replace(0, np.nan)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Same indicators as the notebook, single-ticker subset. Leak-free."""
    c, h, l = df["Close"], df["High"], df["Low"]
    out = pd.DataFrame(index=df.index)

    out["rsi_14"] = rsi(c)
    out["stoch_k"] = stoch(h, l, c)
    out["stoch_d"] = out["stoch_k"].rolling(3).mean()

    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    upper, lower = mid + 2 * sd, mid - 2 * sd
    out["bb_pctb"] = (c - lower) / (upper - lower).replace(0, np.nan)

    ema12, ema26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = ema12 - ema26
    out["macd_hist"] = macd - macd.ewm(span=9).mean()

    hi, lo = h.rolling(60).max(), l.rolling(60).min()
    rng = (hi - lo).replace(0, np.nan)
    for lvl in (0.382, 0.5, 0.618):
        out[f"fib_dist_{int(lvl*1000)}"] = (c - (hi - lvl * rng)) / c

    ret = c.pct_change()
    out["hist_vol_20"] = ret.rolling(20).std() * np.sqrt(252)
    out["hist_vol_60"] = ret.rolling(60).std() * np.sqrt(252)

    out["dow"] = df.index.dayofweek
    out["month"] = df.index.month
    out["quarter"] = df.index.quarter
    return out


def main():
    print(f"Downloading {TICKER} since {START} ...")
    raw = yf.download(TICKER, start=START, auto_adjust=False, progress=False)
    if raw.empty:
        raise SystemExit("No data returned — check your network / ticker.")
    # yfinance sometimes returns multi-index columns; flatten to single level.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    print(f"  got {len(raw)} rows")

    feats = build_features(raw)
    target = raw["Close"].shift(-TARGET_DAYS) / raw["Close"] - 1.0   # seam: t -> t+1

    data = feats.join(target.rename("y")).dropna().sort_index()
    assert data.index.is_monotonic_increasing, "rows not in time order"

    X = data[STATIONARY_CORE].to_numpy()
    y = data["y"].to_numpy()
    print(f"  training rows: {len(data)}  features: {len(STATIONARY_CORE)}")

    # Hold out the last 20% to measure honest out-of-sample error for the band.
    cut = int(len(X) * 0.8)
    model = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
    model.fit(X[:cut], y[:cut])

    oos_pred = model.predict(X[cut:])
    oos_true = y[cut:]
    resid_std = float(np.std(oos_true - oos_pred))     # for the confidence band
    ic = float(pd.Series(oos_pred).corr(pd.Series(oos_true), method="spearman"))
    dacc = float((np.sign(oos_pred) == np.sign(oos_true)).mean())
    print(f"  out-of-sample IC: {ic:+.4f}  dir-acc: {dacc:.4f}  resid_std: {resid_std:.4f}")

    # Refit on ALL data for the live model (more data = better point estimate),
    # but keep the honest OOS error measured above for the band.
    model.fit(X, y)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    path = os.path.join(ARTIFACT_DIR, f"{TICKER}.joblib")
    joblib.dump({
        "model": model,
        "features": STATIONARY_CORE,   # exact order the server must reproduce
        "resid_std": resid_std,
        "ic": ic,
        "dir_acc": dacc,
        "target_days": TARGET_DAYS,
        "trained_on": str(data.index[-1].date()),
    }, path)
    print(f"\nSaved -> {path}")
    print("Link #1 done. The model now exists on disk and can be loaded.")


if __name__ == "__main__":
    main()