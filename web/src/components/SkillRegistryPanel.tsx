import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, BookOpen, Plus, RefreshCw, Upload } from "lucide-react";
import { api } from "../lib/api";
import type {
  SkillRegistryDetailResponse,
  SkillRegistryItem,
} from "../types";
import { StatusBadge } from "./StatusDot";

export function SkillRegistryPanel() {
  const [loading, setLoading] = useState(false);
  const [supported, setSupported] = useState(true);
  const [serverVersion, setServerVersion] = useState<string | null>(null);
  const [requiredVersion, setRequiredVersion] = useState<string>("3.18.0");
  const [skills, setSkills] = useState<SkillRegistryItem[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<SkillRegistryDetailResponse | null>(null);
  const [showPublish, setShowPublish] = useState(false);
  const [publishSource, setPublishSource] = useState("");
  const [publishName, setPublishName] = useState("");
  const [publishOrg, setPublishOrg] = useState("");
  const [publishStatus, setPublishStatus] = useState("draft");
  const [aliasInput, setAliasInput] = useState("production");
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.mlflowSkills({
        ...(query.trim() ? { q: query.trim() } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
      });
      setSupported(res.supported);
      setServerVersion(res.serverVersion ?? null);
      setRequiredVersion(res.requiredVersion || "3.18.0");
      setSkills(res.skills || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [query, statusFilter]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const inspectSkill = async (item: SkillRegistryItem, version?: string) => {
    setError(null);
    try {
      const detail = await api.mlflowSkillDetail(item.name, {
        ...(item.organization ? { organization: item.organization } : {}),
        ...(version ? { version_or_alias: version } : {}),
      });
      setSelected(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handlePublish = async () => {
    if (!publishSource.trim()) return;
    setError(null);
    try {
      await api.publishMlflowSkill({
        source: publishSource.trim(),
        ...(publishName.trim() ? { name: publishName.trim() } : {}),
        ...(publishOrg.trim() ? { organization: publishOrg.trim() } : {}),
        status: publishStatus,
      });
      setShowPublish(false);
      setPublishSource("");
      setPublishName("");
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleUpdateVersion = async (version: string, updates: { status?: string; alias?: string }) => {
    if (!selected) return;
    setError(null);
    try {
      await api.updateMlflowSkillVersion(selected.name, version, {
        ...updates,
        ...(selected.organization ? { organization: selected.organization } : {}),
      });
      await inspectSkill({ name: selected.name, organization: selected.organization }, version);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="space-y-4">
      {!supported && (
        <div
          data-testid="skill-registry-unsupported"
          className="rounded-xl border border-[color-mix(in_srgb,var(--warn)_40%,transparent)] bg-[var(--warn-soft)] p-3.5 text-[12.5px] flex items-start gap-2.5"
        >
          <AlertTriangle className="w-4 h-4 text-[var(--warn)] shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold text-[var(--warn)]">
              MLflow Skill Registry requires MLflow {">="} {requiredVersion}
            </div>
            <div className="text-[var(--text-secondary)]">
              Tracking server reports version{" "}
              <code className="font-mono">{serverVersion || "unknown"}</code>. Local harness skill
              sync remains available in the table below.
            </div>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-[var(--accent)]" />
            <div>
              <h2 className="text-[14px] font-semibold m-0">MLflow Skill Registry</h2>
              <p className="text-[11.5px] text-[var(--text-muted)] m-0">
                Tracking server {serverVersion ? `v${serverVersion}` : "unprobed"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => loadList()}
              disabled={loading}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[12px] cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => setShowPublish((v) => !v)}
              disabled={!supported}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12px] font-semibold cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              Register Skill
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search MLflow skills..."
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] min-w-[200px]"
          />
          <select
            aria-label="Filter registry skill status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="">All statuses</option>
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="deprecated">deprecated</option>
          </select>
        </div>

        {showPublish && (
          <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3 space-y-2.5">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
              <input
                type="text"
                value={publishSource}
                onChange={(e) => setPublishSource(e.target.value)}
                placeholder="Git URL or local skill directory"
                className="md:col-span-2 rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px] font-mono"
              />
              <input
                type="text"
                value={publishName}
                onChange={(e) => setPublishName(e.target.value)}
                placeholder="Skill name (optional)"
                className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px] font-mono"
              />
              <input
                type="text"
                value={publishOrg}
                onChange={(e) => setPublishOrg(e.target.value)}
                placeholder="Organization (optional)"
                className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px] font-mono"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={publishStatus}
                onChange={(e) => setPublishStatus(e.target.value)}
                className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1 text-[12px]"
              >
                <option value="draft">draft</option>
                <option value="active">active</option>
              </select>
              <button
                type="button"
                onClick={handlePublish}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
              >
                <Upload className="w-3.5 h-3.5" />
                Register
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
            {error}
          </div>
        )}

        {supported && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <div className="lg:col-span-5 space-y-1.5">
              {skills.length === 0 ? (
                <div className="py-6 text-center text-[12px] text-[var(--text-muted)]">
                  No skills registered in MLflow yet.
                </div>
              ) : (
                skills.map((item) => (
                  <button
                    key={`${item.organization || ""}:${item.name}`}
                    type="button"
                    onClick={() => inspectSkill(item)}
                    className={`w-full text-left rounded-lg border p-2.5 cursor-pointer transition-colors ${
                      selected?.name === item.name
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-semibold text-[12.5px]">{item.name}</span>
                      {item.latestVersion && (
                        <StatusBadge label={`v${item.latestVersion}`} tone="neutral" />
                      )}
                    </div>
                    {item.description && (
                      <div className="text-[11.5px] text-[var(--text-secondary)] truncate mt-0.5">
                        {item.description}
                      </div>
                    )}
                  </button>
                ))
              )}
            </div>

            <div className="lg:col-span-7">
              {selected ? (
                <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-3.5 space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div>
                      <h3 className="font-mono text-[13.5px] font-semibold m-0">
                        {selected.organization ? `${selected.organization}/` : ""}
                        {selected.name}
                      </h3>
                      {selected.description && (
                        <p className="text-[12px] text-[var(--text-secondary)] m-0 mt-0.5">
                          {selected.description}
                        </p>
                      )}
                    </div>
                    {selected.selectedVersion && (
                      <StatusBadge
                        label={`v${selected.selectedVersion.version} · ${selected.selectedVersion.status || "unknown"}`}
                        tone={selected.selectedVersion.status === "active" ? "ok" : "neutral"}
                      />
                    )}
                  </div>

                  {selected.selectedVersion && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <select
                        aria-label="Version lifecycle status"
                        value={selected.selectedVersion.status || "draft"}
                        onChange={(e) =>
                          handleUpdateVersion(String(selected.selectedVersion!.version), {
                            status: e.target.value,
                          })
                        }
                        className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 text-[11.5px]"
                      >
                        <option value="draft">draft</option>
                        <option value="active">active</option>
                        <option value="deprecated">deprecated</option>
                      </select>
                      <input
                        type="text"
                        value={aliasInput}
                        onChange={(e) => setAliasInput(e.target.value)}
                        placeholder="alias"
                        className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 text-[11.5px] font-mono w-28"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          handleUpdateVersion(String(selected.selectedVersion!.version), {
                            alias: aliasInput.trim(),
                          })
                        }
                        className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] text-[11.5px] cursor-pointer"
                      >
                        Set Alias
                      </button>
                    </div>
                  )}

                  {selected.skillMd && (
                    <pre className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 text-[11.5px] font-mono whitespace-pre-wrap max-h-72 overflow-y-auto m-0">
                      {selected.skillMd}
                    </pre>
                  )}
                </div>
              ) : (
                <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-6 text-center text-[12px] text-[var(--text-muted)]">
                  Select a registered skill to inspect SKILL.md and versions.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
