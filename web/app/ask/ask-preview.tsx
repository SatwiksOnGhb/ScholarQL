"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { JsonPreview } from "@/components/json-preview";
import { ErrorState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, unwrap } from "@/lib/api";

// TODO(B): placeholder; shows the raw Answer from POST /ask plus minimal feedback buttons
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
      {ask.data?.query_id && <FeedbackButtons key={ask.data.query_id} queryId={ask.data.query_id} />}
      {ask.data && <JsonPreview data={ask.data} label="Answer" />}
    </div>
  );
}

/** Sends POST /feedback for one logged answer; voting again replaces the earlier vote. */
function FeedbackButtons({ queryId }: { queryId: string }) {
  const send = useMutation({
    mutationFn: (correct: boolean) =>
      unwrap(api.POST("/feedback", { body: { query_id: queryId, correct } })).then(() => correct),
  });

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Was this answer right?</span>
      <Button size="sm" variant="outline" onClick={() => send.mutate(true)} disabled={send.isPending}>
        Yes
      </Button>
      <Button size="sm" variant="outline" onClick={() => send.mutate(false)} disabled={send.isPending}>
        No
      </Button>
      {send.isSuccess && (
        <span role="status" className="text-muted-foreground">
          Thanks, saved as {send.data ? "correct" : "incorrect"}.
        </span>
      )}
      {send.isError && <span className="text-destructive">{send.error.message}</span>}
    </div>
  );
}
