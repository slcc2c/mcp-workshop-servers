import { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, Trash2, X } from "lucide-react";
import { api } from "../lib/api";
import { resolveGatewayBaseUrl } from "../lib/urls";
import type {
  ProfileInventoryItem,
  ServerInventoryItem,
  UpstreamConfigItem,
  UpstreamsSubTab,
} from "../types";
import { CopyButton } from "../components/CopyButton";
import { ProfilesEditor } from "../components/ProfilesEditor";
import { StatusBadge, connectionTone } from "../components/StatusDot";

export function UpstreamsView({
  initialSubTab = "upstreams",
  onChangeSubTab,
  profiles = [],
  servers = [],
  profileCounts = {},
  onAfterChange,
}: {
  initialSubTab?: UpstreamsSubTab;
  onChangeSubTab?: (sub: UpstreamsSubTab) => void;
  profiles?: ProfileInventoryItem[];
  servers?: ServerInventoryItem[];
  profileCounts?: Record<string, number>;
  onAfterChange: () => Promise<void>;
}) {
  const [subTab, setSubTab] = useState<UpstreamsSubTab>(initialSubTab);
  const [items, setItems] = useState<UpstreamConfigItem[]>([]);
  const [configPath, setConfigPath] = useState("config/gateway.local.yaml");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [probingSlug, setProbingSlug] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [transport, setTransport] = useState<"http" | "stdio">("http");
  const [url, setUrl] = useState("");
  const [headersJson, setHeadersJson] = useState("{}");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [cwd, setCwd] = useState("");
  const [profilesCsv, setProfilesCsv] = useState("studio");
  const [governance, setGovernance] = useState("external-proxy");
  const [description, setDescription] = useState("");
  const [allowToolsText, setAllowToolsText] = useState("");
  const [denyToolsText, setDenyToolsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);

  useEffect(() => {
    setSubTab(initialSubTab);
  }, [initialSubTab]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.upstreams();
      setItems(res.upstreams || []);
      setConfigPath(res.configPath || "config/gateway.local.yaml");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function openNewModal() {
    setSlug("");
    setTransport("http");
    setUrl("");
    setHeadersJson("{}");
    setCommand("");
    setArgsText("");
    setCwd("");
    setProfilesCsv("studio");
    setGovernance("external-proxy");
    setDescription("");
    setAllowToolsText("");
    setDenyToolsText("");
    setFormErr(null);
    setModalOpen(true);
  }

  function openEditModal(item: UpstreamConfigItem) {
    setSlug(item.slug);
    setTransport(item.transport);
    setUrl(item.url || "");
    setHeadersJson(JSON.stringify(item.headers || {}, null, 2));
    setCommand(item.command || "");
    setArgsText((item.args || []).join("\n"));
    setCwd(item.cwd || "");
    setProfilesCsv((item.profiles || ["studio"]).join(", "));
    setGovernance(item.governance || "external-proxy");
    setDescription(item.description || "");
    setAllowToolsText((item.allow_tools || []).join("\n"));
    setDenyToolsText((item.deny_tools || []).join("\n"));
    setFormErr(null);
    setModalOpen(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setFormErr(null);
    let parsedHeaders: Record<string, string> = {};
    try {
      parsedHeaders = JSON.parse(headersJson.trim() || "{}") as Record<string, string>;
    } catch (err) {
      setFormErr(`Invalid headers JSON: ${err instanceof Error ? err.message : String(err)}`);
      return;
    }
    setSaving(true);
    try {
      await api.upsertUpstream(slug.trim(), {
        slug: slug.trim(),
        transport,
        url: transport === "http" ? url.trim() : null,
        headers: transport === "http" ? parsedHeaders : {},
        command: transport === "stdio" ? command.trim() : null,
        args:
          transport === "stdio"
            ? argsText
                .split("\n")
                .map((s) => s.trim())
                .filter(Boolean)
            : [],
        cwd: transport === "stdio" && cwd.trim() ? cwd.trim() : null,
        profiles: profilesCsv
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        allow_tools: allowToolsText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        deny_tools: denyToolsText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        governance: governance.trim() || "external-proxy",
        description: description.trim(),
        enabled: true,
      });
      setModalOpen(false);
      setMsg(`Saved upstream '${slug.trim()}' to ${configPath}`);
      await load();
      await onAfterChange();
    } catch (err) {
      setFormErr(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(item: UpstreamConfigItem) {
    setMsg(null);
    try {
      await api.upsertUpstream(item.slug, {
        transport: item.transport,
        url: item.url,
        headers: item.headers || {},
        command: item.command,
        args: item.args || [],
        cwd: item.cwd,
        env: item.env || {},
        profiles: item.profiles || ["studio"],
        governance: item.governance,
        description: item.description,
        registry_name: item.registry_name,
        enabled: !item.enabled,
      });
      setMsg(`${!item.enabled ? "Enabled" : "Disabled"} '${item.slug}'`);
      await load();
      await onAfterChange();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
            {(
              [
                ["upstreams", `Upstreams (${items.length})`],
                ["profiles", `Profiles (${profiles.length})`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setSubTab(id);
                  onChangeSubTab?.(id);
                }}
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
          <div className="text-[12px] text-[var(--text-muted)] font-mono">{configPath}</div>
        </div>
        {subTab === "upstreams" && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[12px] cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
            <button
              type="button"
              onClick={openNewModal}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12.5px] font-semibold cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Upstream
            </button>
          </div>
        )}
      </div>

      {subTab === "profiles" ? (
        <ProfilesEditor
          profiles={profiles}
          servers={servers}
          profileCounts={profileCounts}
          onChanged={async () => {
            await onAfterChange();
            await load();
          }}
        />
      ) : (
        <>

      {msg && (
        <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] px-3.5 py-2 text-[12.5px] text-[var(--accent)]">
          {msg}
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-8 text-center text-[var(--text-muted)]">
          Loading upstreams...
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-8 text-center text-[var(--text-muted)]">
          No federated upstreams configured yet. Click Add Upstream or run{" "}
          <code className="font-mono">mcp-stack upstream add</code>.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {items.map((item) => (
            <div
              key={item.slug}
              className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 flex flex-col justify-between gap-3"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-[14px]">{item.slug}</span>
                      <span className="px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border-hairline)] font-mono text-[10.5px] text-[var(--text-secondary)]">
                        {item.transport}
                      </span>
                    </div>
                    <div className="font-mono text-[11.5px] text-[var(--text-muted)] break-all mt-0.5">
                      {item.transport === "http" ? item.url : `${item.command} ${(item.args || []).join(" ")}`}
                    </div>
                  </div>
                  <StatusBadge label={item.connectionStatus} tone={connectionTone(item.connectionStatus)} />
                </div>

                {item.description && (
                  <p className="text-[12.5px] text-[var(--text-secondary)] leading-relaxed m-0">
                    {item.description}
                  </p>
                )}

                {item.detail && (
                  <div className="rounded-lg border border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--warn-soft)] px-2.5 py-2 text-[12px] text-[var(--warn)] space-y-1 break-words">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {item.authReasonCode && (
                        <StatusBadge label={item.authReasonCode} tone="warn" />
                      )}
                      <span>{item.detail}</span>
                    </div>
                    {item.connectionStatus === "auth_required" && (
                      <div className="text-[11px] text-[var(--text-secondary)]">
                        Unlock 1Password Desktop or set{" "}
                        <code className="font-mono">OP_SERVICE_ACCOUNT_TOKEN</code>, then click Probe.
                      </div>
                    )}
                  </div>
                )}

                {item.sampleTools && item.sampleTools.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {item.sampleTools.slice(0, 5).map((toolName) => (
                      <span
                        key={toolName}
                        className="px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-hairline)] font-mono text-[10.5px] text-[var(--text-secondary)]"
                      >
                        {toolName}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-3 text-[11.5px] font-mono text-[var(--text-muted)] flex-wrap">
                  <span>
                    {typeof item.rawToolCount === "number" && item.rawToolCount !== item.toolCount
                      ? `${item.exposedToolCount ?? item.toolCount}/${item.rawToolCount} tools (curated)`
                      : `${item.toolCount} tools`}
                  </span>
                  <span>profiles: {(item.profiles || []).join(", ")}</span>
                  <span>governance: {item.governance}</span>
                </div>
              </div>

              <div className="flex items-center justify-between gap-2 pt-2.5 border-t border-[var(--border-hairline)] flex-wrap">
                <CopyButton text={`${resolveGatewayBaseUrl()}${item.route}`} label={item.route} compact />
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={probingSlug === item.slug}
                    onClick={async () => {
                      setProbingSlug(item.slug);
                      try {
                        await api.probeUpstream(item.slug);
                        await load();
                        await onAfterChange();
                      } finally {
                        setProbingSlug(null);
                      }
                    }}
                    className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[12px] cursor-pointer"
                  >
                    {probingSlug === item.slug ? "Probing..." : "Probe"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggle(item)}
                    className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[12px] cursor-pointer"
                  >
                    {item.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    type="button"
                    onClick={() => openEditModal(item)}
                    className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[12px] cursor-pointer"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${item.slug}`}
                    onClick={async () => {
                      await api.deleteUpstream(item.slug);
                      setMsg(`Removed '${item.slug}'`);
                      await load();
                      await onAfterChange();
                    }}
                    className="p-1.5 rounded-md border border-[var(--border-hairline)] text-[var(--err)] hover:bg-[var(--err-soft)] cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-[14.5px]">Configure External Upstream</div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="p-1 rounded-md text-[var(--text-secondary)] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {formErr && (
              <div className="rounded-lg border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
                {formErr}
              </div>
            )}

            <form onSubmit={handleSave} className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[12px] text-[var(--text-secondary)]">Slug</label>
                  <input
                    type="text"
                    required
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="e.g. printer"
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[12px] text-[var(--text-secondary)]">Transport</label>
                  <select
                    value={transport}
                    onChange={(e) => setTransport(e.target.value as "http" | "stdio")}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 text-[12.5px]"
                  >
                    <option value="http">Streamable HTTP</option>
                    <option value="stdio">Stdio Subprocess</option>
                  </select>
                </div>
              </div>

              {transport === "http" ? (
                <>
                  <div className="space-y-1">
                    <label className="text-[12px] text-[var(--text-secondary)]">MCP Endpoint URL</label>
                    <input
                      type="url"
                      required
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://mcp.example.com/mcp"
                      className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[12px] text-[var(--text-secondary)]">
                      Headers JSON (must use <code>env:VAR</code> or <code>op://</code> refs)
                    </label>
                    <textarea
                      rows={3}
                      value={headersJson}
                      onChange={(e) => setHeadersJson(e.target.value)}
                      placeholder='{"Authorization": "Bearer env:LINEAR_API_KEY"}'
                      className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-2.5 font-mono text-[12px]"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-1">
                    <label className="text-[12px] text-[var(--text-secondary)]">Command</label>
                    <input
                      type="text"
                      required
                      value={command}
                      onChange={(e) => setCommand(e.target.value)}
                      placeholder="/path/to/bin"
                      className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                    />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-[12px] text-[var(--text-secondary)]">Args (one per line)</label>
                      <textarea
                        rows={3}
                        value={argsText}
                        onChange={(e) => setArgsText(e.target.value)}
                        className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-2 font-mono text-[12px]"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[12px] text-[var(--text-secondary)]">Working Directory</label>
                      <input
                        type="text"
                        value={cwd}
                        onChange={(e) => setCwd(e.target.value)}
                        placeholder="/Users/spencer/repos/..."
                        className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                      />
                    </div>
                  </div>
                </>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[12px] text-[var(--text-secondary)]">Profiles (comma-separated)</label>
                  <input
                    type="text"
                    value={profilesCsv}
                    onChange={(e) => setProfilesCsv(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[12px] text-[var(--text-secondary)]">Governance Policy</label>
                  <input
                    type="text"
                    value={governance}
                    onChange={(e) => setGovernance(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 font-mono text-[12.5px]"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-[12px] text-[var(--text-secondary)]">
                    Tool Curation Globs (allow_tools / deny_tools, one per line)
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setAllowToolsText("get_*\nlist_*\nsearch_*");
                      setDenyToolsText("");
                    }}
                    className="px-2 py-0.5 rounded border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[11px] font-mono cursor-pointer"
                  >
                    Read-only preset
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <textarea
                    rows={2}
                    aria-label="Allow tools globs"
                    value={allowToolsText}
                    onChange={(e) => setAllowToolsText(e.target.value)}
                    placeholder="allow_tools (optional)"
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-2 font-mono text-[12px]"
                  />
                  <textarea
                    rows={2}
                    aria-label="Deny tools globs"
                    value={denyToolsText}
                    onChange={(e) => setDenyToolsText(e.target.value)}
                    placeholder="deny_tools (optional)"
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-2 font-mono text-[12px]"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[12px] text-[var(--text-secondary)]">Description</label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Short description for Control Plane & discovery"
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-1.5 text-[12.5px]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] text-[12.5px] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12.5px] font-semibold cursor-pointer"
                >
                  {saving ? "Saving & Probing..." : "Save & Probe"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}
