import { Controller } from "@nestjs/common";
import { UsersService } from "./users.service";

/**
 * users routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("users")
export class UsersController {
  constructor(private readonly users: UsersService) {}
}
