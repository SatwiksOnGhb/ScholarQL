"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { QueryResult } from "@/components/query-state";
import { api, type Schemas, unwrap } from "@/lib/api";

// Categorical palette for up to 6 topics (route colours first, so the app stays consistent)
const COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#9256d9", "#c99a06", "#d6457a"];
const TOPICS = 6;

function toRows(t: Schemas["TrendsResponse"]) {
  const years = t.topics[0]?.counts.map((c) => c.year) ?? [];
  return years.map((year, i) => ({
    year,
    ...Object.fromEntries(t.topics.map((topic) => [topic.name, topic.counts[i].count])),
  }));
}

/** Papers per year for the biggest topics (A's topic_year_trends materialized view). */
export function TrendsChart() {
  const trends = useQuery({
    queryKey: ["trends", TOPICS],
    queryFn: () => unwrap(api.GET("/trends", { params: { query: { limit: TOPICS } } })),
    staleTime: 10 * 60_000,
  });
  return (
    <section className="space-y-3" aria-labelledby="trends-heading">
      <h2 id="trends-heading" className="text-lg font-semibold">
        Topic trends
      </h2>
      <QueryResult query={trends}>
        {(t) =>
          t.topics.length === 0 ? (
            <p className="text-sm text-muted-foreground">No topics in the database yet.</p>
          ) : (
            <div className="h-72" role="img" aria-label="Papers per year for the largest topics">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={toRows(t)} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="year" tickLine={false} axisLine={{ stroke: "var(--border)" }} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: "var(--popover)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {t.topics.map((topic, i) => (
                    <Line
                      key={topic.topic_id}
                      type="monotone"
                      dataKey={topic.name}
                      stroke={COLORS[i % COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )
        }
      </QueryResult>
    </section>
  );
}
