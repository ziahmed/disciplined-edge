import { getPrediction } from "@/lib/api";
import { PredictionChart } from "@/components/PredictionChart";

export default async function Screen({
  params,
  searchParams,
}: {
  params: { symbol: string };
  searchParams: { exchange?: string; horizon?: string };
}) {
  const exchange = (searchParams.exchange ?? "NASDAQ") as "NASDAQ" | "SGX";
  const horizon = (searchParams.horizon ?? "1m") as
    | "1d" | "1w" | "1m" | "3m" | "6m" | "1y";

  let prediction;
  let error: string | null = null;

  try {
    prediction = await getPrediction({
      symbol: params.symbol,
      exchange,
      horizon,
    });
  } catch (e) {
    error = e instanceof Error ? e.message : "Something went wrong.";
  }

  if (error || !prediction) {
    return (
      <main>
        <p>Couldn't load a forecast for {params.symbol}: {error}</p>
      </main>
    );
  }

  return (
    <main>
      <h1>{prediction.symbol} — {prediction.horizon}</h1>
      <p>
        Base case: ${prediction.point_target.toFixed(2)} ·{" "}
        {(prediction.prob_up * 100).toFixed(0)}% probability up
      </p>
      <PredictionChart prediction={prediction} />
      <section>
        <h2>Driving factors</h2>
        <ul>
          {prediction.factors.map((f) => (
            <li key={f.rank}>
              <strong>{f.factor}</strong> — {f.explanation}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}