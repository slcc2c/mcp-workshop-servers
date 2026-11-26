import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Bookmark,
  Clock,
  Pin,
  PinOff,
  Play,
  Search,
  Trash2,
  Wrench,
} from "lucide-react";
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
  PlaygroundPresetItem,
  PlaygroundReplayRequest,
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

function summarizeResponse(res: CallToolResponse): string {
  if (!res.ok) {
    const msg =
      typeof res.error === "string"
        ? res.error
        : res.error?.message || "Execution failed";
    return firstLineSummary(msg, 110);
  }
  const blockText = res.contentBlocks?.find((b) => b.text)?.text;
  if (blockText) return firstLineSummary(blockText, 110);
  if (res.contentBlocks?.some((b) => b.type === "image")) return "[Image output]";
  if (typeof res.result === "string") return firstLineSummary(res.result, 110);
  if (res.result !== undefined && res.result !== null) {
    return firstLineSummary(JSON.stringify(res.result), 110);
  }
  return "Completed";
}

export function PlaygroundView({
  tools,
  servers,
  profiles,
  presets,
  profileFilter,
  serverFilter,
  selectedToolKey,
  replayRequest,
  onChangeProfileFilter,
  onChangeServerFilter,
  onSelectToolKey,
  onPresetsChanged,
  onInspectTrace,
  onAfterRun,
}: {
  tools: ToolItem[];
  servers: ServerInventoryItem[];
  profiles: ProfileInventoryItem[];
  presets: PlaygroundPresetItem[];
  profileFilter: string;
  serverFilter: string;
  selectedToolKey: string | null;
  replayRequest: PlaygroundReplayRequest | null;
  onChangeProfileFilter: (v: string) => void;
  onChangeServerFilter: (v: string) => void;
  onSelectToolKey: (key: string) => void;
  onPresetsChanged: () => Promise<void>;
  onInspectTrace: (traceId: string) => void;
  onAfterRun: () => void;
}) {
  const [search, setSearch] = useState("");
  const [presetSearch, setPresetSearch] = useState("");
  const [historySearch, setHistorySearch] = useState("");
  const [leftTab, setLeftTab] = useState<"tools" | "presets" | "history">("tools");
  const [history, setHistory] = useState<PlaygroundHistoryEntry[]>(loadHistory);
  const [argsObj, setArgsObj] = useState<Record<string, unknown>>({});
  const [rawJson, setRawJson] = useState("{}");
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState<CallToolResponse | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const [saveOpen, setSaveOpen] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [presetDesc, setPresetDesc] = useState("");
  const [presetPinned, setPresetPinned] = useState(false);
  const [presetBusy, setPresetBusy] = useState(false);
  const [presetNotice, setPresetNotice] = useState<string | null>(null);

  const pendingArgsRef = useRef<{
    key: string;
    args: Record<string, unknown>;
    autoRun?: boolean;
  } | null>(null);
  const lastReplayNonceRef = useRef<number>(0);

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

  const filteredPresets = useMemo(() => {
    const q = presetSearch.trim().toLowerCase();
    return presets.filter((p) => {
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        p.server.toLowerCase().includes(q) ||
        p.tool.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q)
      );
    });
  }, [presets, presetSearch]);

  const filteredHistory = useMemo(() => {
    const q = historySearch.trim().toLowerCase();
    return history.filter((h) => {
      if (!q) return true;
      return (
        h.server.toLowerCase().includes(q) ||
        h.tool.toLowerCase().includes(q) ||
        (h.responsePreview || "").toLowerCase().includes(q) ||
        JSON.stringify(h.arguments).toLowerCase().includes(q)
      );
    });
  }, [history, historySearch]);

  const activeTool = useMemo(() => {
    if (selectedToolKey) {
      const exact = tools.find((t) => `${t.server}.${t.name}` === selectedToolKey);
      if (exact) return exact;
    }
    return filteredTools[0] || tools[0] || null;
  }, [selectedToolKey, tools, filteredTools]);

  const runWithPayload = useCallback(
    async (toolItem: ToolItem, payload: Record<string, unknown>) => {
      setRunning(true);
      setParseError(null);
      try {
        const res = await api.callTool(toolItem.server, toolItem.name, payload);
        setResponse(res);
        const entry: PlaygroundHistoryEntry = {
          id: `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
          timestamp: new Date().toISOString(),
          server: toolItem.server,
          tool: toolItem.name,
          arguments: payload,
          ok: Boolean(res.ok),
          policyRefusal: Boolean(res.policyRefusal),
          durationMs: res.durationMs,
          responsePreview: summarizeResponse(res),
          traceId: res.traceId ?? null,
        };
        setHistory((prev) => {
          const next = [entry, ...prev].slice(0, 40);
          try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
          } catch {
            // ignore quota errors
          }
          return next;
        });
        onAfterRun();
      } catch (err) {
        setResponse({
          ok: false,
          policyRefusal: false,
          server: toolItem.server,
          tool: toolItem.name,
          durationMs: 0,
          error: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setRunning(false);
      }
    },
    [onAfterRun],
  );

  // Hydrate replay requests race-free
  useEffect(() => {
    if (!replayRequest || replayRequest.nonce === lastReplayNonceRef.current) return;
    lastReplayNonceRef.current = replayRequest.nonce;
    const targetKey = `${replayRequest.server}.${replayRequest.tool}`;
    pendingArgsRef.current = {
      key: targetKey,
      args: replayRequest.arguments || {},
      autoRun: replayRequest.autoRun,
    };
    if (activeTool && `${activeTool.server}.${activeTool.name}` === targetKey) {
      const next = pendingArgsRef.current.args;
      const shouldRun = pendingArgsRef.current.autoRun;
      pendingArgsRef.current = null;
      setArgsObj(next);
      setRawJson(JSON.stringify(next, null, 2));
      setResponse(null);
      setParseError(null);
      if (shouldRun) {
        runWithPayload(activeTool, next);
      }
    } else {
      onSelectToolKey(targetKey);
    }
  }, [replayRequest, activeTool, onSelectToolKey, runWithPayload]);

  // Synchronize arguments when activeTool changes (respecting pendingArgsRef)
  useEffect(() => {
    if (!activeTool) return;
    const activeKey = `${activeTool.server}.${activeTool.name}`;
    const pending = pendingArgsRef.current;
    if (pending && pending.key === activeKey) {
      pendingArgsRef.current = null;
      setArgsObj(pending.args);
      setRawJson(JSON.stringify(pending.args, null, 2));
      setResponse(null);
      setParseError(null);
      if (pending.autoRun) {
        runWithPayload(activeTool, pending.args);
      }
      return;
    }
    const defaults = extractSchemaDefaults(activeTool.parameters);
    setArgsObj(defaults);
    setRawJson(JSON.stringify(defaults, null, 2));
    setResponse(null);
    setParseError(null);
  }, [activeTool, runWithPayload]);

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
    if (!activeTool || running) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(rawJson.trim() || "{}") as Record<string, unknown>;
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "Invalid JSON");
      return;
    }
    await runWithPayload(activeTool, payload);
  }

  function hydrateToolWithArgs(
    server: string,
    toolName: string,
    args: Record<string, unknown>,
    autoRun = false,
  ) {
    const key = `${server}.${toolName}`;
    pendingArgsRef.current = { key, args: args || {}, autoRun };
    if (activeTool && `${activeTool.server}.${activeTool.name}` === key) {
      pendingArgsRef.current = null;
      setArgsObj(args || {});
      setRawJson(JSON.stringify(args || {}, null, 2));
      setResponse(null);
      setParseError(null);
      if (autoRun) {
        runWithPayload(activeTool, args || {});
      }
      return;
    }
    onSelectToolKey(key);
  }

  async function handleSavePreset(e: React.FormEvent) {
    e.preventDefault();
    if (!activeTool || !presetName.trim()) return;
    setPresetBusy(true);
    setPresetNotice(null);
    try {
      await api.createPreset({
        name: presetName.trim(),
        server: activeTool.server,
        tool: activeTool.name,
        arguments: argsObj,
        description: presetDesc.trim(),
        pinned: presetPinned,
      });
      setSaveOpen(false);
      setPresetName("");
      setPresetDesc("");
      setPresetPinned(false);
      setPresetNotice(`Saved preset '${presetName.trim()}'`);
      await onPresetsChanged();
    } catch (err) {
      setPresetNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setPresetBusy(false);
    }
  }

  async function quickSavePresetFromHistory(entry: PlaygroundHistoryEntry) {
    setPresetBusy(true);
    setPresetNotice(null);
    try {
      await api.createPreset({
        name: `${entry.server}.${entry.tool}`,
        server: entry.server,
        tool: entry.tool,
        arguments: entry.arguments || {},
        description: "Saved from Playground history",
        pinned: false,
      });
      setPresetNotice(`Saved preset for ${entry.server}.${entry.tool}`);
      await onPresetsChanged();
    } catch (err) {
      setPresetNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setPresetBusy(false);
    }
  }

  const descParagraphs = activeTool ? formatDescriptionParagraphs(activeTool.description) : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
      {/* Left Pane: Tools | Presets | History */}
      <aside className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] overflow-hidden flex flex-col lg:max-h-[calc(100vh-7rem)] lg:sticky lg:top-[4.5rem]">
        <div className="p-3 border-b border-[var(--border-hairline)] space-y-2.5">
          <div className="inline-flex w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
            <button
              type="button"
              onClick={() => setLeftTab("tools")}
              className={`flex-1 inline-flex items-center justify-center gap-1 px-2 py-1 rounded-md text-[11.5px] font-medium cursor-pointer ${
                leftTab === "tools"
                  ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]"
              }`}
            >
              <Wrench className="w-3 h-3" />
              Tools ({filteredTools.length})
            </button>
            <button
              type="button"
              onClick={() => setLeftTab("presets")}
              className={`flex-1 inline-flex items-center justify-center gap-1 px-2 py-1 rounded-md text-[11.5px] font-medium cursor-pointer ${
                leftTab === "presets"
                  ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]"
              }`}
            >
              <Bookmark className="w-3 h-3" />
              Presets ({presets.length})
            </button>
            <button
              type="button"
              onClick={() => setLeftTab("history")}
              className={`flex-1 inline-flex items-center justify-center gap-1 px-2 py-1 rounded-md text-[11.5px] font-medium cursor-pointer ${
                leftTab === "history"
                  ? "bg-[var(--bg-surface)] text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)]"
              }`}
            >
              <Clock className="w-3 h-3" />
              History ({history.length})
            </button>
          </div>

          {leftTab === "tools" && (
            <>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-2.5" />
                <input
                  data-shortcut-search="true"
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter tools... (/)"
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

          {leftTab === "presets" && (
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-2.5" />
              <input
                data-shortcut-search="true"
                type="search"
                value={presetSearch}
                onChange={(e) => setPresetSearch(e.target.value)}
                placeholder="Filter saved presets..."
                className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] pl-8 pr-2.5 py-1.5 text-[12.5px] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
          )}

          {leftTab === "history" && (
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-2.5" />
                <input
                  data-shortcut-search="true"
                  type="search"
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  placeholder="Filter history..."
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] pl-8 pr-2.5 py-1.5 text-[12.5px] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              {history.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    setHistory([]);
                    try {
                      localStorage.removeItem(HISTORY_KEY);
                    } catch {
                      // ignore
                    }
                  }}
                  title="Clear local history"
                  className="px-2 py-1.5 rounded-lg border border-[var(--border-hairline)] text-[11.5px] text-[var(--text-secondary)] hover:text-[var(--err)] cursor-pointer"
                >
                  Clear
                </button>
              )}
            </div>
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
          ) : leftTab === "presets" ? (
            filteredPresets.length === 0 ? (
              <div className="p-4 text-[12.5px] text-[var(--text-muted)]">
                No saved presets yet. Configure a tool and click Save Preset.
              </div>
            ) : (
              filteredPresets.map((p) => (
                <div key={p.id} className="px-3.5 py-2.5 space-y-1.5 hover:bg-[var(--bg-hover)]">
                  <div className="flex items-start justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => hydrateToolWithArgs(p.server, p.tool, p.arguments, false)}
                      className="text-left min-w-0 flex-1 cursor-pointer"
                    >
                      <div className="flex items-center gap-1.5">
                        {p.pinned && <Pin className="w-3 h-3 text-[var(--accent)] shrink-0" />}
                        <span className="text-[12.5px] font-medium truncate">{p.name}</span>
                      </div>
                      <div className="font-mono text-[11px] text-[var(--text-muted)] truncate">
                        {p.server}.{p.tool}
                      </div>
                      {p.description && (
                        <div className="text-[11px] text-[var(--text-secondary)] truncate mt-0.5">
                          {p.description}
                        </div>
                      )}
                    </button>

                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        title="Run preset"
                        onClick={() => hydrateToolWithArgs(p.server, p.tool, p.arguments, true)}
                        className="p-1 rounded border border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--accent)] hover:border-[var(--accent)] cursor-pointer"
                      >
                        <Play className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        title={p.pinned ? "Unpin preset" : "Pin preset"}
                        onClick={async () => {
                          await api.updatePreset(p.id, { pinned: !p.pinned });
                          await onPresetsChanged();
                        }}
                        className="p-1 rounded border border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
                      >
                        {p.pinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
                      </button>
                      <button
                        type="button"
                        title="Delete preset"
                        onClick={async () => {
                          await api.deletePreset(p.id);
                          await onPresetsChanged();
                        }}
                        className="p-1 rounded border border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--err)] cursor-pointer"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )
          ) : filteredHistory.length === 0 ? (
            <div className="p-4 text-[12.5px] text-[var(--text-muted)]">
              Run a tool to populate local history.
            </div>
          ) : (
            filteredHistory.map((h) => (
              <div key={h.id} className="px-3.5 py-2.5 hover:bg-[var(--bg-hover)] space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => hydrateToolWithArgs(h.server, h.tool, h.arguments, false)}
                    className="font-mono text-[12px] font-medium truncate text-left flex-1 cursor-pointer"
                  >
                    {h.server} / {h.tool}
                  </button>
                  <StatusBadge
                    label={h.policyRefusal ? "refusal" : h.ok ? "ok" : "err"}
                    tone={h.policyRefusal ? "warn" : h.ok ? "ok" : "err"}
                  />
                </div>
                {h.responsePreview && (
                  <div className="text-[11.5px] text-[var(--text-secondary)] truncate">
                    {h.responsePreview}
                  </div>
                )}
                <div className="flex items-center justify-between gap-2 text-[11px] font-mono text-[var(--text-muted)]">
                  <span className="tabular-nums">
                    {formatDuration(h.durationMs)} · {new Date(h.timestamp).toLocaleTimeString()}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {h.traceId && (
                      <button
                        type="button"
                        onClick={() => onInspectTrace(h.traceId!)}
                        title="Inspect trace"
                        className="inline-flex items-center gap-0.5 text-[var(--accent)] hover:underline cursor-pointer"
                      >
                        <Activity className="w-3 h-3" />
                        Trace
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={presetBusy}
                      onClick={() => quickSavePresetFromHistory(h)}
                      title="Save run as gateway preset"
                      className="inline-flex items-center gap-0.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
                    >
                      <Bookmark className="w-3 h-3" />
                      Save
                    </button>
                  </div>
                </div>
              </div>
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

              {presetNotice && (
                <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] px-3 py-1.5 text-[12px] text-[var(--accent)]">
                  {presetNotice}
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
                extraActions={
                  <button
                    type="button"
                    onClick={() => {
                      setPresetName(`${activeTool.server}.${activeTool.name}`);
                      setSaveOpen((v) => !v);
                    }}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[12px] text-[var(--text-secondary)] cursor-pointer"
                  >
                    <Bookmark className="w-3.5 h-3.5" />
                    Save Preset
                  </button>
                }
              />

              {saveOpen && (
                <form
                  onSubmit={handleSavePreset}
                  className="rounded-lg border border-[var(--accent)] bg-[var(--bg-subtle)] p-3 space-y-2.5"
                >
                  <div className="text-[12px] font-semibold">
                    Save Gateway Preset ({activeTool.server}.{activeTool.name})
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input
                      type="text"
                      required
                      value={presetName}
                      onChange={(e) => setPresetName(e.target.value)}
                      placeholder="Preset name (e.g. Daily receipt check)"
                      className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
                    />
                    <input
                      type="text"
                      value={presetDesc}
                      onChange={(e) => setPresetDesc(e.target.value)}
                      placeholder="Optional description..."
                      className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <label className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={presetPinned}
                        onChange={(e) => setPresetPinned(e.target.checked)}
                        className="accent-[var(--accent)]"
                      />
                      Pin to top
                    </label>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSaveOpen(false)}
                        className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] text-[12px] cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={presetBusy}
                        className="px-3 py-1 rounded-md bg-[var(--accent)] text-white text-[12px] font-medium cursor-pointer"
                      >
                        {presetBusy ? "Saving..." : "Save Preset"}
                      </button>
                    </div>
                  </div>
                </form>
              )}
            </div>

            {response && (
              <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5">
                <SmartOutput response={response} onInspectTrace={onInspectTrace} />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
