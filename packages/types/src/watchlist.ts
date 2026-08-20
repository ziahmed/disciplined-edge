import { z } from "zod";

export const WatchlistItem = z.object({
  securityId: z.string().uuid(),
  symbol: z.string(),
  exchange: z.enum(["NASDAQ", "SGX"]),
});
export type WatchlistItem = z.infer<typeof WatchlistItem>;

export const Watchlist = z.object({
  id: z.string().uuid(),
  name: z.string(),
  items: z.array(WatchlistItem),
});
export type Watchlist = z.infer<typeof Watchlist>;
