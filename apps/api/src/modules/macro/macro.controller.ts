import { Controller } from "@nestjs/common";
import { MacroService } from "./macro.service";

/**
 * macro routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("macro")
export class MacroController {
  constructor(private readonly macro: MacroService) {}
}
