"use client";

import { useMutation } from "@tanstack/react-query";

import { JsonPreview } from "@/components/json-preview";
import { ErrorState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { api, unwrap } from "@/lib/api";

const SAMPLE = {
  abstract:
    "We propose a diffusion-based generative model for high-resolution image synthesis " +
    "that trains stably and samples in fewer steps.",
  author_ids: [5004], // fake author; they and their co-authors are excluded
  k: 5,
};

// Placeholder: raw POST /reviewers response for a sample abstract. The real form comes in task 9.
export function ReviewersPreview() {
  const find = useMutation({
    mutationFn: () => unwrap(api.POST("/reviewers", { body: SAMPLE })),
  });

  return (
    <div className="space-y-4">
      <JsonPreview data={SAMPLE} label="Sample request" />
      <Button onClick={() => find.mutate()} disabled={find.isPending}>
        {find.isPending ? "Finding…" : "Find reviewers"}
      </Button>
      {find.isError && <ErrorState error={find.error} />}
      {find.data && <JsonPreview data={find.data} label="Response" />}
    </div>
  );
}
