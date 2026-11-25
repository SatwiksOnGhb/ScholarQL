import Link from "next/link";

import { EmptyState } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api";

type Hit = Schemas["SearchHit"];

export function SearchResults({ hits, filtered }: { hits: Hit[]; filtered: boolean }) {
  if (hits.length === 0) {
    return (
      <EmptyState>
        No papers matched.{filtered && " Try removing the year or venue filter."}
      </EmptyState>
    );
  }
  return (
    <ol className="space-y-3" aria-label="Search results">
      {hits.map((hit) => (
        <li key={hit.paper_id}>
          <ResultCard hit={hit} />
        </li>
      ))}
    </ol>
  );
}

function ResultCard({ hit }: { hit: Hit }) {
  const meta = [hit.year, hit.venue_name].filter(Boolean).join(" · ");
  return (
    <article className="rounded-lg border p-4 transition-colors hover:bg-muted/30">
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-medium leading-snug">
          <Link href={`/papers/${hit.paper_id}`} className="hover:underline">
            {hit.title}
          </Link>
        </h2>
        <Badge variant="secondary" className="shrink-0 tabular-nums" title="Similarity score">
          {hit.score.toFixed(2)}
        </Badge>
      </div>
      {meta && <p className="mt-1 truncate text-sm text-muted-foreground">{meta}</p>}
      {(hit.tldr || hit.abstract) && (
        <p className="mt-2 line-clamp-3 text-sm">{hit.tldr ?? hit.abstract}</p>
      )}
    </article>
  );
}
