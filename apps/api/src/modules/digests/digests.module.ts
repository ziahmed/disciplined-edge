import { Module } from "@nestjs/common";
import { DigestsController } from "./digests.controller";
import { DigestsService } from "./digests.service";

@Module({
  controllers: [DigestsController],
  providers: [DigestsService],
  exports: [DigestsService],
})
export class DigestsModule {}
