import { z } from "zod";

export const Holding = z.object({
  securityId: z.string().uuid(),
  symbol: z.string(),
  quantity: z.number(),
  avgCost: z.number(),
});
export type Holding = z.infer<typeof Holding>;

export const Portfolio = z.object({
  id: z.string().uuid(),
  name: z.string(),
  holdings: z.array(Holding),
  riskScore: z.number().min(0).max(10).optional(), // AI risk score (Phase 2)
});
export type Portfolio = z.infer<typeof Portfolio>;
