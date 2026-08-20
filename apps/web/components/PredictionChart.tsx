"use client";
import type { Prediction } from "@disciplined-edge/types";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export function PredictionChart({ prediction }: { prediction: Prediction }) {
  const { ci68, ci95 } = prediction.intervals;
  const data = [
    { label: "Bear", value: prediction.scenarios.bear, ci95Low: ci95[0], ci68Low: ci68[0] },
    { label: "Base", value: prediction.point_target, ci95Low: ci95[0], ci68Low: ci68[0] },
    { label: "Bull", value: prediction.scenarios.bull, ci95High: ci95[1], ci68High: ci68[1] },
  ];

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
          <XAxis dataKey="label" />
          <YAxis domain={[ci95[0], ci95[1]]} />
          <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
          <Area
            type="monotone"
            dataKey={() => ci95}
            stroke="none"
            fill="#c7d2fe"
            fillOpacity={0.4}
            name="95% range"
          />
          <Area
            type="monotone"
            dataKey={() => ci68}
            stroke="none"
            fill="#818cf8"
            fillOpacity={0.6}
            name="68% range"
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#4338ca"
            fill="none"
            strokeWidth={2}
            name="Point target"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
