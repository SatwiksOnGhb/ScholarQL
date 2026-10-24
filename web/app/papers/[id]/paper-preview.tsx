"use client";

import { useQuery } from "@tanstack/react-query";

import { JsonPreview } from "@/components/json-preview";
import { ErrorState, QueryResult } from "@/components/query-state";
import { api, unwrap } from "@/lib/api";

// TODO(A): placeholder; shows the raw paper and citation-graph responses
export function PaperPreview({ id }: { id: number }) {
  const valid = Number.isInteger(id) && id > 0;
  const paper = useQuery({
    queryKey: ["paper", id],
    queryFn: () => unwrap(api.GET("/papers/{paper_id}", { params: { path: { paper_id: id } } })),
    enabled: valid,
  });
  const citations = useQuery({
    queryKey: ["citations", id, 2],
    queryFn: () =>
      unwrap(
        api.GET("/papers/{paper_id}/citations", {
          params: { path: { paper_id: id }, query: { depth: 2 } },
        }),
      ),
    enabled: valid,
  });

  if (!valid) return <ErrorState error={new Error("Paper IDs are numbers, e.g. /papers/1001.")} />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <QueryResult query={paper}>{(data) => <JsonPreview data={data} label="Paper" />}</QueryResult>
      <QueryResult query={citations}>
        {(data) => <JsonPreview data={data} label="Citation graph (depth 2)" />}
      </QueryResult>
    </div>
  );
}
