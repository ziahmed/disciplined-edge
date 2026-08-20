"""
Model factory — the ONLY place that knows which library backs a model.

This is the model-agnostic seam from your notebook, promoted to the service.
The validation harness and the predict router call make_model() and then only
use .fit() / .predict(); they never import xgboost or torch directly. To swap
the baseline, edit here and nothing else.
"""

from __future__ import annotations

from typing import Literal, Protocol

import numpy as np


class Estimator(Protocol):
    """Minimal interface the rest of the service depends on."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Estimator": ...
    def predict(self, X: np.ndarray) -> np.ndarray: ...


ModelKind = Literal["xgb", "linear", "lstm", "tft"]
Task = Literal["reg", "clf"]


def make_model(kind: ModelKind = "xgb", task: Task = "reg") -> Estimator:
    """
    Return an unfitted estimator.

      kind="xgb"    -> XGBoost (default baseline; replaced RandomForest)
      kind="linear" -> scikit-learn fallback if XGBoost is unavailable
      kind="lstm"   -> PyTorch BiLSTM wrapper (Phase 3; see _TorchSeqModel)
      kind="tft"    -> Temporal Fusion Transformer wrapper (Phase 3)
    """
    if kind == "xgb":
        try:
            from xgboost import XGBClassifier, XGBRegressor

            common = dict(n_estimators=300, max_depth=4, learning_rate=0.05,
                          subsample=0.8, colsample_bytree=0.8, n_jobs=-1)
            return XGBRegressor(**common) if task == "reg" else XGBClassifier(**common)
        except ImportError:
            kind = "linear"  # graceful fallback

    if kind == "linear":
        from sklearn.linear_model import LinearRegression, LogisticRegression

        return LinearRegression() if task == "reg" else LogisticRegression(max_iter=1000)

    if kind in ("lstm", "tft"):
        # Phase-3 placeholder. Implement a class exposing .fit(X, y)/.predict(X)
        # so the harness stays untouched. A BiLSTM/TFT reshapes the flat feature
        # matrix into (samples, timesteps, features) internally.
        raise NotImplementedError(
            f"{kind} wrapper is a Phase-3 task; implement the Estimator protocol "
            "and register it here without touching the validation harness."
        )

    raise ValueError(f"unknown model kind: {kind}")
