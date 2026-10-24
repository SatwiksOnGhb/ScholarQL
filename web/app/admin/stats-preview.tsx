"use client";

import { useQuery } from "@tanstack/react-query";

import { JsonPreview } from "@/components/json-preview";
import { QueryResult } from "@/components/query-state";
import { api, unwrap } from "@/lib/api";

// Placeholder: raw GET /admin/stats response. Charts come in task 11.
export function StatsPreview() {
  const stats = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => unwrap(api.GET("/admin/stats")),
  });
  return <QueryResult query={stats}>{(data) => <JsonPreview data={data} label="Stats" />}</QueryResult>;
}
