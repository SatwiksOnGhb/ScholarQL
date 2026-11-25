"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { NativeSelect } from "@/components/native-select";
import { EmptyState, QueryResult } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { api, type Schemas, unwrap } from "@/lib/api";

type Paper = Schemas["Paper"];
type Graph = Schemas["CitationGraph"];

export function PaperView({ id }: { id: string }) {
  const paper = useQuery({
    queryKey: ["paper", id],
    queryFn: () => unwrap(api.GET("/papers/{paper_id}", { params: { path: { paper_id: id } } })),
  });
  return (
    <QueryResult query={paper}>
      {(p) => (
        <div className="space-y-8">
          <PaperDetails paper={p} />
          <CitationExplorer id={p.paper_id} />
        </div>
      )}
    </QueryResult>
  );
}

function PaperDetails({ paper }: { paper: Paper }) {
  const links = [
    paper.arxiv_id && { label: "arXiv", href: `https://arxiv.org/abs/${paper.arxiv_id}` },
    paper.doi && { label: "DOI", href: `https://doi.org/${paper.doi}` },
    paper.paper_id.startsWith("W") && {
      label: "OpenAlex",
      href: `https://openalex.org/${paper.paper_id}`,
    },
  ].filter(Boolean) as { label: string; href: string }[];

  return (
    <article className="space-y-4">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold leading-snug">{paper.title}</h2>
        <p className="text-sm text-muted-foreground">
          {[paper.year, paper.venue?.name].filter(Boolean).join(" · ")}
        </p>
      </div>

      <p className="text-sm">
        {paper.authors.map((a, i) => (
          <span key={a.author_id}>
            {i > 0 && ", "}
            <span className="font-medium">{a.name}</span>
            {a.institution && (
              <span className="text-muted-foreground"> ({a.institution.name})</span>
            )}
          </span>
        ))}
      </p>

      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <dt className="text-muted-foreground">Citations in corpus</dt>
          <dd className="font-medium tabular-nums">{paper.citation_count}</dd>
        </div>
        {paper.pagerank != null && (
          <div>
            <dt className="text-muted-foreground">PageRank</dt>
            <dd className="font-medium tabular-nums">{paper.pagerank.toFixed(5)}</dd>
          </div>
        )}
        {links.length > 0 && (
          <div>
            <dt className="text-muted-foreground">Links</dt>
            <dd className="flex gap-3">
              {links.map((l) => (
                <a
                  key={l.label}
                  href={l.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 underline underline-offset-4"
                >
                  {l.label}
                  <ExternalLink className="size-3" />
                </a>
              ))}
            </dd>
          </div>
        )}
      </dl>

      {paper.topics.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Topics">
          {paper.topics.map((t) => (
            <li key={t.topic_id}>
              <Badge variant="secondary">{t.name}</Badge>
            </li>
          ))}
        </ul>
      )}

      {paper.tldr && (
        <p className="rounded-lg bg-muted/50 p-3 text-sm">
          <span className="font-medium">TL;DR </span>
          {paper.tldr}
        </p>
      )}
      {paper.abstract && <p className="text-sm leading-relaxed">{paper.abstract}</p>}
    </article>
  );
}

function CitationExplorer({ id }: { id: string }) {
  const [depth, setDepth] = useState(1);
  const graph = useQuery({
    queryKey: ["citations", id, depth],
    queryFn: () =>
      unwrap(
        api.GET("/papers/{paper_id}/citations", {
          params: { path: { paper_id: id }, query: { depth } },
        }),
      ),
  });

  return (
    <section className="space-y-4" aria-labelledby="citations-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="citations-heading" className="text-lg font-semibold">
          Citation explorer
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Hops</span>
          <NativeSelect value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[1, 2, 3].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </NativeSelect>
        </label>
      </div>
      <QueryResult query={graph}>{(g) => <CitationLists graph={g} />}</QueryResult>
    </section>
  );
}

/** Direct references and citations of the root, plus papers further out grouped by hop. */
function CitationLists({ graph }: { graph: Graph }) {
  const byId = new Map(graph.nodes.map((n) => [n.paper_id, n]));
  const refs = graph.edges.filter((e) => e.citing_id === graph.root_id).map((e) => e.cited_id);
  const citedBy = graph.edges.filter((e) => e.cited_id === graph.root_id).map((e) => e.citing_id);
  const further = graph.nodes.filter((n) => n.depth >= 2);

  if (graph.nodes.length <= 1) {
    return (
      <EmptyState>
        No citations to or from other papers in the corpus. The pilot holds only links between
        its own 353 papers.
      </EmptyState>
    );
  }
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <PaperList title={`References (${refs.length})`} ids={refs} byId={byId} />
      <PaperList title={`Cited by (${citedBy.length})`} ids={citedBy} byId={byId} />
      {further.length > 0 && (
        <div className="md:col-span-2">
          <PaperList
            title={`Further out (${further.length})`}
            ids={further.map((n) => n.paper_id)}
            byId={byId}
            showDepth
          />
        </div>
      )}
      {graph.truncated && (
        <p className="text-sm text-muted-foreground md:col-span-2">
          Showing the first {graph.nodes.length} papers; pick fewer hops for the full list.
        </p>
      )}
    </div>
  );
}

function PaperList({
  title,
  ids,
  byId,
  showDepth = false,
}: {
  title: string;
  ids: string[];
  byId: Map<string, Graph["nodes"][number]>;
  showDepth?: boolean;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      {ids.length === 0 ? (
        <p className="text-sm text-muted-foreground">None in the corpus.</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {ids.map((pid) => {
            const n = byId.get(pid);
            return (
              <li key={pid} className="flex items-baseline justify-between gap-3">
                <Link href={`/papers/${pid}`} className="min-w-0 truncate hover:underline">
                  {n?.title ?? pid}
                </Link>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {showDepth && n ? `${n.depth} hops · ` : ""}
                  {n?.year}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
