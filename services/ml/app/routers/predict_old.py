"""
/predict router.

This is the boundary the Node API calls. It validates the request, runs the
prediction pipeline, and returns a contract-conformant Prediction. The actual
forecasting logic (feature engineering, model fit/predict, interval estimation)
is delegated to app.features and app.models — ported from your notebook.

The body below is a working stub that returns a *shaped* prediction so the whole
vertical slice runs end to end before the real model is wired in. Replace
`_run_pipeline` with calls into your notebook code.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas import (
    Factor,
    Intervals,
    Prediction,
    PredictRequest,
    Risk,
    Scenarios,
)

router = APIRouter()

# Phase-1 starter universe. Replace with a securities lookup against Postgres.
_KNOWN = {
    ("ASML", "NASDAQ"), ("TSLA", "NASDAQ"), ("INTC", "NASDAQ"),
    ("IONQ", "NASDAQ"), ("SLV", "NASDAQ"),
}

MODEL_VERSION = "xgb-stub-2026.06.01"


def _run_pipeline(req: PredictRequest) -> Prediction:
    """
    TODO (port from notebook):
      1. Load price_bars + fundamentals for req.symbol.
      2. engineer_features(...) -> feature matrix.
      3. model = make_model("xgb"); walk-forward gives OOS error for intervals.
      4. Predict point_target; derive ci68/ci95 from the model's recent error.
      5. SHAP -> top factors (Phase 3); simpler weights for Phase 1.

    The stub below returns a self-consistent shape so the slice runs today.
    """
    base = 100.0
    return Prediction(
        symbol=req.symbol,
        exchange=req.exchange,
        horizon=req.horizon,
        generated_at=datetime.now(timezone.utc),
        model_version=MODEL_VERSION,
        point_target=base,
        intervals=Intervals(ci68=(base * 0.95, base * 1.05),
                            ci95=(base * 0.90, base * 1.10)),
        prob_up=0.58,
        scenarios=Scenarios(bull=base * 1.10, base=base, bear=base * 0.90),
        risk=Risk(var_95=-0.07, vol_forecast=0.04),
        factors=[
            Factor(rank=1, factor="placeholder signal", contribution=0.0,
                   explanation="Stub prediction — wire _run_pipeline to the model."),
        ],
    )


@router.post("/predict", response_model=Prediction)
def predict(req: PredictRequest) -> Prediction:
    if (req.symbol, req.exchange) not in _KNOWN:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_symbol",
                    "detail": f"{req.symbol}/{req.exchange} not in securities master"},
        )
    return _run_pipeline(req)
