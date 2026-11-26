import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Filter, RotateCcw, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { api } from "../lib/api";
import { formatDuration, normalizeMultilineText } from "../lib/format";
import type { TracesResponse, TraceDetailResponse } from "../types";
import { CopyButton } from "../components/CopyButton";
import { StatusBadge } from "../components/StatusDot";

function formatPayloadPreview(val: unknown): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "string") return normalizeMultilineText(val);
  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}

export function TracesView() {
  const [experiment, setExperiment] = useState("");
  const [server, setServer] = useState("");
  const [user, setUser] = useState("");
  const [modelId, setModelId] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [refusalFilter, setRefusalFilter] = useState("all");
  const [search, setSearch] = useState("");

  const [data, setData] = useState<TracesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TraceDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [curationMsg, setCurationMsg] = useState<string | null>(null);
  const [expectVal, setExpectVal] = useState("");
  const [tagKey, setTagKey] = useState("triage");
  const [tagVal, setTagVal] = useState("");

  const fetchTraces = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await api.traces({
        limit: "40",
        experiment,
        server,
        user,
        model_id: modelId,
        state: stateFilter,
        policy_refusal: refusalFilter,
        q: search,
      });
      setData(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [experiment, server, user, modelId, stateFilter, refusalFilter, search]);

  useEffect(() => {
    fetchTraces();
  }, [fetchTraces]);

  async function openTrace(traceId: string) {
    setSelectedTraceId(traceId);
    setDetail(null);
    setDetailLoading(true);
    setCurationMsg(null);
    try {
      const d = await api.traceDetail(traceId, data?.experimentId);
      setDetail(d);
    } catch (e) {
      setCurationMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setDetailLoading(false);
    }
  }

  async function runCuration(fn: () => Promise<Record<string, unknown>>, label: string) {
    setCurationMsg(`Saving ${label}...`);
    try {
      await fn();
      setCurationMsg(`Saved ${label}.`);
      if (selectedTraceId) {
        const d = await api.traceDetail(selectedTraceId, data?.experimentId);
        setDetail(d);
      }
    } catch (e) {
      setCurationMsg(e instanceof Error ? e.message : String(e));
    }
  }

  const evalRuns = data?.evalRuns || data?.evalHistory || [];
  const expId = data?.experimentId || "";

  return (
    <div className="space-y-4">
      {/* Eval History */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="text-[13.5px] font-semibold m-0">Eval Run History & Regression Guard</h2>
          <a
            href="http://localhost:5002"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[12px] text-[var(--accent)] hover:underline"
          >
            Open MLflow UI (:5002) <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>

        {evalRuns.length === 0 ? (
          <div className="text-[12.5px] text-[var(--text-muted)]">No benchmark eval runs recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-[12.5px]">
              <thead>
                <tr className="border-b border-[var(--border-hairline)] text-[var(--text-secondary)]">
                  <th className="py-2 pr-3 font-medium">Run</th>
                  <th className="py-2 pr-3 font-medium">Min Score</th>
                  <th className="py-2 font-medium">Scorer Breakdown</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-hairline)]">
                {evalRuns.slice(0, 6).map((run, idx) => {
                  const runId = run.run_id ?? run.runId ?? "";
                  const runName = run.run_name ?? run.runName ?? (runId ? runId.slice(0, 12) : `run-${idx + 1}`);
                  const rawMin = run.min_score ?? run.minScore;
                  const minScore = typeof rawMin === "number" ? rawMin : null;
                  const runHref =
                    expId && runId
                      ? `http://localhost:5002/#/experiments/${encodeURIComponent(expId)}/runs/${encodeURIComponent(runId)}`
                      : "http://localhost:5002";
                  return (
                    <tr key={runId || idx}>
                      <td className="py-2.5 pr-3 whitespace-nowrap">
                        <a
                          href={runHref}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-[var(--accent)] hover:underline"
                        >
                          {runName}
                        </a>
                      </td>
                      <td className="py-2.5 pr-3 whitespace-nowrap">
                        <StatusBadge
                          label={minScore !== null ? `min=${minScore}` : "n/a"}
                          tone={minScore !== null && minScore >= 1 ? "ok" : "err"}
                        />
                      </td>
                      <td className="py-2.5">
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(run.metrics || {}).map(([k, v]) => (
                            <span
                              key={k}
                              className="px-2 py-0.5 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-subtle)] font-mono text-[11px] tabular-nums"
                            >
                              {k.replace("/mean", "")}={v}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Filter Bar + Traces Table */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="text-[13.5px] font-semibold m-0">MLflow Traces & Span Drilldown</h2>
          <span className="text-[12px] text-[var(--text-muted)] tabular-nums">
            {(data?.traces || []).length} traces shown
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <select
            id="tr-experiment-filter"
            aria-label="MLflow experiment"
            value={experiment}
            onChange={(e) => setExperiment(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="">Default Experiment</option>
            {(data?.experiments || []).map((ex) => (
              <option key={ex.id} value={ex.name}>
                {ex.name}
              </option>
            ))}
          </select>

          <select
            aria-label="Server filter"
            value={server}
            onChange={(e) => setServer(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="">All Servers</option>
            {(data?.facets?.servers || []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          <select
            aria-label="User filter"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="">All Users</option>
            {(data?.facets?.users || []).map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>

          <select
            aria-label="LoggedModel filter"
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="">All LoggedModels</option>
            {(data?.facets?.modelIds || data?.facets?.models || []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>

          <select
            aria-label="State filter"
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="">All States</option>
            <option value="OK">OK</option>
            <option value="ERROR">ERROR</option>
          </select>

          <select
            aria-label="Refusal filter"
            value={refusalFilter}
            onChange={(e) => setRefusalFilter(e.target.value)}
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px]"
          >
            <option value="all">Refusals: All</option>
            <option value="only">Refusals Only</option>
            <option value="exclude">Exclude Refusals</option>
          </select>

          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search trace, span, tool..."
            className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px] min-w-[200px]"
          />

          <button
            type="button"
            onClick={fetchTraces}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-medium cursor-pointer"
          >
            <Filter className="w-3.5 h-3.5" />
            Filter
          </button>

          <button
            type="button"
            onClick={() => {
              setExperiment("");
              setServer("");
              setUser("");
              setModelId("");
              setStateFilter("");
              setRefusalFilter("all");
              setSearch("");
            }}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] text-[12px] text-[var(--text-secondary)] cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
        </div>

        {err && (
          <div className="rounded-lg border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] px-3 py-2 text-[12.5px] text-[var(--err)]">
            {err}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-[12.5px]">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] text-[var(--text-secondary)]">
                <th className="py-2 pr-3 font-medium">Trace ID</th>
                <th className="py-2 pr-3 font-medium">Server / Tool</th>
                <th className="py-2 pr-3 font-medium">User</th>
                <th className="py-2 pr-3 font-medium">Model</th>
                <th className="py-2 pr-3 font-medium">Outcome</th>
                <th className="py-2 pr-3 font-medium text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-hairline)]">
              {loading && (data?.traces || []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-[var(--text-muted)]">
                    Loading traces...
                  </td>
                </tr>
              ) : (data?.traces || []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-[var(--text-muted)]">
                    No matching traces found.
                  </td>
                </tr>
              ) : (
                (data?.traces || []).map((tr) => {
                  const outcome = tr.policyRefusal ? "policy_refusal" : tr.state || "OK";
                  const tone = tr.policyRefusal ? "warn" : tr.state === "OK" ? "ok" : "err";
                  const label =
                    tr.server && tr.tool
                      ? `${tr.server}.${tr.tool}`
                      : tr.name || tr.spanName || tr.tool || "—";
                  return (
                    <tr
                      key={tr.traceId}
                      onClick={() => openTrace(tr.traceId)}
                      className="cursor-pointer hover:bg-[var(--bg-hover)] transition-colors"
                    >
                      <td className="py-2.5 pr-3 font-mono text-[11.5px] text-[var(--accent)] whitespace-nowrap">
                        {tr.traceId}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-[12px] max-w-[300px] truncate">
                        {label}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-[12px] text-[var(--text-secondary)] whitespace-nowrap">
                        {tr.user || "—"}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-[11.5px] text-[var(--text-muted)] whitespace-nowrap">
                        {tr.modelId ? tr.modelId.slice(0, 12) : "—"}
                      </td>
                      <td className="py-2.5 pr-3 whitespace-nowrap">
                        <StatusBadge label={outcome} tone={tone} />
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-[12px] text-right tabular-nums whitespace-nowrap">
                        {formatDuration(tr.durationMs)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Slide-Over Span Inspector Drawer */}
      {selectedTraceId && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/55 backdrop-blur-xs"
          onClick={() => setSelectedTraceId(null)}
        >
          <div
            className="w-full max-w-2xl h-full bg-[var(--bg-surface)] border-l border-[var(--border-strong)] shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-4 border-b border-[var(--border-hairline)] flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11.5px] text-[var(--text-muted)]">Trace Inspector</div>
                <div className="font-mono text-[13px] font-semibold truncate">{selectedTraceId}</div>
              </div>
              <div className="flex items-center gap-2">
                <CopyButton text={selectedTraceId} label="Copy ID" compact />
                <button
                  type="button"
                  onClick={() => setSelectedTraceId(null)}
                  className="p-1.5 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {detailLoading ? (
                <div className="text-[13px] text-[var(--text-muted)]">Loading spans...</div>
              ) : (
                <>
                  {/* Curation Bar */}
                  <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3.5 space-y-3">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            runCuration(
                              () => api.logFeedback(selectedTraceId, { name: "human_review", value: true }),
                              "thumbs up",
                            )
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] hover:border-[var(--ok)] text-[12px] cursor-pointer"
                        >
                          <ThumbsUp className="w-3.5 h-3.5 text-[var(--ok)]" />
                          Pass
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            runCuration(
                              () => api.logFeedback(selectedTraceId, { name: "human_review", value: false }),
                              "thumbs down",
                            )
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] hover:border-[var(--err)] text-[12px] cursor-pointer"
                        >
                          <ThumbsDown className="w-3.5 h-3.5 text-[var(--err)]" />
                          Flag
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          runCuration(() => api.promoteTraceDataset(selectedTraceId), "dataset promotion")
                        }
                        className="px-2.5 py-1 rounded-md bg-[var(--accent)] text-white text-[12px] font-medium cursor-pointer"
                      >
                        Promote to Golden Dataset
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div className="flex gap-1.5">
                        <input
                          type="text"
                          value={expectVal}
                          onChange={(e) => setExpectVal(e.target.value)}
                          placeholder="Expected outcome note..."
                          className="flex-1 rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1 text-[12px]"
                        />
                        <button
                          type="button"
                          disabled={!expectVal.trim()}
                          onClick={() =>
                            runCuration(
                              () =>
                                api.logExpectation(selectedTraceId, {
                                  name: "expected_behavior",
                                  value: expectVal.trim(),
                                }),
                              "expectation",
                            )
                          }
                          className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[12px] disabled:opacity-50 cursor-pointer"
                        >
                          Save
                        </button>
                      </div>

                      <div className="flex gap-1.5">
                        <input
                          type="text"
                          value={tagKey}
                          onChange={(e) => setTagKey(e.target.value)}
                          placeholder="key"
                          className="w-20 rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 font-mono text-[12px]"
                        />
                        <input
                          type="text"
                          value={tagVal}
                          onChange={(e) => setTagVal(e.target.value)}
                          placeholder="tag value"
                          className="flex-1 rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1 text-[12px]"
                        />
                        <button
                          type="button"
                          disabled={!tagKey.trim() || !tagVal.trim()}
                          onClick={() =>
                            runCuration(
                              () => api.setTraceTag(selectedTraceId, { key: tagKey.trim(), value: tagVal.trim() }),
                              "tag",
                            )
                          }
                          className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[12px] disabled:opacity-50 cursor-pointer"
                        >
                          Tag
                        </button>
                      </div>
                    </div>

                    {curationMsg && <div className="text-[12px] text-[var(--accent)]">{curationMsg}</div>}
                  </div>

                  {/* Spans */}
                  <div className="space-y-3">
                    {(detail?.spans || []).map((sp) => (
                      <div
                        key={sp.spanId}
                        className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-canvas)] p-4 space-y-3"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="font-mono font-semibold text-[13px]">{sp.name}</div>
                          <div className="flex items-center gap-2">
                            {sp.spanType && (
                              <span className="font-mono text-[11px] text-[var(--text-muted)]">
                                {sp.spanType}
                              </span>
                            )}
                            <StatusBadge
                              label={`${sp.status || "OK"} · ${formatDuration(sp.durationMs)}`}
                              tone={sp.status === "ERROR" ? "err" : "ok"}
                            />
                          </div>
                        </div>

                        <div className="space-y-2">
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-1">
                              Inputs
                            </div>
                            <pre className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words max-h-56 overflow-auto m-0">
                              {formatPayloadPreview(sp.inputs)}
                            </pre>
                          </div>
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-1">
                              Outputs
                            </div>
                            <pre className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words max-h-64 overflow-auto m-0">
                              {formatPayloadPreview(sp.outputs)}
                            </pre>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
