import { z } from "zod";

export const Persona = z.enum(["elena", "kai", "ava"]);
export type Persona = z.infer<typeof Persona>;

export const RiskTolerance = z.enum(["conservative", "balanced", "growth", "aggressive"]);
export type RiskTolerance = z.infer<typeof RiskTolerance>;

export const Profile = z.object({
  userId: z.string().uuid(),
  displayName: z.string().optional(),
  baseCurrency: z.enum(["SGD", "USD"]),
  riskTolerance: RiskTolerance.optional(),
  activePersona: Persona.default("elena"),
  onboardingComplete: z.boolean().default(false),
});
export type Profile = z.infer<typeof Profile>;

export const Goal = z.object({
  id: z.string().uuid(),
  label: z.string(),
  horizon: z.string(),
  targetAmount: z.number().optional(),
});
export type Goal = z.infer<typeof Goal>;
