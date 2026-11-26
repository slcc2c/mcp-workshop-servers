import type { TraceSpanItem } from "../types";

export interface WaterfallRow {
  span: TraceSpanItem;
  depth: number;
  offsetPct: number;
  widthPct: number;
  durationMs: number | null;
}

export interface WaterfallModel {
  rows: WaterfallRow[];
  totalMs: number;
}

/**
 * Build a depth-ordered parent-child waterfall timeline from flat MLflow spans.
 * Falls back gracefully to proportional duration bars if start/end timestamps are missing.
 */
export function buildSpanWaterfall(
  spans: TraceSpanItem[],
  traceDurationMs?: number | null,
): WaterfallModel {
  if (!spans || spans.length === 0) {
    return { rows: [], totalMs: traceDurationMs || 0 };
  }

  const byId = new Map<string, TraceSpanItem>();
  const children = new Map<string | null, TraceSpanItem[]>();
  for (const sp of spans) {
    byId.set(sp.spanId, sp);
  }
  for (const sp of spans) {
    const parentKey = sp.parentId && byId.has(sp.parentId) && sp.parentId !== sp.spanId ? sp.parentId : null;
    const bucket = children.get(parentKey);
    if (bucket) bucket.push(sp);
    else children.set(parentKey, [sp]);
  }

  for (const bucket of children.values()) {
    bucket.sort((a, b) => {
      const sa = typeof a.startTimeMs === "number" ? a.startTimeMs : Number.MAX_SAFE_INTEGER;
      const sb = typeof b.startTimeMs === "number" ? b.startTimeMs : Number.MAX_SAFE_INTEGER;
      return sa - sb;
    });
  }

  const ordered: Array<{ span: TraceSpanItem; depth: number }> = [];
  const visited = new Set<string>();
  function visit(parentId: string | null, depth: number) {
    const kids = children.get(parentId) || [];
    for (const sp of kids) {
      if (visited.has(sp.spanId)) continue;
      visited.add(sp.spanId);
      ordered.push({ span: sp, depth });
      visit(sp.spanId, depth + 1);
    }
  }
  visit(null, 0);
  // Catch any orphaned cycle members just in case
  for (const sp of spans) {
    if (!visited.has(sp.spanId)) {
      ordered.push({ span: sp, depth: 0 });
    }
  }

  const validStarts = ordered
    .map((o) => o.span.startTimeMs)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const validEnds = ordered
    .map((o) => o.span.endTimeMs)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));

  if (validStarts.length > 0 && validEnds.length > 0) {
    const minStart = Math.min(...validStarts);
    const maxEnd = Math.max(...validEnds);
    const spanRange = Math.max(maxEnd - minStart, traceDurationMs || 0, 0.01);
    const rows: WaterfallRow[] = ordered.map(({ span, depth }) => {
      const start = typeof span.startTimeMs === "number" ? span.startTimeMs : minStart;
      const dur =
        typeof span.durationMs === "number"
          ? span.durationMs
          : typeof span.endTimeMs === "number" && typeof span.startTimeMs === "number"
            ? Math.max(0, span.endTimeMs - span.startTimeMs)
            : 0;
      const rawOffset = ((start - minStart) / spanRange) * 100;
      const offsetPct = Math.max(0, Math.min(98, rawOffset));
      const rawWidth = (Math.max(0, dur) / spanRange) * 100;
      const widthPct = Math.max(2, Math.min(100 - offsetPct, rawWidth));
      return {
        span,
        depth,
        offsetPct: Number(offsetPct.toFixed(2)),
        widthPct: Number(widthPct.toFixed(2)),
        durationMs: span.durationMs ?? (dur > 0 ? dur : null),
      };
    });
    return { rows, totalMs: Number(spanRange.toFixed(2)) };
  }

  // Fallback: no startTimeMs -> proportional duration bars
  const maxDur = Math.max(
    traceDurationMs || 0,
    ...ordered.map((o) => (typeof o.span.durationMs === "number" ? o.span.durationMs : 0)),
    1,
  );
  const rows: WaterfallRow[] = ordered.map(({ span, depth }) => {
    const dur = typeof span.durationMs === "number" ? span.durationMs : 0;
    const widthPct = Math.max(4, Math.min(100, (dur / maxDur) * 100));
    return {
      span,
      depth,
      offsetPct: 0,
      widthPct: Number(widthPct.toFixed(2)),
      durationMs: span.durationMs ?? null,
    };
  });
  return { rows, totalMs: maxDur };
}
