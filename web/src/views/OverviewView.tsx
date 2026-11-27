import { useEffect, useState } from "react";
import {
  Activity,
  ExternalLink,
  KeyRound,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Terminal,
} from "lucide-react";
import { api } from "../lib/api";
import { buildMlflowExperimentUrl, resolveGatewayBaseUrl, resolveMlflowUiUrl } from "../lib/urls";
import type {
  AuthState,
  EvalRunItem,
  HealthResponse,
  OpsMetricsBucket,
  OpsMetricsSeriesResponse,
  ReadyResponse,
  SecretsHealthResponse,
  ServerInventoryItem,
  WatchdogResponse,
} from "../types";
import { CopyButton } from "../components/CopyButton";
import { StatusBadge, connectionTone } from "../components/StatusDot";

function LatencySparkline({ buckets }: { buckets: OpsMetricsBucket[] }) {
  if (buckets.length === 0) return null;
  const w = Math.max(180, buckets.length * 16);
  const h = 38;
  const maxMs = Math.max(10, ...buckets.map((b) => b.p95Ms || 0));
  const stepX = buckets.length > 1 ? (w - 12) / (buckets.length - 1) : 0;
  const points = buckets
    .map((b, idx) => {
      const x = 6 + idx * stepX;
      const y = 6 + (1 - Math.min(1, (b.p95Ms || 0) / maxMs)) * (h - 12);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label="P95 latency trend" className="overflow-visible">
      <polyline fill="none" stroke="var(--accent)" strokeWidth="1.75" points={points} />
    </svg>
  );
}

function EvalSparkline({ runs }: { runs: EvalRunItem[] }) {
  const pts = [...runs].reverse();
  if (pts.length === 0) return null;
  const w = Math.max(180, pts.length * 26);
  const h = 42;
  const stepX = pts.length > 1 ? (w - 16) / (pts.length - 1) : 0;
  const coords = pts.map((r, idx) => {
    const rawScore = r.min_score ?? r.minScore;
    const score = typeof rawScore === "number" ? rawScore : 1;
    const rawId = r.run_id ?? r.runId ?? "";
    const label = r.run_name ?? r.runName ?? (rawId ? rawId.slice(0, 8) : `run-${idx + 1}`);
    const x = 8 + idx * stepX;
    const y = 8 + (1 - Math.max(0, Math.min(1, score))) * (h - 16);
    return { x, y, score, name: label };
  });
  const polyline = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label="Eval trend" className="overflow-visible">
      <polyline fill="none" stroke="var(--accent)" strokeWidth="1.75" points={polyline} />
      {coords.map((c, idx) => (
        <circle
          key={idx}
          cx={c.x}
          cy={c.y}
          r={3.5}
          fill={c.score >= 1 ? "var(--ok)" : "var(--err)"}
        >
          <title>{`${c.name}: min=${c.score}`}</title>
        </circle>
      ))}
    </svg>
  );
}

export function OverviewView({
  auth,
  health,
  ready,
  watchdog,
  evalHistory,
  profileCounts,
  onOpenPlaygroundServer,
  onProbeUpstream,
  onNavigateTraces,
  onAfterAction,
}: {
  auth: AuthState;
  health: HealthResponse | null;
  ready: ReadyResponse | null;
  watchdog: WatchdogResponse | null;
  evalHistory: EvalRunItem[];
  profileCounts: Record<string, number>;
  onOpenPlaygroundServer: (slug: string) => void;
  onProbeUpstream: (slug: string) => Promise<void>;
  onNavigateTraces: () => void;
  onAfterAction: () => Promise<void>;
}) {
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionOut, setActionOut] = useState<string | null>(null);
  const [withJudge, setWithJudge] = useState(false);
  const [judgeModel, setJudgeModel] = useState("gateway:/mcp-workshop-judge-v1");
  const [probingSlug, setProbingSlug] = useState<string | null>(null);
  const [metricsSeries, setMetricsSeries] = useState<OpsMetricsSeriesResponse | null>(null);
  const [secretsHealth, setSecretsHealth] = useState<SecretsHealthResponse | null>(null);
  const [reprobingAuth, setReprobingAuth] = useState(false);

  useEffect(() => {
    if (!auth.authenticated && auth.authEnabled) return;
    let active = true;
    api
      .opsMetricsSeries()
      .then((res) => {
        if (active) setMetricsSeries(res);
      })
      .catch(() => {});
    api
      .secretsHealth()
      .then((res) => {
        if (active) setSecretsHealth(res);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [auth.authenticated, auth.authEnabled, health?.timestamp]);

  const mlflowUiUrl = resolveMlflowUiUrl(health?.mlflowUiUrl);
  const gatewayBaseUrl = resolveGatewayBaseUrl();

  const servers: ServerInventoryItem[] = health?.servers || [];
  const connectedCount = servers.filter((s) =>
    ["connected", "configured", "enabled"].includes((s.connectionStatus || s.status || "").toLowerCase()),
  ).length;
  const authReqCount = servers.filter(
    (s) => (s.connectionStatus || "").toLowerCase() === "auth_required",
  ).length;
  const downCount = servers.filter(
    (s) => (s.connectionStatus || "").toLowerCase() === "unreachable",
  ).length;
  const reg = watchdog?.evalRegression ?? watchdog?.eval_regression;
  const isRegression = reg?.status === "regression";
  const latestScore = reg?.min_score ?? evalHistory[0]?.min_score ?? evalHistory[0]?.minScore ?? null;
  const latestRunId = reg?.run_id ?? evalHistory[0]?.run_id ?? evalHistory[0]?.runId ?? null;
  const mlflowBenchmarkUrl = buildMlflowExperimentUrl(
    mlflowUiUrl,
    health?.mlflowExperimentId ?? null,
    { section: "runs", runId: latestRunId },
  );
  const wdOverall =
    watchdog?.overall ||
    (watchdog?.components && Object.keys(watchdog.components).length > 0
      ? Object.values(watchdog.components).every((c) => c.healthy !== false)
        ? "healthy"
        : "degraded"
      : "unknown");

  async function runOp(label: string, fn: () => Promise<unknown>) {
    setActionBusy(label);
    try {
      const res = await fn();
      setActionOut(JSON.stringify(res, null, 2));
      await onAfterAction();
    } catch (err) {
      setActionOut(err instanceof Error ? err.message : String(err));
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      {isRegression && (
        <div className="rounded-xl border border-[color-mix(in_srgb,var(--err)_40%,transparent)] bg-[var(--err-soft)] p-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-[var(--err)] shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-semibold text-[13.5px]">Eval Regression Detected</div>
              <div className="text-[12.5px] text-[var(--text-secondary)]">
                Run <code className="font-mono">{reg?.run_id || "n/a"}</code> fell below threshold{" "}
                <span className="font-mono tabular-nums">{reg?.threshold ?? 1}</span>.
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={actionBusy !== null}
              onClick={() => runOp("benchmark", () => api.runBenchmark(withJudge, judgeModel))}
              className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
            >
              Re-run Golden Benchmark
            </button>
            <button
              type="button"
              onClick={onNavigateTraces}
              className="px-3 py-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-[12px] cursor-pointer"
            >
              Inspect Traces
            </button>
          </div>
        </div>
      )}

      {/* KPI Strip */}
      <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2">
          <div className="text-[12px] text-[var(--text-secondary)]">Gateway Readiness</div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xl font-semibold tracking-tight tabular-nums">
              v{health?.version || "—"}
            </span>
            <StatusBadge
              label={(ready?.status || "checking").toUpperCase()}
              tone={ready?.status === "ready" ? "ok" : "warn"}
            />
          </div>
          <div className="text-[11.5px] font-mono text-[var(--text-muted)]">
            {Object.keys(ready?.checks || {}).length} core dependencies checked
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2">
          <div className="text-[12px] text-[var(--text-secondary)]">Mounted Servers & Upstreams</div>
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-semibold tracking-tight tabular-nums">
              {connectedCount}
            </span>
            <span className="text-[12.5px] text-[var(--text-muted)] tabular-nums">
              / {servers.length} configured
            </span>
          </div>
          <div className="text-[11.5px] text-[var(--text-muted)]">
            {servers.filter((s) => s.external).length} external ·{" "}
            {authReqCount > 0 ? (
              <span className="text-[var(--warn)]">{authReqCount} auth needed</span>
            ) : downCount > 0 ? (
              <span className="text-[var(--err)]">{downCount} unreachable</span>
            ) : (
              <span>/mcp active</span>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2">
          <div className="text-[12px] text-[var(--text-secondary)]">Curated Agent Profiles</div>
          <div className="text-xl font-semibold tracking-tight tabular-nums">
            {(health?.profiles || []).length}
          </div>
          <div className="text-[11.5px] font-mono text-[var(--text-muted)] truncate">
            default: {health?.defaultProfile || "core"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[12px] text-[var(--text-secondary)]">Golden Benchmark</span>
            <a
              href={mlflowBenchmarkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-[var(--accent)] hover:underline"
            >
              MLflow <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xl font-semibold tracking-tight tabular-nums">
              {latestScore !== null ? latestScore.toFixed(2) : "—"}
            </span>
            <EvalSparkline runs={evalHistory.slice(0, 8)} />
          </div>
        </div>
      </section>

      {/* Dependencies & Profiles */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[13.5px] font-semibold m-0">Dependencies & Watchdog</h2>
            <StatusBadge
              label={wdOverall}
              tone={connectionTone(wdOverall)}
            />
          </div>
          <div className="divide-y divide-[var(--border-hairline)]">
            {Object.entries(ready?.checks || {}).map(([name, info]) => {
              const ok = Boolean(info.healthy ?? info.reachable);
              return (
                <div key={name} className="py-2 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-[12.5px] text-[var(--text-primary)]">{name}</div>
                    {info.url && (
                      <div className="font-mono text-[11px] text-[var(--text-muted)] truncate">
                        {info.url}
                      </div>
                    )}
                  </div>
                  <StatusBadge label={ok ? "ok" : "down"} tone={ok ? "ok" : "err"} />
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[13.5px] font-semibold m-0">Curated Profiles</h2>
            <CopyButton text={`${gatewayBaseUrl}/mcp`} label="Copy /mcp" compact />
          </div>
          <div className="divide-y divide-[var(--border-hairline)]">
            {(health?.profiles || []).map((prof) => {
              const toolTotal = profileCounts[prof.name];
              return (
                <div key={prof.name} className="py-2 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-medium text-[12.5px]">{prof.name}</span>
                      {typeof toolTotal === "number" && (
                        <span className="text-[11px] font-mono tabular-nums text-[var(--text-muted)]">
                          {toolTotal} tools
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-[11px] text-[var(--text-muted)] truncate">
                      {prof.servers.join(", ")}
                    </div>
                  </div>
                  <CopyButton text={`${gatewayBaseUrl}${prof.route}`} label={prof.route} compact />
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Operational Actions */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="text-[13.5px] font-semibold m-0">Operational Actions</h2>
          {!auth.authenticated && auth.authEnabled && (
            <span className="text-[12px] text-[var(--text-muted)]">
              Sign in to run gateway actions.
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            disabled={actionBusy !== null || !auth.authenticated}
            onClick={() => runOp("uc", api.runUcRefresh)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] disabled:opacity-50 text-[12.5px] cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh UC Tools
          </button>
          <button
            type="button"
            disabled={actionBusy !== null || !auth.authenticated}
            onClick={() => runOp("wd", () => api.runWatchdog(true))}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] disabled:opacity-50 text-[12.5px] cursor-pointer"
          >
            <Activity className="w-3.5 h-3.5" />
            Watchdog Check
          </button>
          <button
            type="button"
            disabled={actionBusy !== null || !auth.authenticated}
            onClick={() => runOp("eval", () => api.runTraceEval(20))}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] disabled:opacity-50 text-[12.5px] cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Trace Eval (Last 20)
          </button>
          <button
            type="button"
            disabled={actionBusy !== null || !auth.authenticated}
            onClick={() => runOp("bench", () => api.runBenchmark(withJudge, judgeModel))}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12.5px] font-semibold cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            {actionBusy === "bench" ? "Benchmarking..." : "Run Golden Benchmark"}
          </button>

          <label className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)] ml-1 cursor-pointer">
            <input
              type="checkbox"
              checked={withJudge}
              onChange={(e) => setWithJudge(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            Ollama judge
          </label>
          <input
            type="text"
            aria-label="Ollama judge model"
            value={judgeModel}
            onChange={(e) => setJudgeModel(e.target.value)}
            className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1 font-mono text-[12px] w-44"
          />
        </div>
        {actionOut && (
          <pre className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words max-h-64 overflow-auto">
            {actionOut}
          </pre>
        )}
      </section>

      {/* Ops Telemetry & 1Password Health */}
      {(secretsHealth || metricsSeries) && (
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[13.5px] font-semibold">
                <KeyRound className="w-4 h-4 text-[var(--accent)]" />
                1Password & Secrets Health
              </div>
              <StatusBadge
                label={secretsHealth?.mode || "env"}
                tone={
                  secretsHealth?.lastErrorCode
                    ? "warn"
                    : secretsHealth?.onepasswordEnabled
                      ? "ok"
                      : "neutral"
                }
              />
            </div>
            {secretsHealth && (
              <div className="text-[12px] text-[var(--text-secondary)] space-y-1">
                <div className="font-mono text-[11.5px]">
                  serviceAccount={String(secretsHealth.serviceAccountConfigured)} · cli=
                  {secretsHealth.cliAvailable ? "ready" : "missing"} · cache=
                  {secretsHealth.cacheEntries}
                </div>
                {secretsHealth.lastError && (
                  <div className="text-[var(--warn)] break-words">
                    {secretsHealth.lastErrorCode ? `[${secretsHealth.lastErrorCode}] ` : ""}
                    {secretsHealth.lastError}
                  </div>
                )}
                {secretsHealth.authRequiredUpstreams.length > 0 && (
                  <div className="pt-1 flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-[var(--warn)]">
                      {secretsHealth.authRequiredUpstreams.length} auth_required upstream(s):{" "}
                      {secretsHealth.authRequiredUpstreams.map((u) => u.slug).join(", ")}
                    </span>
                    <button
                      type="button"
                      disabled={reprobingAuth}
                      onClick={async () => {
                        setReprobingAuth(true);
                        try {
                          await api.reprobeAuthRequired();
                          await onAfterAction();
                        } finally {
                          setReprobingAuth(false);
                        }
                      }}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[11.5px] cursor-pointer"
                    >
                      <RefreshCw className={`w-3 h-3 ${reprobingAuth ? "animate-spin" : ""}`} />
                      {reprobingAuth ? "Re-probing..." : "Re-probe auth_required"}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[13.5px] font-semibold">Gateway Latency & Errors</div>
              <span className="font-mono text-[11px] text-[var(--text-muted)]">
                {metricsSeries?.totalRecorded ?? 0} tool calls
              </span>
            </div>
            <LatencySparkline buckets={metricsSeries?.buckets || []} />
            {metricsSeries && metricsSeries.buckets.length > 0 && (
              <div className="flex items-center gap-4 text-[11.5px] font-mono text-[var(--text-secondary)]">
                <span>
                  Latest P50: {metricsSeries.buckets[metricsSeries.buckets.length - 1].p50Ms} ms
                </span>
                <span>
                  P95: {metricsSeries.buckets[metricsSeries.buckets.length - 1].p95Ms} ms
                </span>
                <span>
                  Err:{" "}
                  {(
                    metricsSeries.buckets[metricsSeries.buckets.length - 1].errorRate * 100
                  ).toFixed(1)}
                  %
                </span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Mounted Servers & Upstreams */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold m-0">
            Mounted Servers & External Upstreams
          </h2>
          <span className="text-[12px] font-mono tabular-nums text-[var(--text-muted)]">
            {servers.length} total
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3.5">
          {servers.map((srv) => {
            const st = srv.connectionStatus || srv.status || "unknown";
            return (
              <div
                key={srv.slug}
                className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 flex flex-col justify-between gap-3 hover:border-[var(--border-strong)] transition-colors"
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono font-semibold text-[13.5px] whitespace-nowrap">
                          {srv.slug}
                        </span>
                        {srv.external && (
                          <span className="px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[10.5px] font-mono text-[var(--text-secondary)]">
                            {srv.transport || "external"}
                          </span>
                        )}
                      </div>
                      <div className="font-mono text-[11px] text-[var(--text-muted)] truncate mt-0.5">
                        {srv.route}
                      </div>
                    </div>
                    <StatusBadge label={st} tone={connectionTone(st)} />
                  </div>

                  {srv.description && (
                    <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed line-clamp-2 m-0">
                      {srv.description}
                    </p>
                  )}

                  {srv.detail && st !== "connected" && (
                    <div className="text-[11.5px] text-[var(--warn)] break-words">
                      {srv.detail}
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between gap-2 pt-2 border-t border-[var(--border-hairline)]">
                  <span className="text-[11.5px] font-mono tabular-nums text-[var(--text-muted)]">
                    {typeof srv.toolCount === "number" ? `${srv.toolCount} tools` : srv.governance || "built-in"}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {srv.external && srv.slug !== "mlflow-upstream" && (
                      <button
                        type="button"
                        disabled={probingSlug === srv.slug}
                        onClick={async () => {
                          setProbingSlug(srv.slug);
                          try {
                            await onProbeUpstream(srv.slug);
                          } finally {
                            setProbingSlug(null);
                          }
                        }}
                        className="px-2 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[11.5px] cursor-pointer"
                      >
                        {probingSlug === srv.slug ? "Probing..." : "Probe"}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => onOpenPlaygroundServer(srv.slug)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] hover:text-[var(--accent)] text-[11.5px] font-medium cursor-pointer"
                    >
                      <Terminal className="w-3 h-3" />
                      Playground
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
