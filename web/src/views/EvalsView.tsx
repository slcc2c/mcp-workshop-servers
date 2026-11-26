import { useCallback, useEffect, useState } from "react";
import { Database, FlaskConical, GitCompare, Play, Plus, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type {
  EvalDatasetDetailResponse,
  EvalDatasetSummary,
  EvalRunCompareResponse,
  EvalRunDetailResponse,
  EvalRunItem,
  ProfileInventoryItem,
} from "../types";
import { StatusBadge } from "../components/StatusDot";

function formatScore(val: unknown): string {
  return typeof val === "number" ? val.toFixed(2) : "—";
}

export function EvalsView({
  profiles,
  onInspectTrace,
  onAfterRun,
}: {
  profiles: ProfileInventoryItem[];
  onInspectTrace: (traceId: string) => void;
  onAfterRun: () => Promise<void>;
}) {
  const [datasets, setDatasets] = useState<EvalDatasetSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [datasetDetail, setDatasetDetail] = useState<EvalDatasetDetailResponse | null>(null);
  const [runs, setRuns] = useState<EvalRunItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [runDetail, setRunDetail] = useState<EvalRunDetailResponse | null>(null);
  const [compareA, setCompareA] = useState<string>("");
  const [compareB, setCompareB] = useState<string>("");
  const [comparison, setComparison] = useState<EvalRunCompareResponse | null>(null);

  // Add record state
  const [inputsJson, setInputsJson] = useState('{"question": "Check gateway readiness"}');
  const [expectationsJson, setExpectationsJson] = useState('{"expected_response": "ready"}');

  // Run eval modal/panel state
  const [showLauncher, setShowLauncher] = useState(false);
  const [evalMode, setEvalMode] = useState<"golden" | "traces" | "agent">("golden");
  const [withJudge, setWithJudge] = useState(false);
  const [judgeModel, setJudgeModel] = useState("typesafe:/");
  const [evalProfile, setEvalProfile] = useState("core");
  const [evalDatasetName, setEvalDatasetName] = useState("");
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dsRes, runRes] = await Promise.all([api.evalDatasets(), api.evalRuns(30)]);
      const dsList = dsRes.datasets || [];
      const runList = runRes.runs || [];
      setDatasets(dsList);
      setRuns(runList);
      if (!selectedDatasetId && dsList[0]?.datasetId) {
        setSelectedDatasetId(dsList[0].datasetId);
      }
      if (!selectedRunId && runList[0]?.run_id) {
        setSelectedRunId(runList[0].run_id);
      }
      if (!compareA && runList[1]?.run_id) setCompareA(runList[1].run_id);
      if (!compareB && runList[0]?.run_id) setCompareB(runList[0].run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [selectedDatasetId, selectedRunId, compareA, compareB]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!selectedDatasetId) return;
    api
      .evalDatasetDetail(selectedDatasetId)
      .then(setDatasetDetail)
      .catch(() => {});
  }, [selectedDatasetId]);

  useEffect(() => {
    if (!selectedRunId) return;
    api
      .evalRunDetail(selectedRunId)
      .then(setRunDetail)
      .catch(() => {});
  }, [selectedRunId]);

  const handleAddRecord = async () => {
    if (!selectedDatasetId) return;
    setError(null);
    try {
      const parsedInputs = JSON.parse(inputsJson) as Record<string, unknown>;
      const parsedExp = expectationsJson.trim()
        ? (JSON.parse(expectationsJson) as Record<string, unknown>)
        : undefined;
      await api.addEvalDatasetRecords(selectedDatasetId, [
        { inputs: parsedInputs, ...(parsedExp ? { expectations: parsedExp } : {}) },
      ]);
      const refreshed = await api.evalDatasetDetail(selectedDatasetId);
      setDatasetDetail(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCompare = async () => {
    if (!compareA || !compareB) return;
    setError(null);
    try {
      const res = await api.evalCompare(compareA, compareB);
      setComparison(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRunEval = async () => {
    setRunning(true);
    setError(null);
    try {
      const isTypeSafe = judgeModel.trim().startsWith("typesafe:/");
      await api.runEval({
        mode: evalMode,
        with_llm_judge: withJudge,
        ...(withJudge ? { judge_model: judgeModel.trim() } : {}),
        ...(withJudge && isTypeSafe ? { model_api: "decisions" } : {}),
        ...(evalDatasetName.trim() ? { dataset_name: evalDatasetName.trim() } : {}),
        ...(evalMode === "agent" ? { profile: evalProfile } : {}),
      });
      setShowLauncher(false);
      await loadAll();
      await onAfterRun();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-[var(--accent)]" />
          <h2 className="text-[15px] font-semibold m-0">Evaluations & Datasets Workbench</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => loadAll()}
            disabled={loading}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[12px] cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setShowLauncher((v) => !v)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 text-white text-[12px] font-semibold cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            Run Evaluation
          </button>
        </div>
      </div>

      {showLauncher && (
        <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5">
            <label className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
              <span>Mode</span>
              <select
                aria-label="Evaluation mode"
                value={evalMode}
                onChange={(e) => setEvalMode(e.target.value as "golden" | "traces" | "agent")}
                className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px]"
              >
                <option value="golden">Golden Benchmark</option>
                <option value="traces">Trace Evaluation</option>
                <option value="agent">Agent Server Eval</option>
              </select>
            </label>

            <label className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
              <span>Dataset Name (optional)</span>
              <input
                type="text"
                value={evalDatasetName}
                onChange={(e) => setEvalDatasetName(e.target.value)}
                placeholder="Default dataset"
                className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] font-mono"
              />
            </label>

            {evalMode === "agent" && (
              <label className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
                <span>Agent Profile</span>
                <select
                  value={evalProfile}
                  onChange={(e) => setEvalProfile(e.target.value)}
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] font-mono"
                >
                  {(profiles.length > 0 ? profiles.map((p) => p.name) : ["core", "discover"]).map(
                    (name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ),
                  )}
                </select>
              </label>
            )}

            <div className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
              <label className="inline-flex items-center gap-1.5 cursor-pointer pt-5">
                <input
                  type="checkbox"
                  checked={withJudge}
                  onChange={(e) => setWithJudge(e.target.checked)}
                />
                Enable LLM / TypeSafe Judge
              </label>
            </div>
          </div>

          {withJudge && (
            <div className="flex items-center gap-2 flex-wrap">
              <input
                type="text"
                aria-label="Judge model URI"
                value={judgeModel}
                onChange={(e) => setJudgeModel(e.target.value)}
                placeholder="typesafe:/ or openai:/gpt-4o-mini"
                className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12px] font-mono min-w-[260px]"
              />
              <button
                type="button"
                onClick={() => setJudgeModel("typesafe:/")}
                className="px-2 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-subtle)] text-[11px] font-mono cursor-pointer"
              >
                typesafe:/
              </button>
              <button
                type="button"
                onClick={() => setJudgeModel("openai:/gpt-4o-mini")}
                className="px-2 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-subtle)] text-[11px] font-mono cursor-pointer"
              >
                openai:/gpt-4o-mini
              </button>
              {judgeModel.startsWith("typesafe:/") && (
                <StatusBadge label="model_api=decisions" tone="accent" />
              )}
            </div>
          )}

          <button
            type="button"
            onClick={handleRunEval}
            disabled={running}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12.5px] font-semibold cursor-pointer"
          >
            <Play className="w-3.5 h-3.5" />
            {running ? "Running..." : "Launch Evaluation"}
          </button>
        </section>
      )}

      {error && (
        <div className="rounded-lg bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Datasets */}
        <section className="lg:col-span-5 rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
          <div className="flex items-center gap-2 text-[13.5px] font-semibold">
            <Database className="w-4 h-4 text-[var(--accent)]" />
            MLflow Datasets ({datasets.length})
          </div>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {datasets.length === 0 ? (
              <div className="text-[12px] text-[var(--text-muted)]">No GenAI datasets found.</div>
            ) : (
              datasets.map((ds) => (
                <button
                  key={ds.datasetId}
                  type="button"
                  onClick={() => setSelectedDatasetId(ds.datasetId)}
                  className={`w-full text-left rounded-lg border px-3 py-2 cursor-pointer ${
                    selectedDatasetId === ds.datasetId
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                      : "border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[12px] font-semibold">{ds.name}</span>
                    {typeof ds.recordCount === "number" && (
                      <StatusBadge label={`${ds.recordCount} rows`} tone="neutral" />
                    )}
                  </div>
                </button>
              ))
            )}
          </div>

          {datasetDetail && (
            <div className="space-y-2 border-t border-[var(--border-hairline)] pt-2.5">
              <div className="text-[12px] font-semibold">
                Records ({datasetDetail.records.length})
              </div>
              <div className="max-h-40 overflow-y-auto space-y-1.5">
                {datasetDetail.records.slice(0, 10).map((rec, idx) => (
                  <div
                    key={rec.datasetRecordId || idx}
                    className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] p-2 text-[11px] font-mono"
                  >
                    {JSON.stringify(rec.inputs)}
                  </div>
                ))}
              </div>
              <div className="space-y-1.5 pt-1">
                <textarea
                  rows={2}
                  aria-label="Dataset record inputs JSON"
                  value={inputsJson}
                  onChange={(e) => setInputsJson(e.target.value)}
                  className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 text-[11px] font-mono"
                />
                <textarea
                  rows={2}
                  aria-label="Dataset record expectations JSON"
                  value={expectationsJson}
                  onChange={(e) => setExpectationsJson(e.target.value)}
                  className="w-full rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 text-[11px] font-mono"
                />
                <button
                  type="button"
                  onClick={handleAddRecord}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[11.5px] cursor-pointer"
                >
                  <Plus className="w-3 h-3" />
                  Add Record
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Runs & Comparison */}
        <section className="lg:col-span-7 rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-[13.5px] font-semibold">Evaluation Runs ({runs.length})</div>
            <div className="flex items-center gap-1.5 flex-wrap">
              <select
                aria-label="Baseline run"
                value={compareA}
                onChange={(e) => setCompareA(e.target.value)}
                className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 text-[11px] font-mono max-w-[130px]"
              >
                <option value="">Baseline A</option>
                {runs.map((r) => {
                  const rid = r.run_id || r.runId || "";
                  return (
                    <option key={rid} value={rid}>
                      {r.run_name || r.runName || rid.slice(0, 8)}
                    </option>
                  );
                })}
              </select>
              <select
                aria-label="Candidate run"
                value={compareB}
                onChange={(e) => setCompareB(e.target.value)}
                className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 text-[11px] font-mono max-w-[130px]"
              >
                <option value="">Candidate B</option>
                {runs.map((r) => {
                  const rid = r.run_id || r.runId || "";
                  return (
                    <option key={rid} value={rid}>
                      {r.run_name || r.runName || rid.slice(0, 8)}
                    </option>
                  );
                })}
              </select>
              <button
                type="button"
                onClick={handleCompare}
                disabled={!compareA || !compareB}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] disabled:opacity-50 text-[11.5px] cursor-pointer"
              >
                <GitCompare className="w-3.5 h-3.5" />
                Compare
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {runs.slice(0, 12).map((r) => {
              const rid = r.run_id || r.runId || "";
              return (
                <button
                  key={rid}
                  type="button"
                  onClick={() => setSelectedRunId(rid)}
                  className={`px-2.5 py-1 rounded-lg border text-[11.5px] font-mono cursor-pointer ${
                    selectedRunId === rid
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "border-[var(--border-hairline)] bg-[var(--bg-elevated)]"
                  }`}
                >
                  {r.run_name || r.runName || rid.slice(0, 8)} · min {formatScore(r.min_score ?? r.minScore)}
                </button>
              );
            })}
          </div>

          {comparison && (
            <div
              data-testid="eval-compare-deltas"
              className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3 space-y-2"
            >
              <div className="text-[12px] font-semibold">
                Comparison: {comparison.runA.runName || comparison.runA.runId} vs{" "}
                {comparison.runB.runName || comparison.runB.runId}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11.5px] font-mono">
                  <thead>
                    <tr className="border-b border-[var(--border-hairline)] text-[var(--text-muted)]">
                      <th className="py-1 pr-2">Metric</th>
                      <th className="py-1 pr-2">Baseline</th>
                      <th className="py-1 pr-2">Candidate</th>
                      <th className="py-1">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.deltas.map((d) => (
                      <tr key={d.metric} className="border-b border-[var(--border-hairline)]/50">
                        <td className="py-1 pr-2">{d.metric}</td>
                        <td className="py-1 pr-2">{formatScore(d.baseline)}</td>
                        <td className="py-1 pr-2">{formatScore(d.candidate)}</td>
                        <td
                          className={`py-1 ${
                            typeof d.delta === "number" && d.delta > 0
                              ? "text-[var(--ok)]"
                              : typeof d.delta === "number" && d.delta < 0
                                ? "text-[var(--err)]"
                                : "text-[var(--text-muted)]"
                          }`}
                        >
                          {typeof d.delta === "number"
                            ? `${d.delta >= 0 ? "+" : ""}${d.delta.toFixed(2)}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {runDetail && (
            <div className="space-y-2.5 border-t border-[var(--border-hairline)] pt-2.5">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="font-mono text-[12.5px] font-semibold">
                  {runDetail.runName || runDetail.runId}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(runDetail.metrics || {})
                    .slice(0, 6)
                    .map(([k, v]) => (
                      <StatusBadge key={k} label={`${k}: ${v.toFixed(2)}`} tone="neutral" />
                    ))}
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11.5px] border-collapse">
                  <thead>
                    <tr className="border-b border-[var(--border-hairline)] text-[var(--text-muted)]">
                      <th className="py-1.5 pr-2">Status</th>
                      <th className="py-1.5 pr-2">TypeSafe p</th>
                      <th className="py-1.5 pr-2">Request</th>
                      <th className="py-1.5">Trace</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(runDetail.rows || []).map((row, idx) => (
                      <tr
                        key={row.evalId || row.traceId || idx}
                        className="border-b border-[var(--border-hairline)]/50"
                      >
                        <td className="py-1.5 pr-2">
                          <StatusBadge
                            label={row.passed === false ? "fail" : row.passed === true ? "pass" : "eval"}
                            tone={row.passed === false ? "err" : row.passed === true ? "ok" : "neutral"}
                          />
                        </td>
                        <td className="py-1.5 pr-2 font-mono">
                          {typeof row.typesafeProbability === "number" ? (
                            <StatusBadge
                              label={`p=${row.typesafeProbability.toFixed(2)}`}
                              tone={row.typesafeProbability >= 0.8 ? "ok" : "warn"}
                            />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-1.5 pr-2 max-w-[260px] truncate text-[var(--text-secondary)]">
                          {row.request || row.response || "—"}
                        </td>
                        <td className="py-1.5 font-mono">
                          {row.traceId ? (
                            <button
                              type="button"
                              onClick={() => onInspectTrace(row.traceId!)}
                              className="text-[var(--accent)] hover:underline cursor-pointer"
                            >
                              {row.traceId.slice(0, 12)}
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
