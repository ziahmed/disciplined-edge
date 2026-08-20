import { Controller } from "@nestjs/common";
import { WatchlistsService } from "./watchlists.service";

/**
 * watchlists routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("watchlists")
export class WatchlistsController {
  constructor(private readonly watchlists: WatchlistsService) {}
}
