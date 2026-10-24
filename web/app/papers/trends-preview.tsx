"use client";

import { useQuery } from "@tanstack/react-query";

import { JsonPreview } from "@/components/json-preview";
import { QueryResult } from "@/components/query-state";
import { api, unwrap } from "@/lib/api";

// TODO(A): placeholder; shows the raw GET /trends response
export function TrendsPreview() {
  const trends = useQuery({ queryKey: ["trends"], queryFn: () => unwrap(api.GET("/trends")) });
  return <QueryResult query={trends}>{(data) => <JsonPreview data={data} label="Trends" />}</QueryResult>;
}
