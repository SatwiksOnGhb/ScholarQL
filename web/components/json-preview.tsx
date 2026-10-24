/** Raw API response viewer for placeholder pages. */
export function JsonPreview({ data, label }: { data: unknown; label?: string }) {
  return (
    <div className="space-y-2">
      {label && <p className="text-sm font-medium text-muted-foreground">{label}</p>}
      <pre className="max-h-[28rem] overflow-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
