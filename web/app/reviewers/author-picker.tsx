"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api, type Schemas, unwrap } from "@/lib/api";
import { useDebouncedValue } from "@/lib/use-debounced-value";

type Author = Schemas["AuthorOption"];

/** Pick submitting authors by name; selected ones show as removable chips. */
export function AuthorPicker({
  selected,
  onChange,
}: {
  selected: Author[];
  onChange: (authors: Author[]) => void;
}) {
  const inputId = useId();
  const [text, setText] = useState("");
  const q = useDebouncedValue(text.trim());

  const matches = useQuery({
    queryKey: ["author-picker", q],
    queryFn: () => unwrap(api.GET("/reviewers/authors", { params: { query: { q, limit: 8 } } })),
    enabled: q.length >= 2,
  });
  const options = (matches.data?.authors ?? []).filter(
    (a) => !selected.some((s) => s.author_id === a.author_id),
  );

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="text-sm font-medium">
        Submitting authors <span className="font-normal text-muted-foreground">(optional)</span>
      </label>
      {selected.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Selected authors">
          {selected.map((a) => (
            <li key={a.author_id}>
              <Badge variant="secondary" className="gap-1 pr-1">
                {a.name}
                <button
                  type="button"
                  onClick={() => onChange(selected.filter((s) => s.author_id !== a.author_id))}
                  className="rounded-sm p-0.5 hover:bg-muted-foreground/20"
                  aria-label={`Remove ${a.name}`}
                >
                  <X className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      )}
      <div className="relative">
        <Input
          id={inputId}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a name, e.g. Ting Chen"
          autoComplete="off"
        />
        {q.length >= 2 && text.trim().length >= 2 && (
          <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border bg-popover shadow-md">
            {matches.isPending ? (
              <p className="px-3 py-2 text-sm text-muted-foreground">Searching…</p>
            ) : options.length === 0 ? (
              <p className="px-3 py-2 text-sm text-muted-foreground">No matching authors</p>
            ) : (
              <ul aria-label="Matching authors">
                {options.map((a) => (
                  <li key={a.author_id}>
                    <button
                      type="button"
                      className="flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-muted"
                      onClick={() => {
                        onChange([...selected, a]);
                        setText("");
                      }}
                    >
                      <span>
                        {a.name}
                        {a.institution_name && (
                          <span className="text-muted-foreground"> · {a.institution_name}</span>
                        )}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {a.paper_count} {a.paper_count === 1 ? "paper" : "papers"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
