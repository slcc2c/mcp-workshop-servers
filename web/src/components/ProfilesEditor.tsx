import { useMemo, useState } from "react";
import { Layers, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { ProfileInventoryItem, ServerInventoryItem } from "../types";
import { StatusBadge } from "./StatusDot";

function parseGlobInput(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatTokenCount(tokens: number): string {
  if (tokens >= 1000) return `~${(tokens / 1000).toFixed(1)}k tok`;
  return `~${tokens} tok`;
}

function tokenBudgetTone(tokens: number): "ok" | "warn" | "err" {
  if (tokens > 16000) return "err";
  if (tokens > 8000) return "warn";
  return "ok";
}

export function ProfilesEditor({
  profiles,
  servers,
  profileCounts,
  onChanged,
}: {
  profiles: ProfileInventoryItem[];
  servers: ServerInventoryItem[];
  profileCounts: Record<string, number>;
  onChanged: () => Promise<void>;
}) {
  const [editingName, setEditingName] = useState<string>("");
  const [isNew, setIsNew] = useState<boolean>(true);
  const [selectedServers, setSelectedServers] = useState<string[]>(["gateway"]);
  const [allowGlobsText, setAllowGlobsText] = useState<string>("");
  const [denyGlobsText, setDenyGlobsText] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const serverToolMap = useMemo(() => {
    const m: Record<string, number> = {};
    for (const s of servers) {
      m[s.slug] = s.toolCount || 0;
    }
    return m;
  }, [servers]);

  const draftToolBudget = useMemo(
    () => selectedServers.reduce((acc, slug) => acc + (serverToolMap[slug] || 0), 0),
    [selectedServers, serverToolMap],
  );

  const startCreate = () => {
    setIsNew(true);
    setEditingName("");
    setSelectedServers(["gateway"]);
    setAllowGlobsText("");
    setDenyGlobsText("");
    setError(null);
  };

  const startEdit = (p: ProfileInventoryItem) => {
    setIsNew(false);
    setEditingName(p.name);
    setSelectedServers([...(p.servers || [])]);
    setAllowGlobsText((p.allowTools || []).join(", "));
    setDenyGlobsText((p.denyTools || []).join(", "));
    setError(null);
  };

  const toggleServer = (slug: string) => {
    setSelectedServers((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    );
  };

  const handleSave = async () => {
    const clean = editingName.trim().toLowerCase();
    if (!clean) {
      setError("Profile name is required.");
      return;
    }
    const allowList = parseGlobInput(allowGlobsText);
    const denyList = parseGlobInput(denyGlobsText);
    const hasFilterPayload = !isNew || allowList.length > 0 || denyList.length > 0;
    const filters = hasFilterPayload ? { allow_tools: allowList, deny_tools: denyList } : undefined;
    setSaving(true);
    setError(null);
    try {
      if (isNew) {
        await api.createProfile(clean, selectedServers, filters);
      } else {
        await api.updateProfile(clean, selectedServers, filters);
      }
      await onChanged();
      if (isNew) startCreate();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (name: string) => {
    setSaving(true);
    setError(null);
    try {
      await api.deleteProfile(name);
      await onChanged();
      if (editingName === name) startCreate();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      <div className="lg:col-span-7 space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[14px] font-semibold">
            <Layers className="w-4 h-4 text-[var(--accent)]" />
            Curated Endpoint Profiles
          </div>
          <button
            type="button"
            onClick={startCreate}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            New Profile
          </button>
        </div>

        <div className="space-y-2">
          {profiles.map((p) => {
            const count = typeof p.toolCount === "number" ? p.toolCount : profileCounts[p.name];
            const estTokens = p.estimatedSchemaTokens;
            const filterCount = (p.allowTools?.length || 0) + (p.denyTools?.length || 0);
            return (
              <div
                key={p.name}
                data-testid={`profile-card-${p.name}`}
                className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5 space-y-2"
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-semibold text-[13px]">{p.name}</span>
                    {p.builtin && <StatusBadge label="built-in" tone="neutral" />}
                    {p.name === "discover" && <StatusBadge label="progressive-disclosure" tone="accent" />}
                    {filterCount > 0 && <StatusBadge label={`${filterCount} globs`} tone="accent" />}
                    {typeof count === "number" && (
                      <span className="font-mono text-[11px] text-[var(--text-muted)]">
                        {count} tools
                      </span>
                    )}
                    {typeof estTokens === "number" && estTokens > 0 && (
                      <StatusBadge
                        label={formatTokenCount(estTokens)}
                        tone={tokenBudgetTone(estTokens)}
                      />
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {!p.builtin && (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(p)}
                          className="px-2 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[11.5px] cursor-pointer"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(p.name)}
                          disabled={saving}
                          aria-label={`Delete profile ${p.name}`}
                          className="p-1.5 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--err-soft)] text-[var(--err)] cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
                <div className="font-mono text-[11px] text-[var(--text-muted)]">{p.route}</div>
                <div className="flex flex-wrap gap-1.5">
                  {p.servers.map((srv) => (
                    <span
                      key={srv}
                      className="px-2 py-0.5 rounded bg-[var(--code-bg)] border border-[var(--border-hairline)] font-mono text-[11px]"
                    >
                      {srv}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="lg:col-span-5">
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[13.5px] font-semibold m-0">
              {isNew ? "Create Custom Profile" : `Edit Profile: ${editingName}`}
            </h3>
            <StatusBadge
              label={`Est. ${draftToolBudget} tools`}
              tone={draftToolBudget > 80 ? "warn" : "ok"}
            />
          </div>

          <label className="block text-[12px] text-[var(--text-secondary)] space-y-1">
            <span>Profile slug</span>
            <input
              type="text"
              aria-label="Profile name"
              value={editingName}
              disabled={!isNew}
              onChange={(e) => setEditingName(e.target.value)}
              placeholder="e.g. research-ops"
              className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] font-mono disabled:opacity-60"
            />
          </label>

          <div className="space-y-1.5">
            <div className="text-[12px] text-[var(--text-secondary)]">Included servers</div>
            <div className="max-h-[260px] overflow-y-auto space-y-1 pr-1">
              {servers.map((srv) => {
                const checked = selectedServers.includes(srv.slug);
                return (
                  <label
                    key={srv.slug}
                    className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] text-[12px] cursor-pointer"
                  >
                    <span className="inline-flex items-center gap-2 font-mono">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleServer(srv.slug)}
                      />
                      {srv.slug}
                    </span>
                    <span className="font-mono text-[11px] text-[var(--text-muted)]">
                      {srv.toolCount || 0} tools
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="block text-[11.5px] text-[var(--text-secondary)] space-y-1">
              <span>Allow tool globs (optional)</span>
              <input
                type="text"
                aria-label="Allow tool globs"
                value={allowGlobsText}
                onChange={(e) => setAllowGlobsText(e.target.value)}
                placeholder="list_*, get_*"
                className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[11.5px] font-mono"
              />
            </label>
            <label className="block text-[11.5px] text-[var(--text-secondary)] space-y-1">
              <span>Deny tool globs (optional)</span>
              <input
                type="text"
                aria-label="Deny tool globs"
                value={denyGlobsText}
                onChange={(e) => setDenyGlobsText(e.target.value)}
                placeholder="delete_*, print_*"
                className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[11.5px] font-mono"
              />
            </label>
          </div>

          {error && (
            <div className="rounded-lg bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !editingName.trim()}
            className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12.5px] font-semibold cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? "Saving..." : isNew ? "Create Profile" : "Save Profile"}
          </button>
        </div>
      </div>
    </div>
  );
}
