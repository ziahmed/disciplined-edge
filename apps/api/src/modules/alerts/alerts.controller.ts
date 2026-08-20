import { Controller } from "@nestjs/common";
import { AlertsService } from "./alerts.service";

/**
 * alerts routes. TODO: add an auth guard + per-user authorization before exposing.
 * See docs/DEVELOPMENT_PLAN.md (Phase mapping) for what this module owns.
 */
@Controller("alerts")
export class AlertsController {
  constructor(private readonly alerts: AlertsService) {}
}
