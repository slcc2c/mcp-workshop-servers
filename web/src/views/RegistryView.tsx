import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Plus, Search, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import type { PromptDetailResponse, RegistryResponse } from "../types";
import { CopyButton } from "../components/CopyButton";
import { PromptRenderer } from "../components/PromptRenderer";
import { StatusBadge } from "../components/StatusDot";

export function RegistryView({
  registry,
  initialPromptName,
  onReload,
}: {
  registry: RegistryResponse | null;
  initialPromptName?: string | null;
  onReload: () => Promise<void>;
}) {
  const [subTab, setSubTab] = useState<"servers" | "prompts" | "models">("servers");
  const [search, setSearch] = useState("");
  const [selectedServerName, setSelectedServerName] = useState<string | null>(null);
  const [selectedPromptName, setSelectedPromptName] = useState<string | null>(initialPromptName || null);
  const [promptDetail, setPromptDetail] = useState<PromptDetailResponse | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const [showNewPrompt, setShowNewPrompt] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  const [newCommit, setNewCommit] = useState("");
  const [newAlias, setNewAlias] = useState("production");
  const [savingPrompt, setSavingPrompt] = useState(false);

  const mutEnabled = Boolean(registry?.mutationsEnabled);
  const mcpServers = useMemo(() => registry?.mcpServers || [], [registry]);
  const prompts = useMemo(() => registry?.prompts || [], [registry]);

  useEffect(() => {
    if (initialPromptName) {
      setSubTab("prompts");
      setSelectedPromptName(initialPromptName);
    }
  }, [initialPromptName]);

  const filteredServers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return mcpServers.filter((s) => !q || s.name.toLowerCase().includes(q));
  }, [mcpServers, search]);

  const activeServer = useMemo(() => {
    if (selectedServerName) {
      const found = mcpServers.find((s) => s.name === selectedServerName);
      if (found) return found;
    }
    return filteredServers[0] || mcpServers[0] || null;
  }, [mcpServers, filteredServers, selectedServerName]);

  const filteredPrompts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return prompts.filter((p) => !q || p.name.toLowerCase().includes(q));
  }, [prompts, search]);

  const activePromptSummary = useMemo(() => {
    if (selectedPromptName) {
      const found = prompts.find((p) => p.name === selectedPromptName);
      if (found) return found;
    }
    return filteredPrompts[0] || prompts[0] || null;
  }, [prompts, filteredPrompts, selectedPromptName]);

  useEffect(() => {
    if (subTab !== "prompts" || !activePromptSummary) return;
    const latestVer = activePromptSummary.versions?.[0]?.version ?? "latest";
    setPromptLoading(true);
    api
      .promptDetail(activePromptSummary.name, String(latestVer))
      .then((res) => setPromptDetail(res))
      .catch((e) => setStatusMsg(e instanceof Error ? e.message : String(e)))
      .finally(() => setPromptLoading(false));
  }, [subTab, activePromptSummary]);

  async function handleSavePrompt(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim() || !newTemplate.trim()) return;
    setSavingPrompt(true);
    setStatusMsg(null);
    try {
      const res = await api.createPrompt({
        name: newName.trim(),
        template: newTemplate,
        commitMessage: newCommit.trim() || undefined,
        alias: newAlias.trim() || undefined,
      });
      setStatusMsg(`Saved prompt '${res.name}' v${res.version}`);
      setShowNewPrompt(false);
      setSelectedPromptName(res.name);
      await onReload();
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingPrompt(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Header Bar */}
      <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
            {(
              [
                ["servers", `MCP Servers (${mcpServers.length})`],
                ["prompts", `Prompts (${prompts.length})`],
                ["models", `Models (${(registry?.loggedModels || []).length})`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setSubTab(id)}
                className={`px-3 py-1.5 rounded-md text-[12.5px] font-medium cursor-pointer transition-colors ${
                  subTab === id
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <StatusBadge
            label={mutEnabled ? "mutations enabled" : "read-only"}
            tone={mutEnabled ? "ok" : "warn"}
          />
        </div>

        <div className="flex items-center gap-2">
          {subTab === "prompts" && mutEnabled && (
            <button
              type="button"
              onClick={() => {
                setNewName(activePromptSummary?.name || "");
                setNewTemplate(promptDetail?.template || "");
                setNewCommit("");
                setShowNewPrompt((v) => !v);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              New Prompt / Version
            </button>
          )}
          <button
            type="button"
            onClick={() => onReload()}
            className="px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[12px] cursor-pointer"
          >
            Reload Registry
          </button>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-3.5 py-2 text-[12.5px] text-[var(--accent)]">
          {statusMsg}
        </div>
      )}

      {/* Subtab 1: MCP Servers Master-Detail */}
      {subTab === "servers" && (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
          <aside className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] overflow-hidden">
            <div className="p-3 border-b border-[var(--border-hairline)]">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-2.5" />
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter MCP servers..."
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] pl-8 pr-2.5 py-1.5 text-[12.5px]"
                />
              </div>
            </div>
            <div className="divide-y divide-[var(--border-hairline)] max-h-[540px] overflow-y-auto">
              {filteredServers.map((s) => {
                const selected = activeServer?.name === s.name;
                return (
                  <button
                    key={s.name}
                    type="button"
                    onClick={() => setSelectedServerName(s.name)}
                    className={`w-full text-left px-3.5 py-2.5 cursor-pointer transition-colors ${
                      selected
                        ? "bg-[var(--accent-soft)] border-l-2 border-[var(--accent)]"
                        : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <div className="font-mono text-[12.5px] font-medium truncate">{s.name}</div>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-[var(--text-muted)]">
                      {s.aliases?.production && (
                        <span className="text-[var(--ok)] font-mono">@production={s.aliases.production}</span>
                      )}
                      {s.tags?.scope && <span className="font-mono">{s.tags.scope}</span>}
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 min-w-0">
            {!activeServer ? (
              <div className="text-[13px] text-[var(--text-muted)]">No registered MCP servers.</div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0 space-y-1">
                    <h3 className="font-mono text-[15px] font-semibold m-0 break-all">
                      {activeServer.name}
                    </h3>
                    {activeServer.url && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-[12px] text-[var(--text-secondary)] break-all">
                          {activeServer.url}
                        </span>
                        <CopyButton text={activeServer.url} label="Copy URL" compact />
                      </div>
                    )}
                  </div>
                  {activeServer.version && (
                    <StatusBadge label={`v${activeServer.version}`} tone="ok" />
                  )}
                </div>

                {/* Aliases */}
                <div className="space-y-1.5">
                  <div className="text-[11.5px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                    Aliases
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(activeServer.aliases || {}).length === 0 ? (
                      <span className="text-[12px] text-[var(--text-muted)]">None</span>
                    ) : (
                      Object.entries(activeServer.aliases || {}).map(([alias, ver]) => (
                        <StatusBadge key={alias} label={`@${alias} = ${ver}`} tone="ok" />
                      ))
                    )}
                  </div>
                </div>

                {/* Clean Metadata Table */}
                <div className="space-y-1.5">
                  <div className="text-[11.5px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                    Registry Tags
                  </div>
                  <div className="divide-y divide-[var(--border-hairline)] rounded-lg border border-[var(--border-hairline)]">
                    {Object.entries(activeServer.tags || {}).length === 0 ? (
                      <div className="p-3 text-[12px] text-[var(--text-muted)]">No tags recorded.</div>
                    ) : (
                      Object.entries(activeServer.tags || {}).map(([k, v]) => (
                        <div
                          key={k}
                          className="grid grid-cols-1 sm:grid-cols-[160px_minmax(0,1fr)] gap-2 px-3 py-2.5"
                        >
                          <div className="font-mono text-[12px] text-[var(--text-secondary)]">{k}</div>
                          <div className="font-mono text-[12px] text-[var(--text-primary)] break-all">
                            {v}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* Subtab 2: Prompt Registry Viewer & Authoring */}
      {subTab === "prompts" && (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
          <aside className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] overflow-hidden">
            <div className="p-3 border-b border-[var(--border-hairline)]">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-2.5" />
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter prompts..."
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] pl-8 pr-2.5 py-1.5 text-[12.5px]"
                />
              </div>
            </div>
            <div className="divide-y divide-[var(--border-hairline)] max-h-[540px] overflow-y-auto">
              {filteredPrompts.map((p) => {
                const ver = p.versions?.[0]?.version ?? "?";
                const aliases = (p.versions || []).flatMap((v) => v.aliases || []);
                const selected = activePromptSummary?.name === p.name;
                return (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => setSelectedPromptName(p.name)}
                    className={`w-full text-left px-3.5 py-2.5 cursor-pointer transition-colors ${
                      selected
                        ? "bg-[var(--accent-soft)] border-l-2 border-[var(--accent)]"
                        : "hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[12.5px] font-medium truncate">{p.name}</span>
                      <span className="font-mono text-[11px] text-[var(--text-muted)] shrink-0">
                        v{String(ver)}
                      </span>
                    </div>
                    {aliases.length > 0 && (
                      <div className="text-[11px] font-mono text-[var(--ok)] mt-0.5">
                        {aliases.map((a) => `@${a}`).join(" ")}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="space-y-4 min-w-0">
            {showNewPrompt && mutEnabled && (
              <form
                onSubmit={handleSavePrompt}
                className="rounded-xl border border-[var(--accent)] bg-[var(--bg-surface)] p-5 space-y-3"
              >
                <div className="font-semibold text-[13.5px] flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-[var(--accent)]" />
                  Register New Prompt / Version
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <input
                    type="text"
                    required
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Prompt name (e.g. receipt-writer)"
                    className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                  />
                  <input
                    type="text"
                    value={newAlias}
                    onChange={(e) => setNewAlias(e.target.value)}
                    placeholder="Alias (optional, e.g. production)"
                    className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                  />
                </div>
                <textarea
                  required
                  rows={6}
                  value={newTemplate}
                  onChange={(e) => setNewTemplate(e.target.value)}
                  placeholder="Write prompt template with {{variables}}..."
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12.5px] leading-relaxed"
                />
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <input
                    type="text"
                    value={newCommit}
                    onChange={(e) => setNewCommit(e.target.value)}
                    placeholder="Commit message..."
                    className="flex-1 min-w-[200px] rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 text-[12.5px]"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setShowNewPrompt(false)}
                      className="px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] text-[12px] cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={savingPrompt}
                      className="px-3.5 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
                    >
                      {savingPrompt ? "Saving..." : "Register Prompt"}
                    </button>
                  </div>
                </div>
              </form>
            )}

            <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5">
              {promptLoading ? (
                <div className="text-[13px] text-[var(--text-muted)]">Loading prompt template...</div>
              ) : !promptDetail ? (
                <div className="text-[13px] text-[var(--text-muted)]">Select a prompt to inspect.</div>
              ) : (
                <div className="space-y-4">
                  <PromptRenderer
                    template={promptDetail.template}
                    title={promptDetail.name}
                    version={promptDetail.version}
                    commitMessage={promptDetail.commitMessage}
                  />
                  <div className="flex items-center justify-between gap-2 pt-3 border-t border-[var(--border-hairline)] flex-wrap">
                    <a
                      href={`http://localhost:5002/#/prompts/${encodeURIComponent(promptDetail.name)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[12px] text-[var(--accent)] hover:underline"
                    >
                      Open in MLflow UI <ArrowUpRight className="w-3.5 h-3.5" />
                    </a>
                    {mutEnabled && promptDetail.version && (
                      <button
                        type="button"
                        onClick={async () => {
                          await api.promotePromptAlias(promptDetail.name, String(promptDetail.version), "production");
                          setStatusMsg(`Set @production -> v${promptDetail.version} on ${promptDetail.name}`);
                          await onReload();
                        }}
                        className="px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--ok)] text-[12px] cursor-pointer"
                      >
                        Promote @production
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {/* Subtab 3: LoggedModels & Registered Models */}
      {subTab === "models" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
            <h3 className="text-[13.5px] font-semibold m-0">LoggedModels</h3>
            <div className="divide-y divide-[var(--border-hairline)]">
              {(registry?.loggedModels || []).map((lm) => (
                <div key={lm.modelId} className="py-2.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-[12.5px] truncate">{lm.name || lm.modelId}</div>
                    <div className="font-mono text-[11px] text-[var(--text-muted)]">{lm.modelId}</div>
                  </div>
                  <CopyButton text={lm.modelId} label="Copy ID" compact />
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
            <h3 className="text-[13.5px] font-semibold m-0">Registered Models</h3>
            {(registry?.registeredModels || []).length === 0 ? (
              <div className="text-[12.5px] text-[var(--text-muted)]">No Registered Models in tracking registry.</div>
            ) : (
              <div className="divide-y divide-[var(--border-hairline)]">
                {(registry?.registeredModels || []).map((rm) => (
                  <div key={rm.name} className="py-2.5 flex items-center justify-between gap-3">
                    <span className="font-mono text-[12.5px]">{rm.name}</span>
                    {mutEnabled && rm.latestVersions?.[0]?.version && (
                      <button
                        type="button"
                        onClick={async () => {
                          await api.promoteModelAlias(rm.name, rm.latestVersions![0].version, "production");
                          setStatusMsg(`Set @production on model ${rm.name}`);
                          await onReload();
                        }}
                        className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] text-[11.5px] cursor-pointer"
                      >
                        Promote @production
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
