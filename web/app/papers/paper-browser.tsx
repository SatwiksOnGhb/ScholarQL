"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { NativeSelect } from "@/components/native-select";
import { EmptyState, QueryResult } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, unwrap } from "@/lib/api";
import { useDebouncedValue } from "@/lib/use-debounced-value";

const YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024];
const SORTS = { citations: "Most cited", pagerank: "PageRank", year: "Newest" } as const;
const PAGE = 20;

/** Paper library from PostgreSQL: title search, year filter, sort by citations or PageRank. */
export function PaperBrowser() {
  const [q, setQ] = useState("");
  const [year, setYear] = useState<number | undefined>();
  const [sort, setSort] = useState<keyof typeof SORTS>("citations");
  const [offset, setOffset] = useState(0);
  const title = useDebouncedValue(q.trim(), 300);

  const papers = useQuery({
    queryKey: ["papers", title, year, sort, offset],
    queryFn: () =>
      unwrap(
        api.GET("/papers", {
          params: {
            query: {
              q: title || undefined,
              year_from: year,
              year_to: year,
              sort,
              limit: PAGE,
              offset,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });

  return (
    <section className="space-y-4" aria-labelledby="library-heading">
      <h2 id="library-heading" className="text-lg font-semibold">
        Paper library
      </h2>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Input
          className="max-w-xs"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          aria-label="Filter by title"
          placeholder="Words in the title…"
        />
        <NativeSelect
          aria-label="Year"
          value={year ?? ""}
          onChange={(e) => {
            setYear(e.target.value ? Number(e.target.value) : undefined);
            setOffset(0);
          }}
        >
          <option value="">Any year</option>
          {YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Sort"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value as keyof typeof SORTS);
            setOffset(0);
          }}
        >
          {Object.entries(SORTS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </div>

      <QueryResult query={papers}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState>No papers match.</EmptyState>
          ) : (
            <>
              <ol className="divide-y rounded-lg border" aria-label="Papers">
                {data.items.map((p) => (
                  <li key={p.paper_id} className="flex items-baseline justify-between gap-4 p-3">
                    <div className="min-w-0">
                      <Link href={`/papers/${p.paper_id}`} className="font-medium hover:underline">
                        {p.title}
                      </Link>
                      <p className="truncate text-xs text-muted-foreground">
                        {[p.year, p.venue_name, p.authors.slice(0, 3).join(", ")]
                          .filter(Boolean)
                          .join(" · ")}
                        {p.authors.length > 3 && " et al."}
                      </p>
                    </div>
                    <span
                      className="shrink-0 text-xs text-muted-foreground tabular-nums"
                      title="Citations in the corpus"
                    >
                      {p.citation_count} cit.
                    </span>
                  </li>
                ))}
              </ol>
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  {offset + 1}–{offset + data.items.length} of {data.total}
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={offset + PAGE >= data.total}
                    onClick={() => setOffset(offset + PAGE)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )
        }
      </QueryResult>
    </section>
  );
}
