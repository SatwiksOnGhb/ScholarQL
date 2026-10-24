"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { JsonPreview } from "@/components/json-preview";
import { QueryResult } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, unwrap } from "@/lib/api";

// Placeholder: raw GET /search results. The real results list and filters come in task 8.
export function SearchPreview() {
  const [draft, setDraft] = useState("diffusion models");
  const [q, setQ] = useState(draft);
  const results = useQuery({
    queryKey: ["search", q],
    queryFn: () => unwrap(api.GET("/search", { params: { query: { q, k: 5 } } })),
    enabled: q.length > 0,
  });

  return (
    <div className="space-y-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(draft.trim());
        }}
      >
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="Search query"
          placeholder="Describe what you're looking for…"
        />
        <Button type="submit">Search</Button>
      </form>
      {q && (
        <QueryResult query={results}>
          {(data) => <JsonPreview data={data} label="Results" />}
        </QueryResult>
      )}
    </div>
  );
}
