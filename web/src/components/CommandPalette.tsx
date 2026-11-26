import { useEffect, useMemo, useRef, useState } from "react";
import { Bookmark, Search, Wrench, Server, FileCode2, Compass, X } from "lucide-react";
import type {
  NavTab,
  PlaygroundPresetItem,
  RegistryPromptItem,
  ServerInventoryItem,
  ToolItem,
} from "../types";

type PaletteEntry =
  | { kind: "preset"; key: string; preset: PlaygroundPresetItem }
  | { kind: "tool"; key: string; tool: ToolItem }
  | { kind: "server"; key: string; server: ServerInventoryItem }
  | { kind: "prompt"; key: string; prompt: RegistryPromptItem }
  | { kind: "view"; key: string; view: { id: NavTab; label: string } };

export function CommandPalette({
  open,
  onClose,
  presets = [],
  servers,
  tools,
  prompts,
  onSelectTab,
  onSelectPreset,
  onSelectTool,
  onSelectPrompt,
}: {
  open: boolean;
  onClose: () => void;
  presets?: PlaygroundPresetItem[];
  servers: ServerInventoryItem[];
  tools: ToolItem[];
  prompts: RegistryPromptItem[];
  onSelectTab: (tab: NavTab) => void;
  onSelectPreset?: (preset: PlaygroundPresetItem) => void;
  onSelectTool: (server: string, toolName: string) => void;
  onSelectPrompt: (name: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
    }
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const views: Array<{ id: NavTab; label: string }> = [
      { id: "overview", label: "Go to Overview" },
      { id: "playground", label: "Go to Playground & Agent" },
      { id: "traces", label: "Go to Traces" },
      { id: "evals", label: "Go to Evals & Datasets" },
      { id: "registry", label: "Go to Registry & Skills" },
      { id: "upstreams", label: "Go to Upstreams & Profiles" },
      { id: "clients", label: "Go to Clients" },
    ];
    const matchedPresets = presets
      .filter(
        (p) =>
          !q ||
          p.name.toLowerCase().includes(q) ||
          p.server.toLowerCase().includes(q) ||
          p.tool.toLowerCase().includes(q) ||
          (p.description || "").toLowerCase().includes(q),
      )
      .slice(0, 6);
    const matchedTools = tools
      .filter(
        (t) =>
          !q ||
          t.name.toLowerCase().includes(q) ||
          t.server.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q),
      )
      .slice(0, 10);
    const matchedServers = servers
      .filter(
        (s) =>
          !q ||
          s.slug.toLowerCase().includes(q) ||
          (s.description || "").toLowerCase().includes(q),
      )
      .slice(0, 6);
    const matchedPrompts = prompts
      .filter((p) => !q || p.name.toLowerCase().includes(q))
      .slice(0, 6);
    const matchedViews = views.filter((v) => !q || v.label.toLowerCase().includes(q));

    const flat: PaletteEntry[] = [
      ...matchedPresets.map((preset) => ({ kind: "preset" as const, key: `preset:${preset.id}`, preset })),
      ...matchedTools.map((tool) => ({
        kind: "tool" as const,
        key: `tool:${tool.server}.${tool.name}`,
        tool,
      })),
      ...matchedServers.map((server) => ({
        kind: "server" as const,
        key: `server:${server.slug}`,
        server,
      })),
      ...matchedPrompts.map((prompt) => ({
        kind: "prompt" as const,
        key: `prompt:${prompt.name}`,
        prompt,
      })),
      ...matchedViews.map((view) => ({ kind: "view" as const, key: `view:${view.id}`, view })),
    ];
    return {
      presets: matchedPresets,
      tools: matchedTools,
      servers: matchedServers,
      prompts: matchedPrompts,
      views: matchedViews,
      flat,
    };
  }, [query, presets, servers, tools, prompts]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    const activeEl = listRef.current.querySelector(`[data-palette-idx="${activeIndex}"]`);
    if (activeEl && typeof activeEl.scrollIntoView === "function") {
      activeEl.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, open]);

  if (!open) return null;

  function activateEntry(entry: PaletteEntry | undefined) {
    if (!entry) return;
    if (entry.kind === "preset") {
      onSelectPreset?.(entry.preset);
    } else if (entry.kind === "tool") {
      onSelectTool(entry.tool.server, entry.tool.name);
    } else if (entry.kind === "server") {
      onSelectTool(entry.server.slug, "");
    } else if (entry.kind === "prompt") {
      onSelectPrompt(entry.prompt.name);
    } else {
      onSelectTab(entry.view.id);
    }
    onClose();
  }

  let runningIndex = 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] bg-black/60 backdrop-blur-xs p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Quick Jump Palette"
        className="w-full max-w-xl rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 border-b border-[var(--border-hairline)]">
          <Search className="w-4 h-4 text-[var(--text-muted)] shrink-0" />
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                onClose();
                return;
              }
              if (e.key === "ArrowDown" && results.flat.length > 0) {
                e.preventDefault();
                setActiveIndex((i) => (i + 1) % results.flat.length);
                return;
              }
              if (e.key === "ArrowUp" && results.flat.length > 0) {
                e.preventDefault();
                setActiveIndex((i) => (i - 1 + results.flat.length) % results.flat.length);
                return;
              }
              if (e.key === "Enter" && results.flat.length > 0) {
                e.preventDefault();
                activateEntry(results.flat[activeIndex] ?? results.flat[0]);
              }
            }}
            placeholder="Jump to preset, tool, server, prompt, or view..."
            className="w-full bg-transparent text-[13.5px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close palette"
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div ref={listRef} className="max-h-[420px] overflow-y-auto p-2 space-y-3">
          {results.flat.length === 0 && (
            <div className="px-3 py-6 text-center text-[12.5px] text-[var(--text-muted)]">
              No matching presets, tools, servers, prompts, or views.
            </div>
          )}

          {results.presets.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Presets
              </div>
              {results.presets.map((p) => {
                const idx = runningIndex++;
                const active = idx === activeIndex;
                return (
                  <button
                    key={p.id}
                    type="button"
                    data-palette-idx={idx}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => activateEntry({ kind: "preset", key: `preset:${p.id}`, preset: p })}
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-left cursor-pointer ${
                      active ? "bg-[var(--accent-soft)] text-[var(--text-primary)]" : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <Bookmark className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />
                      <span className="text-[12.5px] font-medium truncate">{p.name}</span>
                    </span>
                    <span className="font-mono text-[11px] text-[var(--text-muted)] shrink-0">
                      {p.server}.{p.tool}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {results.tools.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Tools
              </div>
              {results.tools.map((t) => {
                const idx = runningIndex++;
                const active = idx === activeIndex;
                return (
                  <button
                    key={`${t.server}.${t.name}`}
                    type="button"
                    data-palette-idx={idx}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() =>
                      activateEntry({ kind: "tool", key: `tool:${t.server}.${t.name}`, tool: t })
                    }
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-left cursor-pointer ${
                      active ? "bg-[var(--accent-soft)] text-[var(--text-primary)]" : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <Wrench className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />
                      <span className="font-mono text-[12.5px] font-medium truncate">{t.name}</span>
                    </span>
                    <span className="font-mono text-[11px] text-[var(--text-muted)] shrink-0">
                      {t.server}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {results.servers.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Servers
              </div>
              {results.servers.map((s) => {
                const idx = runningIndex++;
                const active = idx === activeIndex;
                return (
                  <button
                    key={s.slug}
                    type="button"
                    data-palette-idx={idx}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() =>
                      activateEntry({ kind: "server", key: `server:${s.slug}`, server: s })
                    }
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-left cursor-pointer ${
                      active ? "bg-[var(--accent-soft)] text-[var(--text-primary)]" : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <Server className="w-3.5 h-3.5 text-[var(--ok)] shrink-0" />
                      <span className="font-mono text-[12.5px] truncate">{s.slug}</span>
                    </span>
                    <span className="text-[11px] text-[var(--text-muted)]">{s.route}</span>
                  </button>
                );
              })}
            </div>
          )}

          {results.prompts.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Prompts
              </div>
              {results.prompts.map((p) => {
                const idx = runningIndex++;
                const active = idx === activeIndex;
                return (
                  <button
                    key={p.name}
                    type="button"
                    data-palette-idx={idx}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() =>
                      activateEntry({ kind: "prompt", key: `prompt:${p.name}`, prompt: p })
                    }
                    className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left cursor-pointer ${
                      active ? "bg-[var(--accent-soft)] text-[var(--text-primary)]" : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <FileCode2 className="w-3.5 h-3.5 text-[var(--warn)] shrink-0" />
                    <span className="font-mono text-[12.5px] truncate">{p.name}</span>
                  </button>
                );
              })}
            </div>
          )}

          {results.views.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Views
              </div>
              {results.views.map((v) => {
                const idx = runningIndex++;
                const active = idx === activeIndex;
                return (
                  <button
                    key={v.id}
                    type="button"
                    data-palette-idx={idx}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => activateEntry({ kind: "view", key: `view:${v.id}`, view: v })}
                    className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left cursor-pointer ${
                      active ? "bg-[var(--accent-soft)] text-[var(--text-primary)]" : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <Compass className="w-3.5 h-3.5 text-[var(--text-secondary)] shrink-0" />
                    <span className="text-[12.5px]">{v.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="px-3.5 py-2 border-t border-[var(--border-hairline)] bg-[var(--bg-subtle)] flex items-center justify-between text-[11px] text-[var(--text-muted)]">
          <span>↑↓ Navigate · ↵ Open · Esc Close</span>
          <span className="font-mono tabular-nums">{results.flat.length} matches</span>
        </div>
      </div>
    </div>
  );
}
