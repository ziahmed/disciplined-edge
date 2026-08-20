# API Contract — Node API ↔ Python ML Service

This document is the **source of truth** for the prediction shape. Both sides conform to it:
- TypeScript (`packages/types`) uses it for the client, web, mobile, and Node API.
- Python (`services/ml/app/schemas.py`) mirrors it with Pydantic.

If you change a field, change it **here first**, then update both implementations. The contract tests in each service check conformance against the examples below.

---

## Why two definitions instead of one

There is no single language that both NestJS (TypeScript) and FastAPI (Python) share at runtime, so the shape is necessarily declared twice. The discipline is: this Markdown file is canonical, the two code definitions are *conformant copies*, and a contract test on each side fails the build if it drifts. Do not treat either code file as the authority.

---

## Endpoint: `POST /predict`

Internal endpoint. Called by the Node API, never by clients directly. No auth between services at MVP if they share a private network; add mTLS or a shared secret before exposing anything.

### Request

```json
{
  "symbol": "ASML",
  "exchange": "NASDAQ",
  "horizon": "1m",
  "as_of": "2026-06-01"
}
```

| Field | Type | Notes |
|---|---|---|
| `symbol` | string | Ticker as stored in `securities.symbol` (e.g. `ASML`, `D05.SI`). |
| `exchange` | `"NASDAQ" \| "SGX"` | Must match `securities.exchange`. |
| `horizon` | `"1w" \| "1m" \| "3m" \| "6m" \| "1y"` | Forecast window. |
| `as_of` | string (ISO date) | Optional. Defaults to latest available bar. Used for backtesting/reproducibility. |

### Response

```json
{
  "symbol": "ASML",
  "exchange": "NASDAQ",
  "horizon": "1m",
  "generated_at": "2026-06-01T08:00:00Z",
  "model_version": "xgb-2026.06.01",
  "point_target": 1042.50,
  "intervals": {
    "ci68": [985.00, 1100.00],
    "ci95": [920.00, 1165.00]
  },
  "prob_up": 0.62,
  "scenarios": {
    "bull": 1165.00,
    "base": 1042.50,
    "bear": 920.00
  },
  "risk": {
    "var_95": -0.078,
    "vol_forecast": 0.041
  },
  "factors": [
    {
      "rank": 1,
      "factor": "RSI(14) cooling from overbought",
      "contribution": -0.012,
      "explanation": "Momentum has eased off recent highs, which slightly tempers the upside case."
    },
    {
      "rank": 2,
      "factor": "Relative strength vs QQQ positive",
      "contribution": 0.020,
      "explanation": "The stock has been outpacing the NASDAQ-100, a mild tailwind."
    }
  ]
}
```

### Field contract

| Field | Type | Invariant |
|---|---|---|
| `point_target` | number | The base-case price (or return, if you switch units — pick one and document it). |
| `intervals.ci68` | `[number, number]` | `low <= point_target <= high`. |
| `intervals.ci95` | `[number, number]` | Strictly wider than or equal to `ci68`: `ci95[0] <= ci68[0]` and `ci95[1] >= ci68[1]`. |
| `prob_up` | number | In `[0, 1]`. |
| `scenarios.bear/base/bull` | number | `bear <= base <= bull`. |
| `risk.var_95` | number | 95% Value at Risk over the horizon, as a signed return (negative = loss). |
| `risk.vol_forecast` | number | Forecast volatility over the horizon, non-negative. |
| `factors` | array | 1–5 items, `rank` is 1-based and unique. `contribution` is the signed SHAP value (P3) or a simpler signed weight (P1). |

**Hard rule the schema enforces:** a response is invalid if it omits `intervals` or `prob_up`. This is the technical guarantee behind the product rule "never show a bare price target." The client cannot render a number that has no band, because the contract won't let one exist.

### Errors

```json
{ "error": "unknown_symbol", "detail": "ASMLX/NASDAQ not in securities master" }
```

| `error` | When |
|---|---|
| `unknown_symbol` | Symbol/exchange pair not in `securities`. |
| `insufficient_history` | Fewer than the minimum bars needed for the horizon. |
| `model_unavailable` | No trained model for that symbol/horizon yet. |

The Node API maps these to HTTP 4xx and surfaces an Elena-voiced message; the ML service returns 200 with an `error` body or a 4xx — pick one convention (this scaffold uses HTTP status codes + the error body).
