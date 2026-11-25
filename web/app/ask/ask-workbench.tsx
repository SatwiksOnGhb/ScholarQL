"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, Copy, Info, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorState } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api, type Schemas, unwrap } from "@/lib/api";

import { ms, ROUTE_COLOR, ROUTE_LABEL, type Route } from "../admin/format";

type Answer = Schemas["AskResponse"];

// From B's demo list: one per kind of question the engine handles
const EXAMPLES = [
  { kind: "Aggregation", q: "Top 5 venues by average citations since 2021" },
  { kind: "Lookup", q: "Find arXiv paper 2305.14314" },
  { kind: "Recursive SQL", q: 'Show the citation chain from "Mistral 7B" up to depth 2' },
  { kind: "Set difference", q: 'Papers that cite "LoRA: Low-Rank Adaptation of Large Language Models" but not "Mistral 7B"' },
  { kind: "Semantic", q: "Explain how diffusion models generate images" },
  { kind: "Hybrid", q: "Find papers about adapting language models on a small GPU published since 2023" },
];

export function AskWorkbench() {
  const [question, setQuestion] = useState("");
  const ask = useMutation({
    mutationFn: (q: string) => unwrap(api.POST("/ask", { body: { question: q } })),
  });

  function submit(q: string) {
    const text = q.trim();
    if (text.length >= 3) ask.mutate(text);
  }

  return (
    <div className="space-y-6">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          aria-label="Question"
          placeholder="Ask about papers, authors, venues, citations…"
          maxLength={500}
        />
        <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>
          <Send data-icon="inline-start" />
          {ask.isPending ? "Asking…" : "Ask"}
        </Button>
      </form>

      <div className="flex flex-wrap gap-2" aria-label="Example questions">
        {EXAMPLES.map((e) => (
          <button
            key={e.q}
            type="button"
            className="rounded-full border px-3 py-1 text-left text-xs transition-colors hover:bg-muted"
            onClick={() => {
              setQuestion(e.q);
              submit(e.q);
            }}
          >
            <span className="text-muted-foreground">{e.kind}:</span> {e.q}
          </button>
        ))}
      </div>

      {ask.isError && <AskError error={ask.error} />}
      {ask.data && <AnswerView key={ask.data.query_id ?? ask.data.sql} answer={ask.data} />}
    </div>
  );
}

function AskError({ error }: { error: Error }) {
  // 422 = the engine understood the request but can't answer it; its message says what to try
  if (error instanceof ApiError && error.code === "unanswerable") {
    return (
      <Alert>
        <Info />
        <AlertTitle>The engine can&apos;t answer that yet</AlertTitle>
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    );
  }
  return <ErrorState error={error} />;
}

function AnswerView({ answer }: { answer: Answer }) {
  const route = answer.route as Route;
  return (
    <section className="space-y-4" aria-label="Answer">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge style={{ background: ROUTE_COLOR[route], color: "white" }}>{ROUTE_LABEL[route]}</Badge>
        <span className="text-muted-foreground">
          {answer.rows.length} {answer.rows.length === 1 ? "row" : "rows"} · {ms(answer.latency_ms)}
          {answer.attempts > 1 && ` · ${answer.attempts} attempts`}
        </span>
      </div>
      <p className="text-sm">{answer.explanation}</p>
      {answer.sql && <SqlBlock sql={answer.sql} />}
      <ResultsTable columns={answer.columns} rows={answer.rows} />
      {answer.query_id && <Feedback queryId={answer.query_id} />}
    </section>
  );
}

function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre
        aria-label="Generated SQL"
        className="max-h-80 overflow-auto rounded-lg border bg-muted/40 p-4 pr-12 font-mono text-xs leading-relaxed"
      >
        {sql}
      </pre>
      <Button
        size="icon-sm"
        variant="ghost"
        className="absolute top-2 right-2"
        aria-label="Copy SQL"
        onClick={() =>
          navigator.clipboard.writeText(sql).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          })
        }
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  );
}

function cell(column: string, value: unknown) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">–</span>;
  if (column === "paper_id" && typeof value === "string") {
    return (
      <Link href={`/papers/${value}`} className="font-mono text-xs underline underline-offset-4">
        {value}
      </Link>
    );
  }
  if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
  if (typeof value === "object") return <code className="text-xs">{JSON.stringify(value)}</code>;
  return String(value);
}

function ResultsTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        The query ran but returned no rows.
      </p>
    );
  }
  return (
    <div className="max-h-[32rem] overflow-auto rounded-lg border">
      <table className="w-full text-sm" aria-label="Results">
        <thead className="sticky top-0 bg-muted text-left">
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t align-top">
              {row.map((v, j) => (
                <td key={j} className="px-3 py-2">
                  {cell(columns[j], v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** POST /feedback for one logged answer; voting again replaces the earlier vote. */
function Feedback({ queryId }: { queryId: string }) {
  const send = useMutation({
    mutationFn: (correct: boolean) =>
      unwrap(api.POST("/feedback", { body: { query_id: queryId, correct } })).then(() => correct),
  });
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Was this answer right?</span>
      <Button size="sm" variant="outline" onClick={() => send.mutate(true)} disabled={send.isPending}>
        <ThumbsUp data-icon="inline-start" />
        Yes
      </Button>
      <Button size="sm" variant="outline" onClick={() => send.mutate(false)} disabled={send.isPending}>
        <ThumbsDown data-icon="inline-start" />
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
