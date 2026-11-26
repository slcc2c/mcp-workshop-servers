import { useEffect, useMemo, useState } from "react";
import { Clock, Search, Wrench } from "lucide-react";
import { api } from "../lib/api";
import {
  extractSchemaDefaults,
  firstLineSummary,
  formatDescriptionParagraphs,
  formatDuration,
} from "../lib/format";
import type {
  CallToolResponse,
  PlaygroundHistoryEntry,
  ProfileInventoryItem,
  ServerInventoryItem,
  ToolItem,
} from "../types";
import { CopyButton } from "../components/CopyButton";
import { SchemaForm } from "../components/SchemaForm";
import { SmartOutput } from "../components/SmartOutput";
import { StatusBadge } from "../components/StatusDot";

const HISTORY_KEY = "mcp_wb_playground_history_v1";

function loadHistory(): PlaygroundHistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as PlaygroundHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function PlaygroundView({
  tools,
  servers,
  profiles,
  profileFilter,
  serverFilter,
  selectedToolKey,
  onChangeProfileFilter,
  onChangeServerFilter,
  onSelectToolKey,
  onAfterRun,
}: {
  tools: ToolItem[];
  servers: ServerInventoryItem[];
  profiles: ProfileInventoryItem[];
  profileFilter: string;
  serverFilter: string;
  selectedToolKey: string | null;
  onChangeProfileFilter: (v: string) => void;
  onChangeServerFilter: (v: string) => void;
  onSelectToolKey: (key: string) => void;
  onAfterRun: () => void;
}) {
  const [search, setSearch] = useState("");
  const [leftTab, setLeftTab] = useState<"tools" | "history">("tools");
  const [history, setHistory] = useState<PlaygroundHistoryEntry[]>(loadHistory);
  const [argsObj, setArgsObj] = useState<Record<string, unknown>>({});
  const [rawJson, setRawJson] = useState("{}");
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState<CallToolResponse | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const filteredTools = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tools.filter((t) => {
      if (serverFilter && t.server !== serverFilter) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.server.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
      );
    });
  }, [tools, serverFilter, search]);

  const activeTool = useMemo(() => {
    if (selectedToolKey) {
      const exact = tools.find((t) => `${t.server}.${t.name}` === selectedToolKey);
      if (exact) return exact;
    }
    return filteredTools[0] || tools[0] || null;
  }, [selectedToolKey, tools, filteredTools]);

  useEffect(() => {
    if (!activeTool) return;
    const defaults = extractSchemaDefaults(activeTool.parameters);
    setArgsObj(defaults);
    setRawJson(JSON.stringify(defaults, null, 2));
    setResponse(null);
    setParseError(null);
  }, [activeTool]);

  function handleChangeArgs(next: Record<string, unknown>) {
    setArgsObj(next);
    setRawJson(JSON.stringify(next, null, 2));
    setParseError(null);
  }

  function handleChangeRaw(text: string) {
    setRawJson(text);
    try {
      const parsed = JSON.parse(text.trim() || "{}");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        setArgsObj(parsed as Record<string, unknown>);
        setParseError(null);
      } else {
        setParseError("Arguments must be a JSON object.");
      }
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "Invalid JSON");
    }
  }

  async function runTool() {
    if (!activeTool) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(rawJson.trim() || "{}") as Record<string, unknown>;
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "Invalid JSON");
      return;
    }

    setRunning(true);
    setParseError(null);
    try {
      const res = await api.callTool(activeTool.server, activeTool.name, payload);
      setResponse(res);
      const entry: PlaygroundHistoryEntry = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
        timestamp: new Date().toISOString(),
        server: activeTool.server,
        tool: activeTool.name,
        arguments: payload,
        ok: Boolean(res.ok),
        durationMs: res.durationMs,
      };
      const nextHist = [entry, ...history].slice(0, 30);
      setHistory(nextHist);
      try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(nextHist));
      } catch {
        // ignore quota errors
      }
      onAfterRun();
    } catch (err) {
      setResponse({
        ok: false,
        policyRefusal: false,
        server: activeTool.server,
        tool: activeTool.name,
        durationMs: 0,
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setRunning(false);
    }
  }

  const descParagraphs = activeTool ? formatDescriptionParagraphs(activeTool.description) : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
      {/* Left Pane: Filterable Tool List & History */}
      <aside className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] overflow-hidden flex flex-col lg:max-h-[calc(100vh-7rem)] lg:sticky lg:top-[4.5rem]">
        <div className="p-3 border-b border-[var(--border-hairline)] space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
              <button
                type="button"
                onClick={() => setLeftTab("tools")}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer ${
                  leftTab === "tools"
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                <Wrench className="w-3.5 h-3.5" />
                Tools ({filteredTools.length})
              </button>
              <button
                type="button"
                onClick={() => setLeftTab("history")}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer ${
                  leftTab === "history"
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                History ({history.length})
              </button>
            </div>
          </div>

          {leftTab === "tools" && (
            <>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-2.5" />
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter tools..."
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] pl-8 pr-2.5 py-1.5 text-[12.5px] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <select
                  aria-label="Filter by profile"
                  value={profileFilter}
                  onChange={(e) => onChangeProfileFilter(e.target.value)}
                  className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1.5 text-[12px]"
                >
                  <option value="">All Profiles</option>
                  {profiles.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Filter by server"
                  value={serverFilter}
                  onChange={(e) => onChangeServerFilter(e.target.value)}
                  className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1.5 text-[12px]"
                >
                  <option value="">All Servers</option>
                  {servers.map((s) => (
                    <option key={s.slug} value={s.slug}>
                      {s.slug}
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}
        </div>

        <div className="overflow-y-auto divide-y divide-[var(--border-hairline)] max-h-[420px] lg:max-h-none">
          {leftTab === "tools" ? (
            filteredTools.length === 0 ? (
              <div className="p-4 text-[12.5px] text-[var(--text-muted)]">
                No tools match the active filter.
              </div>
            ) : (
              filteredTools.map((t) => {
                const key = `${t.server}.${t.name}`;
                const selected = activeTool && `${activeTool.server}.${activeTool.name}` === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onSelectToolKey(key)}
                    className={`w-full text-left px-3.5 py-2.5 transition-colors cursor-pointer ${
                      selected
                        ? "bg-[var(--accent-soft)] border-l-2 border-[var(--accent)]"
                        : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-medium text-[12.5px] truncate text-[var(--text-primary)]">
                        {t.name}
                      </span>
                      <span className="font-mono text-[10.5px] text-[var(--text-muted)] whitespace-nowrap shrink-0">
                        {t.server}
                      </span>
                    </div>
                    {t.description && (
                      <div className="text-[11.5px] text-[var(--text-secondary)] truncate mt-0.5">
                        {firstLineSummary(t.description, 90)}
                      </div>
                    )}
                  </button>
                );
              })
            )
          ) : history.length === 0 ? (
            <div className="p-4 text-[12.5px] text-[var(--text-muted)]">
              Run a tool to populate local history.
            </div>
          ) : (
            history.map((h) => (
              <button
                key={h.id}
                type="button"
                onClick={() => {
                  onSelectToolKey(`${h.server}.${h.tool}`);
                  setTimeout(() => {
                    handleChangeArgs(h.arguments);
                  }, 0);
                  setLeftTab("tools");
                }}
                className="w-full text-left px-3.5 py-2.5 hover:bg-[var(--bg-hover)] cursor-pointer space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[12px] font-medium truncate">
                    {h.server} / {h.tool}
                  </span>
                  <StatusBadge label={h.ok ? "ok" : "err"} tone={h.ok ? "ok" : "err"} />
                </div>
                <div className="text-[11px] font-mono text-[var(--text-muted)] tabular-nums">
                  {formatDuration(h.durationMs)} · {new Date(h.timestamp).toLocaleTimeString()}
                </div>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Right Pane: Tool Workspace */}
      <section className="space-y-4 min-w-0">
        {!activeTool ? (
          <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-8 text-center text-[var(--text-muted)]">
            Select a tool from the left list to inspect schema and invoke it live.
          </div>
        ) : (
          <>
            <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 space-y-4">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2 py-0.5 rounded-md bg-[var(--bg-elevated)] border border-[var(--border-hairline)] font-mono text-[11.5px] text-[var(--text-secondary)] whitespace-nowrap shrink-0">
                      {activeTool.server}
                    </span>
                    <h2 className="font-mono text-[15px] font-semibold tracking-tight m-0 break-all">
                      {activeTool.name}
                    </h2>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {response && (
                    <StatusBadge
                      label={
                        response.ok
                          ? `OK · ${formatDuration(response.durationMs)}`
                          : response.policyRefusal
                            ? "POLICY REFUSAL"
                            : "ERROR"
                      }
                      tone={response.ok ? "ok" : response.policyRefusal ? "warn" : "err"}
                    />
                  )}
                  <CopyButton
                    text={JSON.stringify(
                      { server: activeTool.server, tool: activeTool.name, arguments: argsObj },
                      null,
                      2,
                    )}
                    label="Copy call"
                    compact
                  />
                </div>
              </div>

              {descParagraphs.length > 0 && (
                <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] px-4 py-3 space-y-2">
                  {descParagraphs.map((para, i) => (
                    <p
                      key={i}
                      className="text-[13px] leading-relaxed text-[var(--text-secondary)] whitespace-pre-wrap break-words m-0"
                    >
                      {para}
                    </p>
                  ))}
                </div>
              )}

              {parseError && (
                <div className="rounded-lg border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
                  {parseError}
                </div>
              )}

              <SchemaForm
                tool={activeTool}
                argsObj={argsObj}
                rawJson={rawJson}
                onChangeArgs={handleChangeArgs}
                onChangeRawJson={handleChangeRaw}
                onRun={runTool}
                running={running}
              />
            </div>

            {response && (
              <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5">
                <SmartOutput response={response} />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
