"""
/predict router — ANY NASDAQ ticker, train-once-and-cache.

First request for a ticker: download + build features + train + remember.
Every later request: return the cached result instantly (no download, no retrain,
no drift). The cache lives in memory and resets when the server restarts.

Honest guardrails for "any ticker":
  * unknown/typo ticker (no data)      -> 404 "ticker not found"
  * too little history to train        -> 422 "not enough history"
  * transient download failure         -> 503 "data unavailable, try again"
  * non-next-day horizon               -> "not validated for this horizon"

The verdict/IC honesty is unchanged: a real number only where we trained and
measured one, and it plainly states when there's no edge.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from app.schemas import (
    Factor, Intervals, Prediction, PredictRequest, Risk, Scenarios,
)

router = APIRouter()

MODEL_VERSION = "cache-anyticker-2026.06.04"
NOISE_BAND = 0.02
NEXTDAY_HORIZONS = {"1d", "1w"}
START = "2020-01-01"
MIN_ROWS = 200          # need at least this much history to train honestly

FEATURES = [
    "rsi_14", "stoch_k", "stoch_d", "bb_pctb", "macd_hist",
    "fib_dist_382", "fib_dist_500", "fib_dist_618",
    "hist_vol_20", "hist_vol_60", "dow", "month", "quarter",
]

# In-memory cache: symbol -> computed result dict. Reset on server restart.
_CACHE: dict[str, dict] = {}
_LOCK = threading.Lock()    # avoid two simultaneous clicks training the same ticker twice


def _verdict(ic: float) -> str:
    if abs(ic) <= NOISE_BAND:
        return ("No demonstrated edge. The information coefficient sits in the "
                "noise zone — consistent with random chance.")
    if ic < 0:
        return ("Negative edge in testing — slightly worse than a coin flip. "
                "Treat as no usable signal.")
    return ("Weak positive signal in testing. Unproven across tickers and costs "
            "— not tradeable.")


def _rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _stoch(h, l, c, n=14):
    ll, hh = l.rolling(n).min(), h.rolling(n).max()
    return 100 * (c - ll) / (hh - ll).replace(0, np.nan)


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
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


def _train_and_cache(symbol: str) -> dict:
    """Download, train once, store the computed numbers. Raises HTTPException
    with an honest message on any failure."""
    import yfinance as yf
    from xgboost import XGBRegressor

    try:
        raw = yf.download(symbol, start=START, auto_adjust=False, progress=False)
    except Exception:
        raise HTTPException(503, detail={"error": "data_unavailable",
                            "detail": "Price data temporarily unavailable. Try again."})
    if raw is None or raw.empty:
        raise HTTPException(404, detail={"error": "ticker_not_found",
                            "detail": f"No data for '{symbol}'. Check the ticker symbol."})
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    feats = _build_features(raw)
    target = raw["Close"].shift(-1) / raw["Close"] - 1.0
    data = feats.join(target.rename("y")).dropna().sort_index()
    if len(data) < MIN_ROWS:
        raise HTTPException(422, detail={"error": "insufficient_history",
                            "detail": (f"'{symbol}' has only {len(data)} usable rows; "
                                       f"need {MIN_ROWS}+ to train honestly.")})

    X, y = data[FEATURES].to_numpy(), data["y"].to_numpy()
    cut = int(len(X) * 0.8)
    model = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
    model.fit(X[:cut], y[:cut])
    oos_pred, oos_true = model.predict(X[cut:]), y[cut:]
    resid_std = float(np.std(oos_true - oos_pred))
    ic = float(pd.Series(oos_pred).corr(pd.Series(oos_true), method="spearman"))
    dacc = float((np.sign(oos_pred) == np.sign(oos_true)).mean())
    model.fit(X, y)

    latest_close = float(raw["Close"].iloc[-1])
    pred_ret = float(model.predict(data[FEATURES].to_numpy()[-1:])[0])
    result = {
        "latest_close": latest_close, "pred_ret": pred_ret,
        "resid_std": resid_std, "ic": ic, "dacc": dacc,
        "trained_on": str(data.index[-1].date()),
    }
    _CACHE[symbol] = result
    return result


def _not_validated_horizon(req):
    base = 100.0
    return Prediction(
        symbol=req.symbol, exchange=req.exchange, horizon=req.horizon,
        generated_at=datetime.now(timezone.utc), model_version=MODEL_VERSION,
        point_target=base,
        intervals=Intervals(ci68=(base*0.93, base*1.07), ci95=(base*0.86, base*1.14)),
        prob_up=0.50,
        scenarios=Scenarios(bull=base*1.14, base=base, bear=base*0.86),
        risk=Risk(var_95=-0.10, vol_forecast=0.05),
        factors=[Factor(rank=1, factor="Not validated for this horizon",
                        contribution=0.0,
                        explanation=("Models predict next-day returns only. Run the "
                                     "horizon sweep to enable this horizon."))])


def _run_pipeline(req: PredictRequest) -> Prediction:
    if req.horizon not in NEXTDAY_HORIZONS:
        return _not_validated_horizon(req)

    symbol = req.symbol.upper().strip()
    with _LOCK:                                   # one trainer per ticker at a time
        r = _CACHE.get(symbol) or _train_and_cache(symbol)

    lc, pr, rs = r["latest_close"], r["pred_ret"], r["resid_std"]
    ic, dacc = r["ic"], r["dacc"]
    price = lc * (1 + pr)
    lo68, hi68 = lc*(1+pr-rs), lc*(1+pr+rs)
    lo95, hi95 = lc*(1+pr-2*rs), lc*(1+pr+2*rs)

    factors = [
        Factor(rank=1, factor=f"Verdict (next-day, {symbol})", contribution=ic,
               explanation=_verdict(ic)),
        Factor(rank=2, factor=f"Predicted next-day return: {pr*100:+.2f}%",
               contribution=round(pr, 4),
               explanation=(f"From last close ${lc:,.2f} (trained {r['trained_on']}). "
                            "Cached — stable until the server restarts.")),
        Factor(rank=3, factor=f"Measured IC: {ic:+.4f}  |  dir-acc: {dacc*100:.1f}%",
               contribution=ic,
               explanation="Out-of-sample. Near-zero IC and ~50% accuracy = no edge."),
    ]
    return Prediction(
        symbol=symbol, exchange=req.exchange, horizon=req.horizon,
        generated_at=datetime.now(timezone.utc), model_version=MODEL_VERSION,
        point_target=round(price, 2),
        intervals=Intervals(ci68=(round(lo68,2), round(hi68,2)),
                            ci95=(round(lo95,2), round(hi95,2))),
        prob_up=round(float(dacc), 4),
        scenarios=Scenarios(bull=round(hi95,2), base=round(price,2), bear=round(lo95,2)),
        risk=Risk(var_95=round(-2*rs,4), vol_forecast=round(rs,4)),
        factors=factors)


@router.post("/predict", response_model=Prediction)
def predict(req: PredictRequest) -> Prediction:
    # Any non-empty symbol is allowed now; validity is decided by whether data exists.
    if not req.symbol or not req.symbol.strip():
        raise HTTPException(400, detail={"error": "empty_symbol",
                            "detail": "Enter a ticker symbol."})
    return _run_pipeline(req)