import { normalizeMultilineText } from "./format";

export interface DiffLine {
  type: "equal" | "add" | "remove";
  oldLine: number | null;
  newLine: number | null;
  text: string;
}

export interface DiffResult {
  lines: DiffLine[];
  added: number;
  removed: number;
  unchanged: number;
}

export interface SideBySideRow {
  left: DiffLine | null;
  right: DiffLine | null;
}

const MAX_LCS_CELLS = 400_000;

/** Compute a clean line-level diff using LCS with bounded memory fallback for huge templates. */
export function computeLineDiff(baseText: string, targetText: string): DiffResult {
  const a = normalizeMultilineText(baseText).split("\n");
  const b = normalizeMultilineText(targetText).split("\n");
  const m = a.length;
  const n = b.length;

  const lines: DiffLine[] = [];
  if (m * n > MAX_LCS_CELLS) {
    // Prefix/suffix trim fallback for very large templates
    let start = 0;
    while (start < m && start < n && a[start] === b[start]) {
      lines.push({ type: "equal", oldLine: start + 1, newLine: start + 1, text: a[start] });
      start += 1;
    }
    let endA = m - 1;
    let endB = n - 1;
    const tail: DiffLine[] = [];
    while (endA >= start && endB >= start && a[endA] === b[endB]) {
      tail.unshift({ type: "equal", oldLine: endA + 1, newLine: endB + 1, text: a[endA] });
      endA -= 1;
      endB -= 1;
    }
    for (let i = start; i <= endA; i += 1) {
      lines.push({ type: "remove", oldLine: i + 1, newLine: null, text: a[i] });
    }
    for (let j = start; j <= endB; j += 1) {
      lines.push({ type: "add", oldLine: null, newLine: j + 1, text: b[j] });
    }
    lines.push(...tail);
  } else {
    const dp = new Int32Array((m + 1) * (n + 1));
    const stride = n + 1;
    for (let i = m - 1; i >= 0; i -= 1) {
      for (let j = n - 1; j >= 0; j -= 1) {
        if (a[i] === b[j]) {
          dp[i * stride + j] = dp[(i + 1) * stride + (j + 1)] + 1;
        } else {
          const down = dp[(i + 1) * stride + j];
          const right = dp[i * stride + (j + 1)];
          dp[i * stride + j] = down >= right ? down : right;
        }
      }
    }

    let i = 0;
    let j = 0;
    while (i < m && j < n) {
      if (a[i] === b[j]) {
        lines.push({ type: "equal", oldLine: i + 1, newLine: j + 1, text: a[i] });
        i += 1;
        j += 1;
      } else if (dp[(i + 1) * stride + j] >= dp[i * stride + (j + 1)]) {
        lines.push({ type: "remove", oldLine: i + 1, newLine: null, text: a[i] });
        i += 1;
      } else {
        lines.push({ type: "add", oldLine: null, newLine: j + 1, text: b[j] });
        j += 1;
      }
    }
    while (i < m) {
      lines.push({ type: "remove", oldLine: i + 1, newLine: null, text: a[i] });
      i += 1;
    }
    while (j < n) {
      lines.push({ type: "add", oldLine: null, newLine: j + 1, text: b[j] });
      j += 1;
    }
  }

  let added = 0;
  let removed = 0;
  let unchanged = 0;
  for (const line of lines) {
    if (line.type === "add") added += 1;
    else if (line.type === "remove") removed += 1;
    else unchanged += 1;
  }
  return { lines, added, removed, unchanged };
}

/** Pair consecutive remove/add hunks cleanly for side-by-side rendering. */
export function buildSideBySideRows(lines: DiffLine[]): SideBySideRow[] {
  const rows: SideBySideRow[] = [];
  let idx = 0;
  while (idx < lines.length) {
    const cur = lines[idx];
    if (cur.type === "equal") {
      rows.push({ left: cur, right: cur });
      idx += 1;
      continue;
    }
    const removals: DiffLine[] = [];
    const additions: DiffLine[] = [];
    while (idx < lines.length && lines[idx].type !== "equal") {
      if (lines[idx].type === "remove") removals.push(lines[idx]);
      else additions.push(lines[idx]);
      idx += 1;
    }
    const pairCount = Math.max(removals.length, additions.length);
    for (let k = 0; k < pairCount; k += 1) {
      rows.push({
        left: removals[k] ?? null,
        right: additions[k] ?? null,
      });
    }
  }
  return rows;
}
