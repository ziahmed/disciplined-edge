import { Injectable, HttpException } from "@nestjs/common";
import { Prediction, PredictRequest } from "@disciplined-edge/types";

/**
 * Thin client over the Python ML service. The Node side validates the response
 * against the shared zod schema before trusting it — so a contract drift in the
 * ML service surfaces here as a parse error, not a silent bad number.
 */
@Injectable()
export class MlClientService {
  private readonly baseUrl = process.env.ML_SERVICE_URL ?? "http://localhost:8000";

  async predict(req: PredictRequest): Promise<Prediction> {
    // Validate the outbound request too.
    const body = PredictRequest.parse(req);

    const res = await fetch(`${this.baseUrl}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: body.symbol,
        exchange: body.exchange,
        horizon: body.horizon,
        as_of: body.asOf,
      }),
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new HttpException(detail, res.status);
    }

    const raw = await res.json();
    // snake_case (Python) -> camelCase (TS) before validating.
    const normalised = {
      symbol: raw.symbol,
      exchange: raw.exchange,
      horizon: raw.horizon,
      generatedAt: raw.generated_at,
      modelVersion: raw.model_version,
      pointTarget: raw.point_target,
      intervals: raw.intervals,
      probUp: raw.prob_up,
      scenarios: raw.scenarios,
      risk: { var95: raw.risk.var_95, volForecast: raw.risk.vol_forecast },
      factors: raw.factors,
    };

    // Throws if the ML service ever returns a bandless or inconsistent shape.
    return Prediction.parse(normalised);
  }
}
