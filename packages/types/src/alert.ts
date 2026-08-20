import { z } from "zod";

export const AlertKind = z.enum(["price_target", "risk_threshold", "macro_shift"]);
export type AlertKind = z.infer<typeof AlertKind>;

export const Alert = z.object({
  id: z.string().uuid(),
  securityId: z.string().uuid().optional(),
  kind: AlertKind,
  condition: z.record(z.unknown()), // e.g. { op: ">=", value: 250 }
  active: z.boolean().default(true),
});
export type Alert = z.infer<typeof Alert>;
