"""
/predict router — walk-forward IC, train-once-and-cache, with robust band math.

Fixes the 500 (ValidationError: point_target must lie inside the 68% interval):
  * guards against NaN/inf in predicted return and residual std
  * clamps rounded band edges so the point ALWAYS sits inside ci68 / ci95
    (rounding each value independently could push the point a cent outside)

Pipeline per (uncached) ticker: download -> features -> 5-fold walk-forward IC
(+ shuffled control) -> band from OOS residual std -> refit -> latest price.
Cached in memory; later requests are instant.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from app.schemas import (
    Factor, Intervals, Prediction, PredictRequest, Risk, Scenarios,
)

router = APIRouter()

MODEL_VERSION = "walkforward-anyticker-2026.06.05"
NOISE_BAND = 0.02
NEXTDAY_HORIZONS = {"1d", "1w"}
START = "2020-01-01"
MIN_ROWS = 200
N_SPLITS = 5

FEATURES = [
    "rsi_14", "stoch_k", "stoch_d", "bb_pctb", "macd_hist",
    "fib_dist_382", "fib_dist_500", "fib_dist_618",
    "hist_vol_20", "hist_vol_60", "dow", "month", "quarter",
]

_CACHE: dict[str, dict] = {}
_LOCK = threading.Lock()


def _verdict(ic: float, ctrl_ok: bool) -> str:
    if not ctrl_ok:
        return ("Validation control failed for this ticker — the IC may be "
                "contaminated. Treat the result as unreliable.")
    if abs(ic) <= NOISE_BAND:
        return ("No demonstrated edge. Walk-forward IC sits in the noise zone — "
                "consistent with random chance.")
    if ic < 0:
        return ("Negative edge in walk-forward testing — worse than a coin flip. "
                "No usable signal.")
    return ("Positive walk-forward signal. Still unproven against costs and across "
            "more tickers — promising, not tradeable yet.")


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


def _spearman(p, a):
    p, a = pd.Series(p), pd.Series(a)
    m = p.notna() & a.notna()
    return float(p[m].corr(a[m], method="spearman")) if m.sum() >= 3 else 0.0


def _walk_forward(X, y, n_splits=N_SPLITS):
    from xgboost import XGBRegressor
    n = len(X)
    fold = n // (n_splits + 1)
    preds, actuals = [], []
    for k in range(1, n_splits + 1):
        tr, te = fold * k, fold * (k + 1)
        m = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
        m.fit(X[:tr], y[:tr])
        preds.extend(m.predict(X[tr:te]).tolist())
        actuals.extend(y[tr:te].tolist())
    preds, actuals = np.array(preds), np.array(actuals)
    ic = _spearman(preds, actuals)
    dacc = float((np.sign(preds) == np.sign(actuals)).mean())
    resid = actuals - preds
    resid = resid[np.isfinite(resid)]                  # drop any NaN/inf
    resid_std = float(np.std(resid)) if len(resid) else 0.0
    return ic, dacc, resid_std


def _safe(x, default=0.0):
    """Return a finite float, or `default` if x is NaN/inf/None."""
    try:
        xf = float(x)
        return xf if math.isfinite(xf) else default
    except (TypeError, ValueError):
        return default


def _train_and_cache(symbol: str) -> dict:
    from app.data_provider import get_history          # licensed/hybrid source
    from xgboost import XGBRegressor

    try:
        raw = get_history(symbol, start=START)
    except Exception as e:
        raise HTTPException(404, detail={"error": "ticker_not_found",
                            "detail": f"No data for '{symbol}': {e}"})
    if raw is None or raw.empty:
        raise HTTPException(404, detail={"error": "ticker_not_found",
                            "detail": f"No data for '{symbol}'."})

    feats = _build_features(raw)
    target = raw["Close"].shift(-1) / raw["Close"] - 1.0
    data = feats.join(target.rename("y")).dropna().sort_index()
    if len(data) < MIN_ROWS:
        raise HTTPException(422, detail={"error": "insufficient_history",
                            "detail": f"'{symbol}' has only {len(data)} usable rows."})
    assert data.index.is_monotonic_increasing

    X, y = data[FEATURES].to_numpy(), data["y"].to_numpy()
    ic, dacc, resid_std = _walk_forward(X, y)
    y_shuf = y.copy(); np.random.default_rng(0).shuffle(y_shuf)
    ctrl_ic, _, _ = _walk_forward(X, y_shuf)
    ctrl_ok = abs(_safe(ctrl_ic)) <= NOISE_BAND

    final = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
    final.fit(X, y)
    latest_close = _safe(raw["Close"].iloc[-1])
    pred_ret = _safe(final.predict(data[FEATURES].to_numpy()[-1:])[0])

    # resid_std must be a sane, positive, finite band width.
    resid_std = _safe(resid_std, 0.02)
    if resid_std <= 0:
        resid_std = 0.02

    result = {
        "latest_close": latest_close, "pred_ret": pred_ret, "resid_std": resid_std,
        "ic": _safe(ic), "dacc": _safe(dacc, 0.5), "ctrl_ic": _safe(ctrl_ic),
        "ctrl_ok": ctrl_ok, "trained_on": str(data.index[-1].date()),
        "n_rows": len(data),
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
    with _LOCK:
        r = _CACHE.get(symbol) or _train_and_cache(symbol)

    lc, pr, rs = r["latest_close"], r["pred_ret"], r["resid_std"]
    ic, dacc, ctrl_ic, ctrl_ok = r["ic"], r["dacc"], r["ctrl_ic"], r["ctrl_ok"]

    # Build the point and band, then ROUND with clamping so the point can never
    # land outside its own interval (this is what caused the 500).
    point = round(lc * (1 + pr), 2)
    raw_lo68, raw_hi68 = lc * (1 + pr - rs), lc * (1 + pr + rs)
    raw_lo95, raw_hi95 = lc * (1 + pr - 2*rs), lc * (1 + pr + 2*rs)
    lo68 = min(round(raw_lo68, 2), point)
    hi68 = max(round(raw_hi68, 2), point)
    lo95 = min(round(raw_lo95, 2), lo68)
    hi95 = max(round(raw_hi95, 2), hi68)

    factors = [
        Factor(rank=1, factor=f"Verdict (next-day, {symbol})", contribution=round(ic, 4),
               explanation=_verdict(ic, ctrl_ok)),
        Factor(rank=2, factor=f"Predicted next-day return: {pr*100:+.2f}%",
               contribution=round(pr, 4),
               explanation=(f"From last close ${lc:,.2f} (trained {r['trained_on']}, "
                            f"{r['n_rows']} rows). Cached — stable until restart.")),
        Factor(rank=3, factor=f"Walk-forward IC: {ic:+.4f}  |  dir-acc: {dacc*100:.1f}%",
               contribution=round(ic, 4),
               explanation=("5-fold out-of-sample — the trustworthy grader. "
                            f"Control IC {ctrl_ic:+.4f} (should be ~0). "
                            "Near-zero IC = no edge.")),
    ]
    return Prediction(
        symbol=symbol, exchange=req.exchange, horizon=req.horizon,
        generated_at=datetime.now(timezone.utc), model_version=MODEL_VERSION,
        point_target=point,
        intervals=Intervals(ci68=(lo68, hi68), ci95=(lo95, hi95)),
        prob_up=round(_safe(dacc, 0.5), 4),
        scenarios=Scenarios(bull=hi95, base=point, bear=lo95),
        risk=Risk(var_95=round(-2*rs, 4), vol_forecast=round(rs, 4)),
        factors=factors)


@router.post("/predict", response_model=Prediction)
def predict(req: PredictRequest) -> Prediction:
    if not req.symbol or not req.symbol.strip():
        raise HTTPException(400, detail={"error": "empty_symbol",
                            "detail": "Enter a ticker symbol."})
    return _run_pipeline(req)