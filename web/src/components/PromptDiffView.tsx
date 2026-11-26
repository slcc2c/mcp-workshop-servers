import { useMemo, useState } from "react";
import { buildSideBySideRows, computeLineDiff } from "../lib/diff";

export function PromptDiffView({
  baseLabel,
  targetLabel,
  baseTemplate,
  targetTemplate,
}: {
  baseLabel: string;
  targetLabel: string;
  baseTemplate: string;
  targetTemplate: string;
}) {
  const [mode, setMode] = useState<"side-by-side" | "unified">("side-by-side");
  const diff = useMemo(
    () => computeLineDiff(baseTemplate, targetTemplate),
    [baseTemplate, targetTemplate],
  );
  const sideRows = useMemo(() => buildSideBySideRows(diff.lines), [diff.lines]);

  return (
    <div className="space-y-3" data-testid="prompt-diff-view">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-[12px] font-mono">
          <span className="text-[var(--text-secondary)]">
            {baseLabel} → {targetLabel}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-[var(--ok-soft)] text-[var(--ok)] tabular-nums">
            +{diff.added}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-[var(--err-soft)] text-[var(--err)] tabular-nums">
            -{diff.removed}
          </span>
          <span className="text-[var(--text-muted)] tabular-nums">{diff.unchanged} same</span>
        </div>

        <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
          <button
            type="button"
            onClick={() => setMode("side-by-side")}
            className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium cursor-pointer ${
              mode === "side-by-side"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)]"
            }`}
          >
            Side-by-Side
          </button>
          <button
            type="button"
            onClick={() => setMode("unified")}
            className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium cursor-pointer ${
              mode === "unified"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)]"
            }`}
          >
            Unified
          </button>
        </div>
      </div>

      {diff.added === 0 && diff.removed === 0 ? (
        <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-4 py-6 text-center text-[12.5px] text-[var(--text-muted)]">
          Both versions have identical template text.
        </div>
      ) : mode === "unified" ? (
        <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] overflow-x-auto font-mono text-[12px]">
          {diff.lines.map((line, idx) => {
            const bg =
              line.type === "add"
                ? "bg-[var(--ok-soft)] text-[var(--text-primary)]"
                : line.type === "remove"
                  ? "bg-[var(--err-soft)] text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]";
            const sign = line.type === "add" ? "+" : line.type === "remove" ? "-" : " ";
            return (
              <div key={idx} className={`grid grid-cols-[40px_40px_20px_minmax(0,1fr)] px-2 py-0.5 ${bg}`}>
                <span className="text-[var(--text-muted)] select-none tabular-nums text-right pr-2">
                  {line.oldLine ?? ""}
                </span>
                <span className="text-[var(--text-muted)] select-none tabular-nums text-right pr-2">
                  {line.newLine ?? ""}
                </span>
                <span
                  className={`select-none font-bold ${
                    line.type === "add"
                      ? "text-[var(--ok)]"
                      : line.type === "remove"
                        ? "text-[var(--err)]"
                        : "text-[var(--text-muted)]"
                  }`}
                >
                  {sign}
                </span>
                <span className="whitespace-pre-wrap break-words">{line.text || " "}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] overflow-x-auto font-mono text-[12px]">
          <div className="border-b md:border-b-0 md:border-r border-[var(--border-hairline)]">
            <div className="px-3 py-1.5 border-b border-[var(--border-hairline)] bg-[var(--bg-subtle)] text-[11px] font-semibold text-[var(--text-muted)]">
              {baseLabel}
            </div>
            {sideRows.map((row, idx) => {
              const isRem = row.left?.type === "remove";
              return (
                <div
                  key={`l-${idx}`}
                  className={`grid grid-cols-[36px_minmax(0,1fr)] px-2 py-0.5 min-h-[22px] ${
                    isRem
                      ? "bg-[var(--err-soft)] text-[var(--text-primary)]"
                      : row.left
                        ? "text-[var(--text-secondary)]"
                        : "bg-[var(--bg-subtle)]/40"
                  }`}
                >
                  <span className="text-[var(--text-muted)] select-none tabular-nums text-right pr-2">
                    {row.left?.oldLine ?? ""}
                  </span>
                  <span className="whitespace-pre-wrap break-words">{row.left?.text ?? ""}</span>
                </div>
              );
            })}
          </div>
          <div>
            <div className="px-3 py-1.5 border-b border-[var(--border-hairline)] bg-[var(--bg-subtle)] text-[11px] font-semibold text-[var(--text-muted)]">
              {targetLabel}
            </div>
            {sideRows.map((row, idx) => {
              const isAdd = row.right?.type === "add";
              return (
                <div
                  key={`r-${idx}`}
                  className={`grid grid-cols-[36px_minmax(0,1fr)] px-2 py-0.5 min-h-[22px] ${
                    isAdd
                      ? "bg-[var(--ok-soft)] text-[var(--text-primary)]"
                      : row.right
                        ? "text-[var(--text-secondary)]"
                        : "bg-[var(--bg-subtle)]/40"
                  }`}
                >
                  <span className="text-[var(--text-muted)] select-none tabular-nums text-right pr-2">
                    {row.right?.newLine ?? ""}
                  </span>
                  <span className="whitespace-pre-wrap break-words">{row.right?.text ?? ""}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
