import { Injectable } from "@nestjs/common";
import { Prediction, PredictRequest } from "@disciplined-edge/types";
import { MlClientService } from "./ml-client.service";

/**
 * Owns the prediction domain on the Node side:
 *   - cache lookup (Redis, omitted in this scaffold)
 *   - call the ML service on miss
 *   - persist to `predictions` / `prediction_factors` (omitted)
 *   - return the validated Prediction
 */
@Injectable()
export class PredictionsService {
  constructor(private readonly ml: MlClientService) {}

  async getPrediction(req: PredictRequest): Promise<Prediction> {
    // TODO: const cached = await this.cache.get(key(req)); if (cached) return cached;
    const prediction = await this.ml.predict(req);
    // TODO: await this.repo.save(prediction); await this.cache.set(key(req), prediction, TTL);
    return prediction;
  }
}
