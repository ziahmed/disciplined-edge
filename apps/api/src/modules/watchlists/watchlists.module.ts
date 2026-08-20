import { Module } from "@nestjs/common";
import { WatchlistsController } from "./watchlists.controller";
import { WatchlistsService } from "./watchlists.service";

@Module({
  controllers: [WatchlistsController],
  providers: [WatchlistsService],
  exports: [WatchlistsService],
})
export class WatchlistsModule {}
