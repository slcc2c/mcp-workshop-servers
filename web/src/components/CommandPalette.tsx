import { useEffect, useMemo, useState } from "react";
import { Search, Wrench, Server, FileCode2, Compass, X } from "lucide-react";
import type { NavTab, RegistryPromptItem, ServerInventoryItem, ToolItem } from "../types";

export function CommandPalette({
  open,
  onClose,
  servers,
  tools,
  prompts,
  onSelectTab,
  onSelectTool,
  onSelectPrompt,
}: {
  open: boolean;
  onClose: () => void;
  servers: ServerInventoryItem[];
  tools: ToolItem[];
  prompts: RegistryPromptItem[];
  onSelectTab: (tab: NavTab) => void;
  onSelectTool: (server: string, toolName: string) => void;
  onSelectPrompt: (name: string) => void;
}) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const views: Array<{ id: NavTab; label: string }> = [
      { id: "overview", label: "Go to Overview" },
      { id: "playground", label: "Go to Tool Playground" },
      { id: "traces", label: "Go to Traces & Evals" },
      { id: "registry", label: "Go to MLflow Registry" },
      { id: "upstreams", label: "Go to Upstreams Admin" },
      { id: "clients", label: "Go to Agents & Clients" },
    ];
    return {
      views: views.filter((v) => !q || v.label.toLowerCase().includes(q)),
      servers: servers
        .filter((s) => !q || s.slug.toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q))
        .slice(0, 6),
      tools: tools
        .filter(
          (t) =>
            !q ||
            t.name.toLowerCase().includes(q) ||
            t.server.toLowerCase().includes(q) ||
            t.description.toLowerCase().includes(q),
        )
        .slice(0, 10),
      prompts: prompts.filter((p) => !q || p.name.toLowerCase().includes(q)).slice(0, 6),
    };
  }, [query, servers, tools, prompts]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] bg-black/60 backdrop-blur-xs p-4"
      onClick={onClose}
    >
      <div
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
              if (e.key === "Escape") onClose();
            }}
            placeholder="Jump to tool, server, prompt, or view..."
            className="w-full bg-transparent text-[13.5px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="max-h-[420px] overflow-y-auto p-2 space-y-3">
          {results.tools.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Tools
              </div>
              {results.tools.map((t) => (
                <button
                  key={`${t.server}.${t.name}`}
                  type="button"
                  onClick={() => {
                    onSelectTool(t.server, t.name);
                    onClose();
                  }}
                  className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-left hover:bg-[var(--bg-hover)] cursor-pointer"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <Wrench className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />
                    <span className="font-mono text-[12.5px] font-medium truncate">{t.name}</span>
                  </span>
                  <span className="font-mono text-[11px] text-[var(--text-muted)] shrink-0">
                    {t.server}
                  </span>
                </button>
              ))}
            </div>
          )}

          {results.servers.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Servers
              </div>
              {results.servers.map((s) => (
                <button
                  key={s.slug}
                  type="button"
                  onClick={() => {
                    onSelectTool(s.slug, "");
                    onClose();
                  }}
                  className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-left hover:bg-[var(--bg-hover)] cursor-pointer"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <Server className="w-3.5 h-3.5 text-[var(--ok)] shrink-0" />
                    <span className="font-mono text-[12.5px] truncate">{s.slug}</span>
                  </span>
                  <span className="text-[11px] text-[var(--text-muted)]">{s.route}</span>
                </button>
              ))}
            </div>
          )}

          {results.prompts.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Prompts
              </div>
              {results.prompts.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    onSelectPrompt(p.name);
                    onClose();
                  }}
                  className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left hover:bg-[var(--bg-hover)] cursor-pointer"
                >
                  <FileCode2 className="w-3.5 h-3.5 text-[var(--warn)] shrink-0" />
                  <span className="font-mono text-[12.5px] truncate">{p.name}</span>
                </button>
              ))}
            </div>
          )}

          {results.views.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Views
              </div>
              {results.views.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => {
                    onSelectTab(v.id);
                    onClose();
                  }}
                  className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left hover:bg-[var(--bg-hover)] cursor-pointer"
                >
                  <Compass className="w-3.5 h-3.5 text-[var(--text-secondary)] shrink-0" />
                  <span className="text-[12.5px]">{v.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
