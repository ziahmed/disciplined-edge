import { Controller } from "@nestjs/common";
import { PortfoliosService } from "./portfolios.service";

/**
 * portfolios routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("portfolios")
export class PortfoliosController {
  constructor(private readonly portfolios: PortfoliosService) {}
}
