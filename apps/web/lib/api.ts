import { Prediction, PredictRequest, PredictError } from "@disciplined-edge/types";

const ML_SERVICE_URL =
  process.env.NEXT_PUBLIC_ML_SERVICE_URL ?? "http://localhost:8000";

export async function getPrediction(req: PredictRequest): Promise<Prediction> {
  const parsedReq = PredictRequest.parse(req);

  const res = await fetch(`${ML_SERVICE_URL}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parsedReq),
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const parsedError = PredictError.safeParse(body?.detail ?? body);
    const message = parsedError.success
      ? parsedError.data.detail ?? parsedError.data.error
      : `Prediction request failed (${res.status})`;
    throw new Error(message);
  }

  const raw = await res.json();
  return Prediction.parse(raw);
}
