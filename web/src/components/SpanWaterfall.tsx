import { useMemo } from "react";
import type { TraceSpanItem } from "../types";
import { formatDuration } from "../lib/format";
import { buildSpanWaterfall } from "../lib/waterfall";

export function SpanWaterfall({
  spans,
  traceDurationMs,
  selectedSpanId,
  onSelectSpan,
}: {
  spans: TraceSpanItem[];
  traceDurationMs?: number | null;
  selectedSpanId?: string | null;
  onSelectSpan?: (spanId: string) => void;
}) {
  const waterfall = useMemo(
    () => buildSpanWaterfall(spans, traceDurationMs),
    [spans, traceDurationMs],
  );

  if (waterfall.rows.length === 0) return null;

  return (
    <div
      className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-canvas)] p-3.5 space-y-2"
      data-testid="span-waterfall"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Span Waterfall ({waterfall.rows.length} spans)
        </span>
        <span className="font-mono text-[11px] text-[var(--text-muted)] tabular-nums">
          Total {formatDuration(traceDurationMs ?? waterfall.totalMs)}
        </span>
      </div>

      <div className="divide-y divide-[var(--border-hairline)]">
        {waterfall.rows.map((row) => {
          const isError = row.span.status === "ERROR";
          const isSelected = selectedSpanId === row.span.spanId;
          return (
            <button
              key={row.span.spanId}
              type="button"
              onClick={() => onSelectSpan?.(row.span.spanId)}
              className={`w-full text-left py-2 px-2 grid grid-cols-[minmax(140px,1.2fr)_minmax(110px,1.4fr)_68px] items-center gap-3 rounded transition-colors cursor-pointer ${
                isSelected ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--bg-hover)]"
              }`}
            >
              <div
                className="min-w-0 flex items-center gap-1.5"
                style={{ paddingLeft: `${Math.min(row.depth, 5) * 14}px` }}
              >
                {row.depth > 0 && (
                  <span className="text-[var(--text-muted)] font-mono text-[11px] shrink-0">└</span>
                )}
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    isError ? "bg-[var(--err)]" : "bg-[var(--ok)]"
                  }`}
                />
                <span className="font-mono text-[12px] truncate text-[var(--text-primary)]">
                  {row.span.name}
                </span>
              </div>

              <div className="h-2.5 rounded-full bg-[var(--bg-subtle)] relative overflow-hidden">
                <div
                  className={`h-full rounded-full ${isError ? "bg-[var(--err)]" : "bg-[var(--accent)]"}`}
                  style={{
                    marginLeft: `${row.offsetPct}%`,
                    width: `${row.widthPct}%`,
                  }}
                />
              </div>

              <div className="font-mono text-[11.5px] text-right tabular-nums text-[var(--text-secondary)]">
                {formatDuration(row.durationMs)}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
