import { Controller } from "@nestjs/common";
import { DigestsService } from "./digests.service";

/**
 * digests routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("digests")
export class DigestsController {
  constructor(private readonly digests: DigestsService) {}
}
