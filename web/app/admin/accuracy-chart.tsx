"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import type { Schemas } from "@/lib/api";

import { pct, ROUTE_COLOR, ROUTE_LABEL, ROUTES, type Route, shortWeek } from "./format";

type Cell = Schemas["RouteWeekAccuracy"];
type Point = { week: string } & Partial<Record<Route, number | null>> & {
    cells: Partial<Record<Route, Cell>>;
  };

/** One point per week; each route's accuracy as 0-100 (null = no rated answers that week). */
function pivot(rows: Cell[]): Point[] {
  const byWeek = new Map<string, Point>();
  for (const row of rows) {
    const point = byWeek.get(row.week) ?? { week: row.week, cells: {} };
    point[row.route] = row.accuracy == null ? null : Math.round(row.accuracy * 1000) / 10;
    point.cells[row.route] = row;
    byWeek.set(row.week, point);
  }
  return [...byWeek.values()].sort((a, b) => a.week.localeCompare(b.week));
}

export function AccuracyChart({ rows }: { rows: Cell[] }) {
  const [showTable, setShowTable] = useState(false);
  const data = pivot(rows);
  const routes = ROUTES.filter((r) => rows.some((row) => row.route === r));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend routes={routes} />
        <Button variant="ghost" size="sm" onClick={() => setShowTable((s) => !s)}>
          {showTable ? "Show chart" : "Show table"}
        </Button>
      </div>
      {showTable ? (
        <AccuracyTable data={data} routes={routes} />
      ) : (
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="week"
                tickFormatter={shortWeek}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                tickFormatter={(v) => `${v}%`}
                tickLine={false}
                axisLine={false}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              />
              <Tooltip
                cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
                content={(props) => <AccuracyTooltip {...props} routes={routes} />}
              />
              {routes.map((route) => (
                <Line
                  key={route}
                  dataKey={route}
                  name={ROUTE_LABEL[route]}
                  stroke={ROUTE_COLOR[route]}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  dot={{ r: 4, fill: ROUTE_COLOR[route], stroke: "var(--background)", strokeWidth: 2 }}
                  activeDot={{ r: 5, stroke: "var(--background)", strokeWidth: 2 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function Legend({ routes }: { routes: Route[] }) {
  return (
    <ul className="flex flex-wrap gap-4 text-sm" aria-label="Routes">
      {routes.map((route) => (
        <li key={route} className="flex items-center gap-2">
          <span
            className="h-0.5 w-4 rounded-full"
            style={{ background: ROUTE_COLOR[route] }}
            aria-hidden="true"
          />
          {ROUTE_LABEL[route]}
        </li>
      ))}
    </ul>
  );
}

function AccuracyTooltip({
  active,
  payload,
  routes,
}: TooltipContentProps & { routes: Route[] }) {
  const point = payload?.[0]?.payload as Point | undefined;
  if (!active || !point) return null;
  return (
    <div className="min-w-44 rounded-lg border bg-popover p-3 text-sm shadow-md">
      <p className="mb-2 text-xs text-muted-foreground">Week {shortWeek(point.week)}</p>
      <ul className="space-y-1">
        {routes.map((route) => {
          const cell = point.cells[route];
          return (
            <li key={route} className="flex items-center gap-2">
              <span
                className="h-0.5 w-3 rounded-full"
                style={{ background: ROUTE_COLOR[route] }}
                aria-hidden="true"
              />
              <span className="font-semibold tabular-nums">{pct(cell?.accuracy)}</span>
              <span className="text-muted-foreground">
                {ROUTE_LABEL[route]} · {cell ? `${cell.correct}/${cell.with_feedback} rated` : "no data"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AccuracyTable({ data, routes }: { data: Point[]; routes: Route[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Accuracy by route and week</caption>
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4 font-medium">Week</th>
            {routes.map((r) => (
              <th key={r} className="py-2 pr-4 font-medium">
                {ROUTE_LABEL[r]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.week} className="border-b last:border-0">
              <td className="py-2 pr-4">{point.week}</td>
              {routes.map((r) => {
                const cell = point.cells[r];
                return (
                  <td key={r} className="py-2 pr-4 tabular-nums">
                    {pct(cell?.accuracy)}
                    {cell && (
                      <span className="text-muted-foreground">
                        {" "}
                        ({cell.correct}/{cell.with_feedback})
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
