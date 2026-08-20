"""
train_all.py  —  Train and save models for ALL validated tickers in one run.

Replaces the hand-edit-and-rerun loop. Run ONCE, offline, separate from the
server:

    cd services/ml
    .venv\\Scripts\\activate          (Windows)   or   source .venv/bin/activate
    pip install yfinance scikit-learn xgboost joblib pandas numpy
    python train_all.py

It trains each ticker on its real history with the SAME leak-free features,
saves artifacts/<TICKER>.joblib, and prints one summary table so you can see
all four honest ICs side by side.

Why this is a script and NOT inside main.py: training is a heavy, occasional
job (download years of data, fit models). Serving is fast and constant. Keeping
them separate means the server starts instantly and never re-trains on a restart.
The server just loads whatever .joblib files this script produced.
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
import yfinance as yf
import joblib
from xgboost import XGBRegressor

# ── which tickers to train (SLV intentionally excluded — not validated) ──
TICKERS      = ["ASML", "TSLA", "INTC", "IONQ"]
START        = "2020-01-01"
TARGET_DAYS  = 1
ARTIFACT_DIR = "artifacts"

FEATURES = [
    "rsi_14", "stoch_k", "stoch_d", "bb_pctb", "macd_hist",
    "fib_dist_382", "fib_dist_500", "fib_dist_618",
    "hist_vol_20", "hist_vol_60",
    "dow", "month", "quarter",
]


def _rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _stoch(h, l, c, n=14):
    ll, hh = l.rolling(n).min(), h.rolling(n).max()
    return 100 * (c - ll) / (hh - ll).replace(0, np.nan)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    c, h, l = df["Close"], df["High"], df["Low"]
    out = pd.DataFrame(index=df.index)
    out["rsi_14"] = _rsi(c)
    out["stoch_k"] = _stoch(h, l, c)
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


def train_one(ticker: str) -> dict:
    raw = yf.download(ticker, start=START, auto_adjust=False, progress=False)
    if raw.empty:
        return {"ticker": ticker, "status": "NO DATA", "ic": None, "dacc": None, "rows": 0}
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    feats = build_features(raw)
    target = raw["Close"].shift(-TARGET_DAYS) / raw["Close"] - 1.0
    data = feats.join(target.rename("y")).dropna().sort_index()
    if not data.index.is_monotonic_increasing:
        return {"ticker": ticker, "status": "ORDER ERR", "ic": None, "dacc": None, "rows": len(data)}

    X, y = data[FEATURES].to_numpy(), data["y"].to_numpy()
    cut = int(len(X) * 0.8)
    model = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
    model.fit(X[:cut], y[:cut])
    oos_pred, oos_true = model.predict(X[cut:]), y[cut:]
    resid_std = float(np.std(oos_true - oos_pred))
    ic = float(pd.Series(oos_pred).corr(pd.Series(oos_true), method="spearman"))
    dacc = float((np.sign(oos_pred) == np.sign(oos_true)).mean())

    model.fit(X, y)  # refit on all data for the live model
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "resid_std": resid_std,
                 "ic": ic, "dir_acc": dacc, "target_days": TARGET_DAYS,
                 "trained_on": str(data.index[-1].date())},
                os.path.join(ARTIFACT_DIR, f"{ticker}.joblib"))
    return {"ticker": ticker, "status": "OK", "ic": ic, "dacc": dacc, "rows": len(data)}


def main():
    print(f"Training {len(TICKERS)} tickers: {', '.join(TICKERS)}\n")
    results = []
    for t in TICKERS:
        print(f"  {t} ...", end=" ", flush=True)
        try:
            r = train_one(t)
        except Exception as e:
            r = {"ticker": t, "status": f"ERROR {type(e).__name__}", "ic": None, "dacc": None, "rows": 0}
        results.append(r)
        print(r["status"])

    print("\n" + "=" * 52)
    print(f"{'ticker':<7}{'status':<12}{'rows':>6}{'IC':>10}{'dir_acc':>9}")
    print("-" * 52)
    for r in results:
        ic = f"{r['ic']:+.4f}" if r["ic"] is not None else "   --"
        da = f"{r['dacc']:.4f}" if r["dacc"] is not None else "  --"
        print(f"{r['ticker']:<7}{r['status']:<12}{r['rows']:>6}{ic:>10}{da:>9}")
    print("=" * 52)

    ics = [r["ic"] for r in results if r["ic"] is not None]
    if ics:
        print(f"mean IC across {len(ics)} tickers: {np.mean(ics):+.4f}")
        print(f"spread: {min(ics):+.4f} .. {max(ics):+.4f}")
    print("\nDone. The server will load these on the next prediction request —")
    print("no restart needed. Pick each ticker on the page (horizon '1 week').")


if __name__ == "__main__":
    main()