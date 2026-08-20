import { Module } from "@nestjs/common";
import { PredictionsController } from "./predictions.controller";
import { PredictionsService } from "./predictions.service";
import { MlClientService } from "./ml-client.service";

@Module({
  controllers: [PredictionsController],
  providers: [PredictionsService, MlClientService],
  exports: [PredictionsService],
})
export class PredictionsModule {}
