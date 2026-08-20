import { Module } from "@nestjs/common";
import { AuthModule } from "./modules/auth/auth.module";
import { UsersModule } from "./modules/users/users.module";
import { PortfoliosModule } from "./modules/portfolios/portfolios.module";
import { WatchlistsModule } from "./modules/watchlists/watchlists.module";
import { PredictionsModule } from "./modules/predictions/predictions.module";
import { AlertsModule } from "./modules/alerts/alerts.module";
import { MacroModule } from "./modules/macro/macro.module";
import { DigestsModule } from "./modules/digests/digests.module";
import { PersonasModule } from "./modules/personas/personas.module";

@Module({
  imports: [
    AuthModule,
    UsersModule,
    PortfoliosModule,
    WatchlistsModule,
    PredictionsModule,
    AlertsModule,
    MacroModule,
    DigestsModule,
    PersonasModule,
  ],
})
export class AppModule {}
