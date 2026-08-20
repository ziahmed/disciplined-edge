import { Controller } from "@nestjs/common";
import { PersonasService } from "./personas.service";

/**
 * personas routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("personas")
export class PersonasController {
  constructor(private readonly personas: PersonasService) {}
}
