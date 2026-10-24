export const ROUTES = ["sql", "semantic", "hybrid"] as const;
export type Route = (typeof ROUTES)[number];

/** Fixed color per route, on every chart (CSS variables defined in globals.css). */
export const ROUTE_COLOR: Record<Route, string> = {
  sql: "var(--route-sql)",
  semantic: "var(--route-semantic)",
  hybrid: "var(--route-hybrid)",
};
export const ROUTE_LABEL: Record<Route, string> = {
  sql: "SQL",
  semantic: "Semantic",
  hybrid: "Hybrid",
};

export function pct(ratio: number | null | undefined): string {
  return ratio == null ? "–" : `${Math.round(ratio * 100)}%`;
}

export function ms(value: number | null | undefined): string {
  if (value == null) return "–";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
}

/** 1,284 stays exact; only 10,000 and up compact (12.9K), so small counts never blur. */
export function compact(n: number): string {
  if (n < 10_000) return n.toLocaleString("en-US");
  return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}K`;
}

/** "2026-W43" -> "W43" for axis ticks */
export function shortWeek(week: string): string {
  return week.split("-")[1] ?? week;
}
