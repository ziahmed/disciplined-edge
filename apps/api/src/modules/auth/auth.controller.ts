import { Controller } from "@nestjs/common";
import { AuthService } from "./auth.service";

/**
 * auth routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("auth")
export class AuthController {
  constructor(private readonly auth: AuthService) {}
}
