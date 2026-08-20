"use client";
import type { Prediction } from "@disciplined-edge/types";

/**
 * Renders point target + 68%/95% confidence bands with Recharts.
 * There is no prop path that shows a price without its band — the Prediction
 * type guarantees the bands exist.
 */
export function PredictionChart({ prediction }: { prediction: Prediction }) {
  // TODO: Recharts AreaChart with ci95 (outer) and ci68 (inner) bands.
  return <div>{/* chart for {prediction.symbol} */}</div>;
}
