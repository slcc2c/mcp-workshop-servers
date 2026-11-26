import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, FolderGit2, Play, RefreshCw, ShieldAlert } from "lucide-react";
import { api } from "../lib/api";
import type { SkillAuditResponse, SkillSyncResponse } from "../types";
import { StatusBadge } from "../components/StatusDot";

function statusTone(status: string | undefined): "ok" | "warn" | "err" | "neutral" {
  if (status === "synced" || status === "atelier_managed") return "ok";
  if (status === "drifted_copy" || status === "extra_unmanaged") return "warn";
  if (status === "missing" || status === "wrong_target") return "err";
  return "neutral";
}

export function SkillsView() {
  const [audit, setAudit] = useState<SkillAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SkillSyncResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [quarantineLegacy, setQuarantineLegacy] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.skills();
      setAudit(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills audit");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  async function runSync(dryRun: boolean) {
    setSyncing(true);
    setError(null);
    try {
      const res = await api.syncSkills({
        dry_run: dryRun,
        quarantine_legacy: quarantineLegacy,
      });
      setSyncResult(res);
      if (!dryRun) {
        await load();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Skill sync failed");
    } finally {
      setSyncing(false);
    }
  }

  const targetIds = useMemo(() => Object.keys(audit?.targets || {}), [audit]);
  const sources = useMemo(() => {
    const set = new Set<string>();
    for (const sk of audit?.skills || []) {
      set.add(sk.sourceId);
    }
    return Array.from(set).sort();
  }, [audit]);

  const filteredSkills = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (audit?.skills || []).filter((sk) => {
      if (sourceFilter !== "all" && sk.sourceId !== sourceFilter) return false;
      if (onlyIssues) {
        const hasIssue = Object.values(sk.targets || {}).some(
          (st) => st !== "synced" && st !== "atelier_managed",
        );
        if (!hasIssue) return false;
      }
      if (
        q &&
        !sk.name.toLowerCase().includes(q) &&
        !sk.sourceId.toLowerCase().includes(q) &&
        !sk.description.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [audit, query, sourceFilter, onlyIssues]);

  if (audit && !audit.available) {
    return (
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 space-y-2">
        <div className="flex items-center gap-2 text-[var(--warn)] font-semibold text-[14px]">
          <ShieldAlert className="w-4 h-4" />
          Skills Manifest Unavailable
        </div>
        <p className="text-[12.5px] text-[var(--text-secondary)] m-0">
          {audit.error || "Configure MCP_SKILLS_MANIFEST_PATH to inspect cross-harness skills."}
        </p>
      </section>
    );
  }

  const summary = audit?.summary;

  return (
    <div className="space-y-4">
      {/* KPI Summary */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
            Canonical Skills
          </div>
          <div className="text-[22px] font-semibold font-mono tabular-nums mt-1">
            {summary?.canonicalSkills ?? "—"}
          </div>
        </div>
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
            Synced Symlinks
          </div>
          <div className="text-[22px] font-semibold font-mono tabular-nums text-[var(--ok)] mt-1">
            {summary?.syncedLinks ?? "—"}
          </div>
        </div>
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
            Drift / Missing
          </div>
          <div
            className={`text-[22px] font-semibold font-mono tabular-nums mt-1 ${
              (summary?.driftIssues ?? 0) > 0 ? "text-[var(--warn)]" : "text-[var(--ok)]"
            }`}
          >
            {summary?.driftIssues ?? "—"}
          </div>
        </div>
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
            Cross-Layer Collisions
          </div>
          <div
            className={`text-[22px] font-semibold font-mono tabular-nums mt-1 ${
              (summary?.collisions ?? 0) > 0 ? "text-[var(--warn)]" : "text-[var(--ok)]"
            }`}
          >
            {summary?.collisions ?? "—"}
          </div>
        </div>
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
            Legacy Quarantine
          </div>
          <div className="text-[22px] font-semibold font-mono tabular-nums mt-1">
            {summary?.legacyItems ?? "—"}
          </div>
        </div>
      </div>

      {/* Sync Controls */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-[14px] font-semibold m-0">Cross-Harness Skill Projection</h2>
            <p className="text-[12px] text-[var(--text-secondary)] m-0 mt-0.5">
              Manifest: <code className="font-mono">{audit?.manifestPath || "default"}</code>
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)] cursor-pointer">
              <input
                type="checkbox"
                checked={quarantineLegacy}
                onChange={(e) => setQuarantineLegacy(e.target.checked)}
              />
              Quarantine legacy roots
            </label>
            <button
              type="button"
              onClick={() => load()}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[12px] cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => runSync(true)}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[12px] font-medium cursor-pointer"
            >
              <Play className="w-3.5 h-3.5" />
              Preview Sync (Dry Run)
            </button>
            <button
              type="button"
              onClick={() => runSync(false)}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12px] font-semibold cursor-pointer"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Apply Sync
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
            {error}
          </div>
        )}

        {syncResult && (
          <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 text-[12px] space-y-1">
            <div className="font-semibold">
              {syncResult.dryRun ? "Dry-run preview" : "Applied"}: {syncResult.symlinkedCount} symlinks,{" "}
              {syncResult.quarantinedCount} quarantined
            </div>
            {syncResult.quarantineBatch && (
              <div className="font-mono text-[11px] text-[var(--text-secondary)]">
                Quarantine batch: {syncResult.quarantineBatch}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Collisions & Plugin Shadows */}
      {(audit?.collisions?.length || 0) > 0 && (
        <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2.5">
          <div className="flex items-center gap-2 text-[13px] font-semibold">
            <AlertTriangle className="w-4 h-4 text-[var(--warn)]" />
            Cross-Layer Collisions & Alias Overlaps ({audit?.collisions?.length})
          </div>
          <div className="space-y-2">
            {audit?.collisions?.map((col) => (
              <div
                key={`${col.kind}:${col.group}`}
                className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3 text-[12px] space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-semibold">{col.group}</span>
                  <StatusBadge label={col.kind} tone="warn" />
                </div>
                <div className="text-[var(--text-secondary)]">{col.recommendation}</div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {col.occurrences.map((occ, i) => (
                    <span
                      key={`${occ.layer}-${i}`}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[var(--code-bg)] border border-[var(--border-hairline)] font-mono text-[11px]"
                      title={occ.path}
                    >
                      <FolderGit2 className="w-3 h-3" />
                      {occ.layer}
                      {occ.origin ? `:${occ.origin}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Skill Harness Matrix */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter skills..."
              className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] min-w-[200px]"
            />
            <select
              aria-label="Filter skill source"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
            >
              <option value="all">All sources</option>
              {sources.map((src) => (
                <option key={src} value={src}>
                  {src}
                </option>
              ))}
            </select>
            <label className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)] cursor-pointer">
              <input
                type="checkbox"
                checked={onlyIssues}
                onChange={(e) => setOnlyIssues(e.target.checked)}
              />
              Issues only
            </label>
          </div>
          <div className="text-[11.5px] text-[var(--text-muted)] font-mono">
            {filteredSkills.length} skills
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] text-[var(--text-muted)]">
                <th className="py-2 pr-3 font-medium">Skill</th>
                <th className="py-2 pr-3 font-medium">Source</th>
                {targetIds.map((tid) => (
                  <th key={tid} className="py-2 pr-3 font-medium font-mono">
                    {tid}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredSkills.map((sk) => (
                <tr key={sk.name} className="border-b border-[var(--border-hairline)]/60">
                  <td className="py-2 pr-3">
                    <div className="font-mono font-medium">{sk.name}</div>
                    <div className="text-[11px] text-[var(--text-muted)] truncate max-w-[260px]">
                      {sk.description}
                    </div>
                  </td>
                  <td className="py-2 pr-3 font-mono text-[11px] text-[var(--text-secondary)]">
                    {sk.sourceId}
                  </td>
                  {targetIds.map((tid) => {
                    const st = sk.targets?.[tid] || "n/a";
                    return (
                      <td key={tid} className="py-2 pr-3">
                        <StatusBadge label={st} tone={statusTone(st)} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
