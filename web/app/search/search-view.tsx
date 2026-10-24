"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { NativeSelect } from "@/components/native-select";
import { EmptyState, QueryResult } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, unwrap } from "@/lib/api";

import { SearchResults } from "./search-results";

const YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024]; // dataset scope
const EXAMPLES = [
  "contrastive self-supervised learning for images",
  "making large language models cheaper to fine-tune",
  "explaining predictions of black-box models",
];

function toInt(value: string | null): number | undefined {
  const n = Number(value);
  return value && Number.isInteger(n) ? n : undefined;
}

/** Search form + results. The query lives in the URL (?q=&year_from=&venue_id=) so it can be shared. */
export function SearchView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const q = params.get("q")?.trim() ?? "";
  const yearFrom = toInt(params.get("year_from"));
  const venueId = toInt(params.get("venue_id"));

  const [draft, setDraft] = useState(q);

  function update(next: { q?: string; year_from?: number; venue_id?: number }) {
    const merged = { q, year_from: yearFrom, venue_id: venueId, ...next };
    const search = new URLSearchParams();
    if (merged.q) search.set("q", merged.q);
    if (merged.year_from) search.set("year_from", String(merged.year_from));
    if (merged.venue_id) search.set("venue_id", String(merged.venue_id));
    router.replace(`${pathname}?${search}`, { scroll: false });
  }

  const venues = useQuery({
    queryKey: ["search-venues"],
    queryFn: () => unwrap(api.GET("/search/venues", { params: { query: { limit: 30 } } })),
    staleTime: 10 * 60_000,
  });

  const results = useQuery({
    queryKey: ["search", q, yearFrom, venueId],
    queryFn: () =>
      unwrap(
        api.GET("/search", {
          params: { query: { q, k: 20, year_from: yearFrom, venue_id: venueId } },
        }),
      ),
    enabled: q.length > 0,
  });

  return (
    <div className="space-y-6">
      <form
        role="search"
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: draft.trim() });
        }}
      >
        <div className="flex gap-2">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label="Search papers"
            placeholder="Describe what you're looking for…"
            maxLength={500}
          />
          <Button type="submit" disabled={!draft.trim()}>
            <Search data-icon="inline-start" />
            Search
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">From</span>
            <NativeSelect
              value={yearFrom ?? ""}
              onChange={(e) => update({ year_from: toInt(e.target.value) })}
            >
              <option value="">Any year</option>
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="flex min-w-0 items-center gap-2">
            <span className="text-muted-foreground">Venue</span>
            <NativeSelect
              className="max-w-64"
              value={venueId ?? ""}
              disabled={!venues.data}
              onChange={(e) => update({ venue_id: toInt(e.target.value) })}
            >
              <option value="">Any venue</option>
              {venues.data?.venues.map((v) => (
                <option key={v.venue_id} value={v.venue_id}>
                  {v.name} ({v.paper_count})
                </option>
              ))}
            </NativeSelect>
          </label>
        </div>
      </form>

      {!q ? (
        <EmptyState>
          <p className="mb-3">Try a description, not just keywords:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((example) => (
              <Button
                key={example}
                variant="outline"
                size="sm"
                onClick={() => {
                  setDraft(example);
                  update({ q: example });
                }}
              >
                {example}
              </Button>
            ))}
          </div>
        </EmptyState>
      ) : (
        <QueryResult query={results}>
          {(data) => <SearchResults hits={data.results} filtered={Boolean(yearFrom || venueId)} />}
        </QueryResult>
      )}
    </div>
  );
}
