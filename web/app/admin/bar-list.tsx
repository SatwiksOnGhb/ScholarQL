/** Ranked horizontal bars for long labels (questions, error types). Single series, so one
 * color and no legend; the value sits at the bar tip in text color. */
export function BarList({
  items,
  ariaLabel,
}: {
  items: { label: string; value: number }[];
  ariaLabel: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ol className="space-y-3" aria-label={ariaLabel}>
      {items.map((item) => (
        <li key={item.label} className="space-y-1">
          <p className="truncate text-sm" title={item.label}>
            {item.label}
          </p>
          <div className="flex items-center gap-2">
            <div
              className="h-2 rounded-r-[4px]"
              style={{
                width: `${Math.max((item.value / max) * 100, 1)}%`,
                background: "var(--bar-single)",
              }}
              aria-hidden="true"
            />
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {item.value}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}
