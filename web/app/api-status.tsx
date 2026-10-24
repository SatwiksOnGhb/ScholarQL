"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { api, unwrap } from "@/lib/api";

/** Small badge showing whether the API and both databases are reachable. */
export function ApiStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => unwrap(api.GET("/health")),
    refetchInterval: 30_000,
  });

  if (health.isPending) return <Badge variant="outline">Checking API…</Badge>;
  if (health.isError) return <Badge variant="destructive">API unreachable</Badge>;

  const { status, postgres, mongodb } = health.data;
  return (
    <Badge variant={status === "ok" ? "secondary" : "destructive"}>
      API {status} · PostgreSQL {postgres} · MongoDB {mongodb}
    </Badge>
  );
}
