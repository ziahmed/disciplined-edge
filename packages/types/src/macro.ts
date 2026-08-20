import { z } from "zod";

export const MacroSignal = z.object({
  name: z.string(), // fed_funds | sgd_usd | sg_cpi | vix
  asOf: z.string().date(),
  value: z.number(),
  trend: z.enum(["up", "down", "flat"]),
});
export type MacroSignal = z.infer<typeof MacroSignal>;
