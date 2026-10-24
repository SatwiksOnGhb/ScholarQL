import { ShieldCheck } from "lucide-react";

import { EmptyState } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api";

type Response = Schemas["ReviewerResponse"];

export function ReviewerResults({ data }: { data: Response }) {
  return (
    <div className="space-y-4">
      <ConflictSummary data={data} />
      {data.reviewers.length === 0 ? (
        <EmptyState>No suitable reviewers found.</EmptyState>
      ) : (
        <ol className="space-y-3">
          {data.reviewers.map((r, i) => (
            <li key={r.author_id}>
              <ReviewerCard reviewer={r} rank={i + 1} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ConflictSummary({ data }: { data: Response }) {
  const coauthors = data.excluded_authors.filter((a) => a.reason === "coauthor");
  const institutions = data.excluded_institutions.map((i) => i.name ?? `Institution ${i.institution_id}`);
  if (data.excluded_authors.length === 0) return null;
  return (
    <div className="flex gap-3 rounded-lg border bg-muted/40 p-3 text-sm">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="space-y-1">
        <p className="font-medium">Conflict-of-interest check</p>
        <p className="text-muted-foreground">
          Excluded {coauthors.length} co-author{coauthors.length === 1 ? "" : "s"}
          {coauthors.length > 0 && (
            <>
              {" "}
              ({coauthors
                .slice(0, 5)
                .map((a) => a.name ?? a.author_id)
                .join(", ")}
              {coauthors.length > 5 && `, +${coauthors.length - 5} more`})
            </>
          )}
          {institutions.length > 0 && <> and everyone at {institutions.join(", ")}</>}.
        </p>
      </div>
    </div>
  );
}

function ReviewerCard({ reviewer, rank }: { reviewer: Schemas["Reviewer"]; rank: number }) {
  return (
    <article className="rounded-lg border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-medium">
            <span className="mr-2 text-muted-foreground tabular-nums">{rank}.</span>
            {reviewer.name}
          </h3>
          {/* Only the institution shrinks, so the paper count is always readable */}
          <p className="flex min-w-0 gap-1 text-sm text-muted-foreground">
            {reviewer.institution_name && (
              <>
                <span className="truncate" title={reviewer.institution_name}>
                  {reviewer.institution_name}
                </span>
                <span aria-hidden="true">·</span>
              </>
            )}
            <span className="shrink-0">
              {reviewer.paper_count} {reviewer.paper_count === 1 ? "paper" : "papers"} in the
              dataset
            </span>
          </p>
        </div>
        <Badge variant="secondary" className="shrink-0 tabular-nums" title="Profile similarity">
          {reviewer.score.toFixed(2)}
        </Badge>
      </div>
      {reviewer.matching_papers.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Why
          </p>
          <ul className="space-y-1 text-sm">
            {reviewer.matching_papers.map((p) => (
              <li key={p.paper_id} className="flex items-baseline justify-between gap-3">
                <a
                  href={`https://openalex.org/W${p.paper_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="min-w-0 truncate hover:underline"
                  title={p.title}
                >
                  {p.title}
                </a>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {p.year} · {p.score.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
