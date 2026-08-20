import { z } from "zod";

/**
 * Prediction contract — conformant copy of docs/api-contract.md.
 * If this drifts from the Markdown contract, the contract test fails.
 */
export const Exchange = z.enum(["NASDAQ", "SGX"]);
export type Exchange = z.infer<typeof Exchange>;

export const Horizon = z.enum(["1d", "1w", "1m", "3m", "6m", "1y"]);
export type Horizon = z.infer<typeof Horizon>;

export const PredictRequest = z.object({
  symbol: z.string().min(1),
  exchange: Exchange,
  horizon: Horizon,
  as_of: z.string().date().optional(),
});
export type PredictRequest = z.infer<typeof PredictRequest>;

export const Factor = z.object({
  rank: z.number().int().min(1).max(5),
  factor: z.string(),
  contribution: z.number(),
  explanation: z.string(),
});
export type Factor = z.infer<typeof Factor>;

const Interval = z.tuple([z.number(), z.number()]);

export const Prediction = z
  .object({
    symbol: z.string(),
    exchange: Exchange,
    horizon: Horizon,
    generated_at: z.string().datetime(),
    model_version: z.string(),
    point_target: z.number(),
    intervals: z.object({
      ci68: Interval,
      ci95: Interval,
    }),
    prob_up: z.number().min(0).max(1),
    scenarios: z.object({
      bull: z.number(),
      base: z.number(),
      bear: z.number(),
    }),
    risk: z.object({
      var_95: z.number(),
      vol_forecast: z.number().min(0),
    }),
    factors: z.array(Factor).min(1).max(5),
  })
  .refine((p) => p.intervals.ci68[0] <= p.point_target && p.point_target <= p.intervals.ci68[1], {
    message: "point_target must lie inside the 68% interval",
  })
  .refine(
    (p) => p.intervals.ci95[0] <= p.intervals.ci68[0] && p.intervals.ci95[1] >= p.intervals.ci68[1],
    { message: "95% interval must contain the 68% interval" },
  )
  .refine((p) => p.scenarios.bear <= p.scenarios.base && p.scenarios.base <= p.scenarios.bull, {
    message: "scenarios must satisfy bear <= base <= bull",
  });
export type Prediction = z.infer<typeof Prediction>;

export const PredictError = z.object({
  error: z.enum(["unknown_symbol", "insufficient_history", "model_unavailable", "ticker_not_found", "empty_symbol"]),
  detail: z.string().optional(),
});
export type PredictError = z.infer<typeof PredictError>;
