"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { api, unwrap } from "@/lib/api";

// Render's free plan sleeps after 15 idle minutes and takes up to a minute to wake;
// a redeploy restarts it too. Only call the API down after it has failed for this long.
const DOWN_AFTER_FAILURES = 18; // x 5 s = 90 s

/** Small badge showing whether the API and both databases are reachable. */
export function ApiStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => unwrap(api.GET("/health")),
    refetchInterval: 30_000,
    retry: true,
    retryDelay: 5_000,
  });

  // Once the API has answered, a failed background check doesn't change the badge
  if (health.data) {
    const { status, postgres, mongodb } = health.data;
    return (
      <Badge variant={status === "ok" ? "secondary" : "destructive"}>
        API {status} · PostgreSQL {postgres} · MongoDB {mongodb}
      </Badge>
    );
  }
  if (health.failureCount >= DOWN_AFTER_FAILURES) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="destructive">API not responding · retrying</Badge>
        <span className="text-xs text-muted-foreground">{health.failureReason?.message}</span>
      </div>
    );
  }
  if (health.failureCount > 0) {
    return <Badge variant="outline">Waking up the API (free hosting, up to a minute)…</Badge>;
  }
  return <Badge variant="outline">Checking API…</Badge>;
}
