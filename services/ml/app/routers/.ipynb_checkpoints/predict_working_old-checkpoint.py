"""
/predict router — TRAIN-ON-EVERY-CLICK (research mode), ASML/TSLA/INTC/IONQ.

Per request, for the next-day horizon, this:
  1. downloads the ticker's history live (yfinance)
  2. builds the leak-free features
  3. trains a fresh XGBoost model right now (80/20 split for honest OOS metrics)
  4. predicts the next-day return -> price, sizes the band from OOS error
  5. shows the freshly-measured IC / dir-acc + honest verdict

TRADEOFFS YOU ACCEPTED (research mode, single user):
  * every click takes ~20-60s while a model trains (page shows nothing until done)
  * every click re-downloads from Yahoo (watch for rate-limiting)
  * the prediction can drift click-to-click as new data/training randomness shifts it
This is fine for solo research. It is NOT how you'd serve real users — for that,
train offline and load a saved model. Kept honest so you can switch back easily.

Honesty rules unchanged:
  * only next-day horizon ('1w' slot) computes a number; others -> not validated
  * tickers not in TRAINABLE -> "not yet validated" (e.g. SLV)
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from app.schemas import (
    Factor, Intervals, Prediction, PredictRequest, Risk, Scenarios,
)

router = APIRouter()

_KNOWN = {
    ("ASML", "NASDAQ"), ("TSLA", "NASDAQ"), ("INTC", "NASDAQ"),
    ("IONQ", "NASDAQ"), ("SLV", "NASDAQ"),
}
TRAINABLE = {"ASML", "TSLA", "INTC", "IONQ"}     # SLV intentionally excluded
MODEL_VERSION = "live-train-on-click-2026.06.04"
NOISE_BAND = 0.02
NEXTDAY_HORIZONS = {"1d", "1w"}
START = "2020-01-01"

FEATURES = [
    "rsi_14", "stoch_k", "stoch_d", "bb_pctb", "macd_hist",
    "fib_dist_382", "fib_dist_500", "fib_dist_618",
    "hist_vol_20", "hist_vol_60", "dow", "month", "quarter",
]


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


def _not_validated(req, kind):
    base = 100.0
    if kind == "ticker":
        f = [Factor(rank=1, factor="Not yet validated", contribution=0.0,
                    explanation=(f"{req.symbol} is not in the trainable set "
                                 "(e.g. SLV, an ETF you chose not to validate)."))]
    else:
        f = [Factor(rank=1, factor="Not validated for this horizon", contribution=0.0,
                    explanation=("Models predict next-day returns only. Run the "
                                 "horizon sweep to enable this horizon."))]
    return Prediction(
        symbol=req.symbol, exchange=req.exchange, horizon=req.horizon,
        generated_at=datetime.now(timezone.utc), model_version=MODEL_VERSION,
        point_target=base,
        intervals=Intervals(ci68=(base*0.93, base*1.07), ci95=(base*0.86, base*1.14)),
        prob_up=0.50,
        scenarios=Scenarios(bull=base*1.14, base=base, bear=base*0.86),
        risk=Risk(var_95=-0.10, vol_forecast=0.05), factors=f)


def _run_pipeline(req: PredictRequest) -> Prediction:
    if req.symbol not in TRAINABLE:
        return _not_validated(req, "ticker")
    if req.horizon not in NEXTDAY_HORIZONS:
        return _not_validated(req, "horizon")

    import yfinance as yf
    from xgboost import XGBRegressor

    # 1. live data
    raw = yf.download(req.symbol, start=START, auto_adjust=False, progress=False)
    if raw.empty:
        raise HTTPException(503, detail={"error": "data_unavailable",
                            "detail": "Could not fetch live price data (Yahoo)."})
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    # 2. features + target (seam: t -> t+1)
    feats = _build_features(raw)
    target = raw["Close"].shift(-1) / raw["Close"] - 1.0
    data = feats.join(target.rename("y")).dropna().sort_index()
    if len(data) < 200:
        raise HTTPException(503, detail={"error": "insufficient_history",
                            "detail": "Not enough data to train."})

    X, y = data[FEATURES].to_numpy(), data["y"].to_numpy()

    # 3. train fresh, right now (80/20 for honest OOS metrics + band)
    cut = int(len(X) * 0.8)
    model = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
    model.fit(X[:cut], y[:cut])
    oos_pred, oos_true = model.predict(X[cut:]), y[cut:]
    resid_std = float(np.std(oos_true - oos_pred))
    ic = float(pd.Series(oos_pred).corr(pd.Series(oos_true), method="spearman"))
    dacc = float((np.sign(oos_pred) == np.sign(oos_true)).mean())
    model.fit(X, y)  # refit on all data for the live point estimate

    # 4. predict latest -> price
    latest_close = float(raw["Close"].iloc[-1])
    pred_ret = float(model.predict(data[FEATURES].to_numpy()[-1:])[0])
    price = latest_close * (1 + pred_ret)
    lo68, hi68 = latest_close*(1+pred_ret-resid_std), latest_close*(1+pred_ret+resid_std)
    lo95, hi95 = latest_close*(1+pred_ret-2*resid_std), latest_close*(1+pred_ret+2*resid_std)

    factors = [
        Factor(rank=1, factor=f"Verdict (next-day, {req.symbol})", contribution=ic,
               explanation=_verdict(ic)),
        Factor(rank=2, factor=f"Predicted next-day return: {pred_ret*100:+.2f}%",
               contribution=round(pred_ret, 4),
               explanation=(f"From last close ${latest_close:,.2f}. Freshly trained "
                            "this request — may drift click to click.")),
        Factor(rank=3, factor=f"Measured IC: {ic:+.4f}  |  dir-acc: {dacc*100:.1f}%",
               contribution=ic,
               explanation="Out-of-sample. Near-zero IC and ~50% accuracy = no edge."),
    ]
    return Prediction(
        symbol=req.symbol, exchange=req.exchange, horizon=req.horizon,
        generated_at=datetime.now(timezone.utc), model_version=MODEL_VERSION,
        point_target=round(price, 2),
        intervals=Intervals(ci68=(round(lo68,2), round(hi68,2)),
                            ci95=(round(lo95,2), round(hi95,2))),
        prob_up=round(float(dacc), 4),
        scenarios=Scenarios(bull=round(hi95,2), base=round(price,2), bear=round(lo95,2)),
        risk=Risk(var_95=round(-2*resid_std,4), vol_forecast=round(resid_std,4)),
        factors=factors)


@router.post("/predict", response_model=Prediction)
def predict(req: PredictRequest) -> Prediction:
    if (req.symbol, req.exchange) not in _KNOWN:
        raise HTTPException(status_code=404,
            detail={"error": "unknown_symbol",
                    "detail": f"{req.symbol}/{req.exchange} not in securities master"})
    return _run_pipeline(req)