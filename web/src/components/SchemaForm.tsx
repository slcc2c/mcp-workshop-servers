import { useState, type ReactNode } from "react";
import { Play, Code2, SlidersHorizontal } from "lucide-react";
import type { ToolItem } from "../types";
import { resolveSchemaType } from "../lib/format";

export function SchemaForm({
  tool,
  argsObj,
  rawJson,
  onChangeArgs,
  onChangeRawJson,
  onRun,
  running,
  extraActions,
}: {
  tool: ToolItem;
  argsObj: Record<string, unknown>;
  rawJson: string;
  onChangeArgs: (next: Record<string, unknown>) => void;
  onChangeRawJson: (text: string) => void;
  onRun: () => void;
  running: boolean;
  extraActions?: ReactNode;
}) {
  const [mode, setMode] = useState<"form" | "json">("form");
  const props = tool.parameters?.properties || {};
  const propEntries = Object.entries(props);
  const requiredSet = new Set(tool.parameters?.required || []);

  function updateField(key: string, val: unknown) {
    const next = { ...argsObj };
    if (val === undefined || val === "") {
      delete next[key];
    } else {
      next[key] = val;
    }
    onChangeArgs(next);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !running) {
      e.preventDefault();
      onRun();
    }
  }

  return (
    <div className="space-y-3" onKeyDown={handleKeyDown}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
          <button
            type="button"
            onClick={() => setMode("form")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${
              mode === "form"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            Form
          </button>
          <button
            type="button"
            onClick={() => setMode("json")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${
              mode === "json"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Code2 className="w-3.5 h-3.5" />
            JSON
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {extraActions}
          <button
            type="button"
            disabled={running}
            onClick={onRun}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12.5px] font-semibold cursor-pointer transition-all whitespace-nowrap shrink-0"
          >
            <Play className="w-3.5 h-3.5" />
            {running ? "Running..." : "Run Tool"}
            <kbd className="ml-1 hidden sm:inline px-1.5 py-0.2 rounded bg-white/15 text-[10.5px] font-mono">
              ⌘↵
            </kbd>
          </button>
        </div>
      </div>

      {mode === "form" && propEntries.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5">
          {propEntries.map(([key, prop]) => {
            const pType = resolveSchemaType(prop);
            const isReq = requiredSet.has(key);
            const val = argsObj[key];
            const enumVals = Array.isArray(prop?.enum) ? prop.enum : null;

            return (
              <div
                key={key}
                className={
                  pType === "object" || pType === "array" || key === "query" || key === "content" || key === "template"
                    ? "md:col-span-2 space-y-1"
                    : "space-y-1"
                }
              >
                <label className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="font-mono font-medium text-[var(--text-primary)]">
                    {key}
                    {isReq && <span className="text-[var(--err)] ml-0.5">*</span>}
                  </span>
                  <span className="text-[11px] font-mono text-[var(--text-muted)]">{pType}</span>
                </label>

                {enumVals ? (
                  <select
                    aria-label={key}
                    value={val === undefined ? "" : String(val)}
                    onChange={(e) => updateField(key, e.target.value || undefined)}
                    className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
                  >
                    {!isReq && <option value="">— default —</option>}
                    {enumVals.map((opt) => (
                      <option key={String(opt)} value={String(opt)}>
                        {String(opt)}
                      </option>
                    ))}
                  </select>
                ) : pType === "boolean" ? (
                  <label className="inline-flex items-center gap-2 py-1 text-[12.5px] text-[var(--text-primary)] cursor-pointer">
                    <input
                      aria-label={key}
                      type="checkbox"
                      checked={Boolean(val)}
                      onChange={(e) => updateField(key, e.target.checked)}
                      className="rounded accent-[var(--accent)]"
                    />
                    <span>{val ? "true" : "false"}</span>
                  </label>
                ) : pType === "integer" || pType === "number" ? (
                  <input
                    aria-label={key}
                    type="number"
                    value={val === undefined ? "" : String(val)}
                    placeholder={prop?.default !== undefined ? String(prop.default) : ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      if (!raw) updateField(key, undefined);
                      else updateField(key, pType === "integer" ? parseInt(raw, 10) : Number(raw));
                    }}
                    className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 font-mono text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
                  />
                ) : pType === "object" || pType === "array" ? (
                  <textarea
                    aria-label={key}
                    rows={3}
                    value={val === undefined ? "" : typeof val === "string" ? val : JSON.stringify(val, null, 2)}
                    placeholder={pType === "array" ? '["item"]' : "{}"}
                    onChange={(e) => {
                      const txt = e.target.value;
                      if (!txt.trim()) {
                        updateField(key, undefined);
                        return;
                      }
                      try {
                        updateField(key, JSON.parse(txt));
                      } catch {
                        updateField(key, txt);
                      }
                    }}
                    className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 font-mono text-[12px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
                  />
                ) : (
                  <input
                    aria-label={key}
                    type="text"
                    value={val === undefined ? "" : String(val)}
                    placeholder={prop?.default !== undefined ? String(prop.default) : prop?.description || ""}
                    onChange={(e) => updateField(key, e.target.value)}
                    className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
                  />
                )}

                {prop?.description && (
                  <p className="text-[11.5px] text-[var(--text-muted)] leading-snug">{prop.description}</p>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <textarea
          aria-label="Tool JSON arguments"
          rows={5}
          value={rawJson}
          onChange={(e) => onChangeRawJson(e.target.value)}
          className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12.5px] leading-relaxed text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
        />
      )}
    </div>
  );
}
