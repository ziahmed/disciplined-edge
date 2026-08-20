"""
Prediction contract — conformant copy of docs/api-contract.md (Python side).

If this drifts from the Markdown contract, tests/test_contract.py fails.
The validators below are the Python mirror of the zod refinements in
packages/types/src/prediction.ts.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Exchange = Literal["NASDAQ", "SGX"]
Horizon = Literal["1w", "1m", "3m", "6m", "1y"]


class PredictRequest(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: Exchange
    horizon: Horizon
    as_of: date | None = None


class Factor(BaseModel):
    rank: int = Field(ge=1, le=5)
    factor: str
    contribution: float
    explanation: str


class Intervals(BaseModel):
    ci68: tuple[float, float]
    ci95: tuple[float, float]


class Scenarios(BaseModel):
    bull: float
    base: float
    bear: float


class Risk(BaseModel):
    var_95: float
    vol_forecast: float = Field(ge=0)


class Prediction(BaseModel):
    symbol: str
    exchange: Exchange
    horizon: Horizon
    generated_at: datetime
    model_version: str
    point_target: float
    intervals: Intervals
    prob_up: float = Field(ge=0, le=1)
    scenarios: Scenarios
    risk: Risk
    factors: list[Factor] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def _check_invariants(self) -> "Prediction":
        lo68, hi68 = self.intervals.ci68
        lo95, hi95 = self.intervals.ci95
        if not (lo68 <= self.point_target <= hi68):
            raise ValueError("point_target must lie inside the 68% interval")
        if not (lo95 <= lo68 and hi95 >= hi68):
            raise ValueError("95% interval must contain the 68% interval")
        s = self.scenarios
        if not (s.bear <= s.base <= s.bull):
            raise ValueError("scenarios must satisfy bear <= base <= bull")
        return self


class PredictError(BaseModel):
    error: Literal["unknown_symbol", "insufficient_history", "model_unavailable"]
    detail: str | None = None
