"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { JsonPreview } from "@/components/json-preview";
import { ErrorState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, unwrap } from "@/lib/api";

// TODO(B): placeholder; shows the raw Answer from POST /ask
export function AskPreview() {
  const [question, setQuestion] = useState("Papers published at NeurIPS in 2020");
  const ask = useMutation({
    mutationFn: (q: string) => unwrap(api.POST("/ask", { body: { question: q } })),
  });

  return (
    <div className="space-y-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask.mutate(question);
        }}
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          aria-label="Question"
          placeholder="Ask about papers, authors, venues…"
        />
        <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>
          {ask.isPending ? "Asking…" : "Ask"}
        </Button>
      </form>
      {ask.isError && <ErrorState error={ask.error} />}
      {ask.data && <JsonPreview data={ask.data} label="Answer" />}
    </div>
  );
}
