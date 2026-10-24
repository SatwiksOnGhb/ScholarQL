"use client";

import {
  Bar,
  BarChart,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from "recharts";

import type { Schemas } from "@/lib/api";

import { ms, ROUTE_LABEL, type Route } from "./format";

type Row = Schemas["RouteLatency"];
const SERIES = [
  { key: "p50_ms", label: "p50 (median)", color: "var(--latency-p50)" },
  { key: "p95_ms", label: "p95", color: "var(--latency-p95)" },
] as const;

export function LatencyChart({ rows }: { rows: Row[] }) {
  const data = rows.map((r) => ({ ...r, name: ROUTE_LABEL[r.route as Route] }));
  return (
    <div className="space-y-3">
      <ul className="flex gap-4 text-sm" aria-label="Percentiles">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </li>
        ))}
      </ul>
      <div style={{ height: rows.length * 64 + 24 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 56, bottom: 0, left: 0 }}
            barGap={2}
            barCategoryGap="22%"
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="name"
              width={76}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--foreground)", fontSize: 13 }}
            />
            <Tooltip
              cursor={{ fill: "var(--muted)", opacity: 0.5 }}
              content={(props) => <LatencyTooltip {...props} />}
            />
            {SERIES.map((s) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={s.color}
                barSize={12}
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey={s.key}
                  position="right"
                  formatter={(v) => ms(Number(v))}
                  style={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                />
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function LatencyTooltip({ active, payload }: TooltipContentProps) {
  const row = payload?.[0]?.payload as (Row & { name: string }) | undefined;
  if (!active || !row) return null;
  return (
    <div className="rounded-lg border bg-popover p-3 text-sm shadow-md">
      <p className="mb-1 text-xs text-muted-foreground">
        {row.name} · {row.count} questions
      </p>
      {SERIES.map((s) => (
        <p key={s.key} className="flex items-center gap-2">
          <span className="size-2 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
          <span className="font-semibold tabular-nums">{ms(row[s.key])}</span>
          <span className="text-muted-foreground">{s.label}</span>
        </p>
      ))}
    </div>
  );
}
