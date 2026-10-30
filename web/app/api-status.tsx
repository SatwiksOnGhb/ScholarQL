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
    // Keep trying until it answers: Render's free plan takes about a minute to wake up
    retry: true,
    retryDelay: 5_000,
  });

  if (health.failureReason) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="destructive">API not responding · retrying</Badge>
        <span className="text-xs text-muted-foreground">{health.failureReason.message}</span>
      </div>
    );
  }
  if (!health.data) return <Badge variant="outline">Checking API…</Badge>;

  const { status, postgres, mongodb } = health.data;
  return (
    <Badge variant={status === "ok" ? "secondary" : "destructive"}>
      API {status} · PostgreSQL {postgres} · MongoDB {mongodb}
    </Badge>
  );
}
