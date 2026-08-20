import { Controller, Get, Param, Query, BadRequestException } from "@nestjs/common";
import { Exchange, Horizon, PredictRequest } from "@disciplined-edge/types";
import { PredictionsService } from "./predictions.service";

/**
 * GET /predictions/:symbol?exchange=NASDAQ&horizon=1m
 *
 * Auth guard + per-user authorization omitted in this scaffold; add the guard
 * before exposing this route.
 */
@Controller("predictions")
export class PredictionsController {
  constructor(private readonly predictions: PredictionsService) {}

  @Get(":symbol")
  async get(
    @Param("symbol") symbol: string,
    @Query("exchange") exchange: string,
    @Query("horizon") horizon: string,
  ) {
    const parsed = PredictRequest.safeParse({
      symbol,
      exchange: Exchange.safeParse(exchange).success ? exchange : undefined,
      horizon: Horizon.safeParse(horizon).success ? horizon : undefined,
    });
    if (!parsed.success) {
      throw new BadRequestException(parsed.error.flatten());
    }
    return this.predictions.getPrediction(parsed.data);
  }
}
