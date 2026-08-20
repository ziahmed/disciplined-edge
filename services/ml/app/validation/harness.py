"""
Validation harness — model-agnostic. Ported from your notebook.

Only depends on make_model() + .fit()/.predict(). Swapping XGBoost for a
BiLSTM/TFT requires no change here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sharpe(returns, periods: int = 252) -> float:
    """Annualised Sharpe. >1 decent, >2 strong (after costs!)."""
    r = pd.Series(returns).dropna()
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(np.sqrt(periods) * r.mean() / r.std())


def information_coefficient(pred, actual) -> float:
    """Rank correlation between predictions and realised returns.
    ~0.03-0.06 is genuinely useful; near 0 or negative is a weak signal."""
    p, a = pd.Series(pred), pd.Series(actual)
    mask = p.notna() & a.notna()
    if mask.sum() < 3:
        return 0.0
    return float(p[mask].corr(a[mask], method="spearman"))


def direction_accuracy(pred, actual) -> float:
    """Share of times we called up-vs-down correctly. 0.5 is a coin flip."""
    p, a = np.sign(np.asarray(pred)), np.sign(np.asarray(actual))
    mask = ~(np.isnan(p) | np.isnan(a))
    if mask.sum() == 0:
        return 0.0
    return float((p[mask] == a[mask]).mean())


def walk_forward(X: np.ndarray, y: np.ndarray, make_model_fn,
                 n_splits: int = 5, kind: str = "xgb") -> dict:
    """
    Expanding-window walk-forward CV (true time-series validation).

    For each fold: fit on everything up to a point, predict the next block.
    Returns out-of-sample predictions and the trading metrics above.
    """
    n = len(X)
    if n < n_splits + 2:
        raise ValueError("not enough rows for the requested number of splits")

    fold = n // (n_splits + 1)
    preds, actuals = [], []

    for k in range(1, n_splits + 1):
        train_end = fold * k
        test_end = fold * (k + 1)
        model = make_model_fn(kind=kind, task="reg")
        model.fit(X[:train_end], y[:train_end])
        preds.extend(model.predict(X[train_end:test_end]).tolist())
        actuals.extend(y[train_end:test_end].tolist())

    preds, actuals = np.array(preds), np.array(actuals)
    return {
        "ic": information_coefficient(preds, actuals),
        "dir_acc": direction_accuracy(preds, actuals),
        "sharpe_gross": sharpe(np.sign(preds) * actuals),
        "n_oos": len(preds),
    }
