"use client";

import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";

import { NativeSelect } from "@/components/native-select";
import { ErrorState, LoadingState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, type Schemas, unwrap } from "@/lib/api";

import { AuthorPicker } from "./author-picker";
import { ReviewerResults } from "./reviewer-results";

const MIN_CHARS = 20;
const EXAMPLE_ABSTRACT =
  "We study self-supervised contrastive learning of visual representations. Augmented views " +
  "of the same image are pulled together in embedding space while other images are pushed " +
  "apart, and a projection head with large batches improves linear evaluation on ImageNet.";

export function ReviewerFinder() {
  const abstractId = useId();
  const [abstract, setAbstract] = useState("");
  const [authors, setAuthors] = useState<Schemas["AuthorOption"][]>([]);
  const [k, setK] = useState(10);

  const find = useMutation({
    mutationFn: (body: Schemas["ReviewerRequest"]) =>
      unwrap(api.POST("/reviewers", { body })),
  });
  const tooShort = abstract.trim().length < MIN_CHARS;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          find.mutate({ abstract, author_ids: authors.map((a) => a.author_id), k });
        }}
      >
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <label htmlFor={abstractId} className="text-sm font-medium">
              Abstract
            </label>
            <button
              type="button"
              className="text-xs text-muted-foreground underline-offset-4 hover:underline"
              onClick={() => setAbstract(EXAMPLE_ABSTRACT)}
            >
              Use an example
            </button>
          </div>
          <Textarea
            id={abstractId}
            value={abstract}
            onChange={(e) => setAbstract(e.target.value)}
            rows={9}
            maxLength={5000}
            placeholder="Paste the submission's abstract…"
          />
          <p className="text-xs text-muted-foreground">{abstract.length} / 5000 characters</p>
        </div>

        <AuthorPicker selected={authors} onChange={setAuthors} />

        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Suggest</span>
            <NativeSelect value={k} onChange={(e) => setK(Number(e.target.value))}>
              {[5, 10, 20].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </NativeSelect>
            <span className="text-muted-foreground">reviewers</span>
          </label>
          <Button type="submit" disabled={tooShort || find.isPending}>
            {find.isPending ? "Finding…" : "Find reviewers"}
          </Button>
        </div>
      </form>

      <section aria-live="polite" aria-label="Suggested reviewers">
        {find.isPending ? (
          <LoadingState rows={4} />
        ) : find.isError ? (
          <ErrorState error={find.error} />
        ) : find.data ? (
          <ReviewerResults data={find.data} />
        ) : (
          <div className="rounded-lg border border-dashed p-8 text-sm text-muted-foreground">
            <p className="mb-2 font-medium text-foreground">How it works</p>
            <ol className="list-decimal space-y-1 pl-5">
              <li>Your abstract is compared with every author&apos;s research profile.</li>
              <li>
                The submitting authors, anyone who has co-authored with them, and anyone at their
                institutions are excluded.
              </li>
              <li>Each suggestion shows the papers that make them a good match.</li>
            </ol>
          </div>
        )}
      </section>
    </div>
  );
}
