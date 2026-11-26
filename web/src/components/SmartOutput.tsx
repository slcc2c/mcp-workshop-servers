import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Activity, Download, FileText, Code2, Layers, WrapText } from "lucide-react";
import type { CallToolResponse, MCPContentBlock } from "../types";
import { classifyTextPayload, normalizeMultilineText } from "../lib/format";
import { CopyButton } from "./CopyButton";

function JsonValueRenderer({ data, depth = 0 }: { data: unknown; depth?: number }) {
  if (data === null || data === undefined) {
    return <span className="text-[var(--text-muted)] font-mono text-[12px]">null</span>;
  }
  if (typeof data === "boolean") {
    return (
      <span
        className={`font-mono text-[12px] font-medium ${
          data ? "text-[var(--ok)]" : "text-[var(--warn)]"
        }`}
      >
        {String(data)}
      </span>
    );
  }
  if (typeof data === "number") {
    return <span className="font-mono text-[12px] tabular-nums text-[var(--accent)]">{data}</span>;
  }
  if (typeof data === "string") {
    const clean = normalizeMultilineText(data);
    return (
      <div className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-[var(--text-primary)]">
        {clean}
      </div>
    );
  }
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span className="text-[var(--text-muted)] font-mono text-[12px]">[]</span>;
    }
    const allFlatObjects =
      depth < 2 &&
      data.every((item) => item !== null && typeof item === "object" && !Array.isArray(item));
    if (allFlatObjects && data.length <= 50) {
      const cols = Array.from(
        new Set(data.flatMap((row) => Object.keys(row as Record<string, unknown>))),
      ).slice(0, 8);
      if (cols.length > 0) {
        return (
          <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
            <table className="w-full text-left border-collapse text-[12px]">
              <thead>
                <tr className="bg-[var(--bg-subtle)] border-b border-[var(--border-hairline)]">
                  {cols.map((col) => (
                    <th
                      key={col}
                      className="px-3 py-2 font-mono font-medium text-[var(--text-secondary)] whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => (
                  <tr
                    key={idx}
                    className="border-b last:border-b-0 border-[var(--border-hairline)] hover:bg-[var(--bg-hover)]"
                  >
                    {cols.map((col) => {
                      const cell = (row as Record<string, unknown>)[col];
                      const rendered =
                        cell === null || cell === undefined
                          ? "—"
                          : typeof cell === "object"
                            ? JSON.stringify(cell)
                            : normalizeMultilineText(String(cell));
                      return (
                        <td
                          key={col}
                          className="px-3 py-2 align-top text-[var(--text-primary)] whitespace-pre-wrap break-words max-w-[320px]"
                        >
                          {rendered}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
    }
    return (
      <div className="space-y-1.5">
        {data.map((item, idx) => (
          <div
            key={idx}
            className="rounded-md border border-[var(--border-hairline)] bg-[var(--bg-subtle)] px-3 py-2"
          >
            <JsonValueRenderer data={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  const obj = data as Record<string, unknown>;
  const entries = Object.entries(obj);
  if (entries.length === 0) {
    return <span className="text-[var(--text-muted)] font-mono text-[12px]">{"{}"}</span>;
  }

  return (
    <div className="divide-y divide-[var(--border-hairline)] rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)]">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 md:grid-cols-[170px_minmax(0,1fr)] gap-2 px-3 py-2.5">
          <div className="font-mono text-[12px] font-medium text-[var(--text-secondary)] break-words">
            {k}
          </div>
          <div className="min-w-0">
            <JsonValueRenderer data={v} depth={depth + 1} />
          </div>
        </div>
      ))}
    </div>
  );
}

function ContentBlockView({ block }: { block: MCPContentBlock }) {
  if (block.type === "image" && block.data) {
    const mime = block.mimeType || "image/png";
    const src = `data:${mime};base64,${block.data}`;
    return (
      <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 space-y-2">
        <div className="flex items-center justify-between gap-2 text-[11.5px] text-[var(--text-secondary)]">
          <span className="font-mono">Image ({mime})</span>
          <a
            href={src}
            download={`mcp-image.${mime.split("/")[1] || "png"}`}
            className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
          >
            <Download className="w-3.5 h-3.5" />
            Save
          </a>
        </div>
        <img
          src={src}
          alt="MCP tool image output"
          className="max-w-full max-h-[460px] rounded border border-[var(--border-hairline)] bg-white object-contain"
        />
      </div>
    );
  }

  const text = block.text || "";
  if (!text) return null;
  const seg = classifyTextPayload(text);
  if (seg.kind === "json" && seg.parsedJson !== undefined) {
    return <JsonValueRenderer data={seg.parsedJson} />;
  }
  if (seg.kind === "markdown") {
    return (
      <div className="wb-prose rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4">
        <Markdown remarkPlugins={[remarkGfm]}>{seg.text}</Markdown>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 text-[13.5px] leading-relaxed text-[var(--text-primary)] whitespace-pre-wrap break-words">
      {seg.text}
    </div>
  );
}

export function SmartValueView({
  value,
  maxHeightClass = "max-h-64",
}: {
  value: unknown;
  maxHeightClass?: string;
}) {
  const [rawMode, setRawMode] = useState(false);

  if (value === null || value === undefined) {
    return <div className="font-mono text-[12px] text-[var(--text-muted)]">—</div>;
  }

  let parsed: unknown = value;
  if (typeof value === "string") {
    const seg = classifyTextPayload(value);
    if (seg.kind === "json" && seg.parsedJson !== undefined) {
      parsed = seg.parsedJson;
    } else if (seg.kind === "markdown") {
      return (
        <div className="space-y-1.5">
          <div className="wb-prose rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3">
            <Markdown remarkPlugins={[remarkGfm]}>{seg.text}</Markdown>
          </div>
        </div>
      );
    } else {
      return (
        <pre
          className={`rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words ${maxHeightClass} overflow-auto m-0`}
        >
          {seg.text}
        </pre>
      );
    }
  }

  const rawJson = typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => setRawMode((v) => !v)}
          className="px-2 py-0.5 rounded border border-[var(--border-hairline)] text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
        >
          {rawMode ? "Formatted" : "Raw JSON"}
        </button>
        <CopyButton text={rawJson} label="Copy" compact />
      </div>
      {rawMode ? (
        <pre
          className={`rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words ${maxHeightClass} overflow-auto m-0`}
        >
          {rawJson}
        </pre>
      ) : (
        <div className={`${maxHeightClass} overflow-auto`}>
          <JsonValueRenderer data={parsed} />
        </div>
      )}
    </div>
  );
}

export function SmartOutput({
  response,
  onInspectTrace,
}: {
  response: CallToolResponse;
  onInspectTrace?: (traceId: string) => void;
}) {
  const [view, setView] = useState<"formatted" | "raw" | "meta">("formatted");
  const [wrapRaw, setWrapRaw] = useState(true);

  const errText =
    typeof response.error === "string"
      ? response.error
      : response.error?.message || "";
  const rawJson = JSON.stringify(response, null, 2);

  const blocks =
    response.contentBlocks && response.contentBlocks.length > 0
      ? response.contentBlocks
      : response.result !== undefined && response.result !== null
        ? [
            {
              type: "text" as const,
              text:
                typeof response.result === "string"
                  ? response.result
                  : JSON.stringify(response.result, null, 2),
            },
          ]
        : [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
          <button
            type="button"
            onClick={() => setView("formatted")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${
              view === "formatted"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            Formatted
          </button>
          <button
            type="button"
            onClick={() => setView("raw")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${
              view === "raw"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Code2 className="w-3.5 h-3.5" />
            Raw JSON
          </button>
          <button
            type="button"
            onClick={() => setView("meta")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${
              view === "meta"
                ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Structured
          </button>
        </div>

        <div className="flex items-center gap-2">
          {view === "raw" && (
            <button
              type="button"
              onClick={() => setWrapRaw((v) => !v)}
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-[11.5px] cursor-pointer ${
                wrapRaw
                  ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent-soft)]"
                  : "border-[var(--border-hairline)] text-[var(--text-secondary)]"
              }`}
            >
              <WrapText className="w-3.5 h-3.5" />
              Wrap
            </button>
          )}
          {response.traceId && onInspectTrace && (
            <button
              type="button"
              onClick={() => onInspectTrace(response.traceId!)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[color-mix(in_srgb,var(--accent)_40%,transparent)] bg-[var(--accent-soft)] text-[var(--accent)] text-[11.5px] font-medium hover:brightness-110 cursor-pointer"
            >
              <Activity className="w-3.5 h-3.5" />
              Inspect Trace
            </button>
          )}
          <CopyButton text={rawJson} label="Copy JSON" compact />
        </div>
      </div>

      {!response.ok && (
        <div className="rounded-lg border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] p-3.5 text-[13px] text-[var(--text-primary)] whitespace-pre-wrap break-words">
          <div className="font-semibold text-[var(--err)] mb-1">
            {response.policyRefusal ? "Policy Refusal" : "Tool Execution Error"}
          </div>
          {normalizeMultilineText(errText || "Unknown error")}
        </div>
      )}

      {view === "formatted" && response.ok && (
        <div className="space-y-3" data-testid="smart-output-formatted">
          {blocks.length > 0 ? (
            blocks.map((block, i) => <ContentBlockView key={i} block={block} />)
          ) : response.structuredContent !== undefined && response.structuredContent !== null ? (
            <JsonValueRenderer data={response.structuredContent} />
          ) : (
            <div className="text-[12.5px] text-[var(--text-muted)]">Tool completed with empty output.</div>
          )}
        </div>
      )}

      {view === "raw" && (
        <pre
          data-testid="smart-output-raw"
          className={`rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3.5 font-mono text-[12px] leading-relaxed text-[var(--text-primary)] max-h-[520px] overflow-auto ${
            wrapRaw ? "whitespace-pre-wrap break-words" : "whitespace-pre"
          }`}
        >
          {rawJson}
        </pre>
      )}

      {view === "meta" && (
        <JsonValueRenderer
          data={
            response.structuredContent ?? {
              server: response.server,
              tool: response.tool,
              durationMs: response.durationMs,
              truncated: Boolean(response.truncated),
              contentBlockCount: blocks.length,
            }
          }
        />
      )}
    </div>
  );
}
