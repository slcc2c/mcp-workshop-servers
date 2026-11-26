import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Copy, Edit3, Eye, GitCompare, Plus, Sparkles, X } from "lucide-react";
import { api } from "../lib/api";
import { extractPromptVariables, renderPromptTemplate } from "../lib/format";
import type { PromptDetailResponse, RegistryPromptItem } from "../types";
import { CopyButton } from "./CopyButton";
import { PromptDiffView } from "./PromptDiffView";
import { PromptRenderer } from "./PromptRenderer";
import { StatusBadge } from "./StatusDot";

type PromptSubMode = "template" | "preview" | "diff";

export function PromptWorkbench({
  promptSummary,
  selectedVersion,
  onSelectVersion,
  mutationsEnabled,
  mlflowUiBase,
  onStartNewVersion,
  onMutated,
}: {
  promptSummary: RegistryPromptItem | null;
  selectedVersion?: string | null;
  onSelectVersion?: (ver: string) => void;
  mutationsEnabled: boolean;
  mlflowUiBase: string;
  onStartNewVersion: (name: string, template: string) => void;
  onMutated: () => Promise<void>;
}) {
  const [mode, setMode] = useState<PromptSubMode>("template");
  const [detail, setDetail] = useState<PromptDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const versionCacheRef = useRef<Record<string, PromptDetailResponse>>({});

  // Live variable preview state keyed by prompt name -> { varName: val }
  const [varValuesByPrompt, setVarValuesByPrompt] = useState<Record<string, Record<string, string>>>(
    {},
  );
  const [showMcpPayload, setShowMcpPayload] = useState(false);

  // Diff state
  const [diffBaseVer, setDiffBaseVer] = useState<string>("");
  const [diffTargetVer, setDiffTargetVer] = useState<string>("");
  const [diffBaseDetail, setDiffBaseDetail] = useState<PromptDetailResponse | null>(null);
  const [diffTargetDetail, setDiffTargetDetail] = useState<PromptDetailResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  // Alias form state
  const [customAlias, setCustomAlias] = useState("");
  const [aliasBusy, setAliasBusy] = useState(false);

  const versions = useMemo(() => promptSummary?.versions || [], [promptSummary]);
  const activeVersionStr = useMemo(() => {
    if (!promptSummary) return "latest";
    if (selectedVersion && versions.some((v) => String(v.version) === String(selectedVersion))) {
      return String(selectedVersion);
    }
    return versions[0]?.version !== undefined ? String(versions[0].version) : "latest";
  }, [promptSummary, selectedVersion, versions]);

  const activeVersionMeta = useMemo(
    () => versions.find((v) => String(v.version) === activeVersionStr) || null,
    [versions, activeVersionStr],
  );

  // Fetch active prompt version detail
  useEffect(() => {
    if (!promptSummary) {
      setDetail(null);
      return;
    }
    const cacheKey = `${promptSummary.name}::${activeVersionStr}`;
    const cached = versionCacheRef.current[cacheKey];
    if (cached) {
      setDetail(cached);
    }
    let cancelled = false;
    setLoading(!cached);
    setStatusMsg(null);
    api
      .promptDetail(promptSummary.name, activeVersionStr)
      .then((res) => {
        if (cancelled) return;
        versionCacheRef.current[cacheKey] = res;
        setDetail(res);
      })
      .catch((e) => {
        if (!cancelled) setStatusMsg(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [promptSummary, activeVersionStr]);

  // Default diff versions whenever prompt/active version changes
  useEffect(() => {
    if (!promptSummary || versions.length === 0) return;
    const currentIdx = versions.findIndex((v) => String(v.version) === activeVersionStr);
    const targetVer = String(versions[Math.max(0, currentIdx)]?.version ?? activeVersionStr);
    const baseCandidate =
      versions[currentIdx + 1]?.version ?? versions[versions.length - 1]?.version ?? targetVer;
    setDiffTargetVer(targetVer);
    setDiffBaseVer(String(baseCandidate));
  }, [promptSummary, versions, activeVersionStr]);

  // Fetch diff versions when in Diff mode
  useEffect(() => {
    if (mode !== "diff" || !promptSummary || !diffBaseVer || !diffTargetVer) return;
    let cancelled = false;
    async function loadPair() {
      if (!promptSummary) return;
      const getVer = async (ver: string) => {
        const key = `${promptSummary.name}::${ver}`;
        if (versionCacheRef.current[key]) return versionCacheRef.current[key];
        const fetched = await api.promptDetail(promptSummary.name, ver);
        versionCacheRef.current[key] = fetched;
        return fetched;
      };
      setDiffLoading(true);
      try {
        const [b, t] = await Promise.all([getVer(diffBaseVer), getVer(diffTargetVer)]);
        if (!cancelled) {
          setDiffBaseDetail(b);
          setDiffTargetDetail(t);
        }
      } catch (e) {
        if (!cancelled) setStatusMsg(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setDiffLoading(false);
      }
    }
    loadPair();
    return () => {
      cancelled = true;
    };
  }, [mode, promptSummary, diffBaseVer, diffTargetVer]);

  const templateVars = useMemo(
    () => (detail?.template ? extractPromptVariables(detail.template) : []),
    [detail?.template],
  );
  const currentVarValues = useMemo(
    () => (promptSummary ? varValuesByPrompt[promptSummary.name] || {} : {}),
    [promptSummary, varValuesByPrompt],
  );
  const renderedPreview = useMemo(
    () => (detail?.template ? renderPromptTemplate(detail.template, currentVarValues) : ""),
    [detail?.template, currentVarValues],
  );

  async function handleSetAlias(aliasName: string) {
    if (!promptSummary || !detail?.version || !aliasName.trim()) return;
    const cleanAlias = aliasName.trim().replace(/^@+/, "");
    setAliasBusy(true);
    setStatusMsg(null);
    try {
      await api.promotePromptAlias(promptSummary.name, String(detail.version), cleanAlias);
      setStatusMsg(`Set @${cleanAlias} -> v${detail.version}`);
      setCustomAlias("");
      await onMutated();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setAliasBusy(false);
    }
  }

  async function handleDeleteAlias(aliasName: string) {
    if (!promptSummary) return;
    setAliasBusy(true);
    setStatusMsg(null);
    try {
      await api.deletePromptAlias(promptSummary.name, aliasName);
      setStatusMsg(`Removed alias @${aliasName}`);
      await onMutated();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setAliasBusy(false);
    }
  }

  if (!promptSummary) {
    return (
      <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 text-[13px] text-[var(--text-muted)]">
        Select a prompt to inspect versions, test live variable substitution, or compare diffs.
      </div>
    );
  }

  const activeAliases = activeVersionMeta?.aliases || [];

  return (
    <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 space-y-4">
      {/* Header + Mode Switcher */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-mono text-[15px] font-semibold m-0 break-all">
              {promptSummary.name}
            </h3>
            <span className="px-2 py-0.5 rounded-md text-[11px] font-mono font-medium bg-[var(--accent-soft)] text-[var(--accent)]">
              v{activeVersionStr}
            </span>
          </div>
          {promptSummary.description && (
            <p className="text-[12px] text-[var(--text-secondary)] m-0">
              {promptSummary.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-0.5">
            {(
              [
                ["template", "Template", <Copy key="t" className="w-3.5 h-3.5" />],
                ["preview", "Live Preview", <Eye key="p" className="w-3.5 h-3.5" />],
                ["diff", "Diff", <GitCompare key="d" className="w-3.5 h-3.5" />],
              ] as const
            ).map(([id, label, icon]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12px] font-medium cursor-pointer transition-colors ${
                  mode === id
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {icon}
                {label}
              </button>
            ))}
          </div>

          {mutationsEnabled && detail && (
            <button
              type="button"
              onClick={() => onStartNewVersion(promptSummary.name, detail.template)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] text-[12px] cursor-pointer"
            >
              <Edit3 className="w-3.5 h-3.5" />
              Edit as New Version
            </button>
          )}
        </div>
      </div>

      {/* Version Strip */}
      {versions.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            Versions ({versions.length})
          </div>
          <div className="flex items-center gap-1.5 flex-wrap" data-testid="prompt-version-strip">
            {versions.map((v) => {
              const verStr = String(v.version);
              const isSelected = verStr === activeVersionStr;
              const vAliases = v.aliases || [];
              return (
                <button
                  key={verStr}
                  type="button"
                  title={v.commitMessage || undefined}
                  onClick={() => onSelectVersion?.(verStr)}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[12px] font-mono cursor-pointer transition-colors ${
                    isSelected
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)] font-semibold"
                      : "border-[var(--border-hairline)] bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <span>v{verStr}</span>
                  {vAliases.map((al) => (
                    <span
                      key={al}
                      className="px-1.5 py-0.5 rounded bg-[var(--ok-soft)] text-[var(--ok)] text-[10px]"
                    >
                      @{al}
                    </span>
                  ))}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {statusMsg && (
        <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] px-3 py-1.5 text-[12px] text-[var(--accent)]">
          {statusMsg}
        </div>
      )}

      {/* Main Mode Body */}
      {loading && !detail ? (
        <div className="text-[13px] text-[var(--text-muted)] py-4">Loading prompt template...</div>
      ) : !detail ? (
        <div className="text-[13px] text-[var(--text-muted)] py-4">
          Unable to load version details.
        </div>
      ) : mode === "template" ? (
        <div className="space-y-3">
          <PromptRenderer
            template={detail.template}
            title={detail.name}
            version={detail.version}
            commitMessage={detail.commitMessage}
          />
          {detail.tags && Object.keys(detail.tags).length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(detail.tags).map(([k, v]) => (
                <StatusBadge key={k} label={`${k}=${v}`} tone="neutral" />
              ))}
            </div>
          )}
        </div>
      ) : mode === "preview" ? (
        <div className="space-y-4" data-testid="prompt-live-preview">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {templateVars.length === 0 ? (
              <div className="text-[12.5px] text-[var(--text-muted)] sm:col-span-2">
                This prompt template has no {"{{variable}}"} placeholders.
              </div>
            ) : (
              templateVars.map((varName) => (
                <label key={varName} className="block space-y-1">
                  <span className="font-mono text-[11.5px] text-[var(--text-secondary)]">
                    {`{{${varName}}}`}
                  </span>
                  <input
                    type="text"
                    value={currentVarValues[varName] || ""}
                    onChange={(e) =>
                      setVarValuesByPrompt((prev) => ({
                        ...prev,
                        [promptSummary.name]: {
                          ...(prev[promptSummary.name] || {}),
                          [varName]: e.target.value,
                        },
                      }))
                    }
                    placeholder={`Value for ${varName}...`}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 font-mono text-[12px]"
                  />
                </label>
              ))
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[var(--accent)]" />
                Rendered MCP prompts/get Output
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowMcpPayload((v) => !v)}
                  className="px-2 py-0.5 rounded border border-[var(--border-hairline)] text-[11px] text-[var(--text-secondary)] cursor-pointer"
                >
                  {showMcpPayload ? "Hide MCP JSON" : "Show MCP JSON"}
                </button>
                <CopyButton text={renderedPreview} label="Copy Output" compact />
              </div>
            </div>
            <pre
              data-testid="prompt-live-preview-output"
              className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-4 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap break-words m-0"
            >
              {renderedPreview}
            </pre>
            {showMcpPayload && (
              <pre className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words m-0">
                {JSON.stringify(
                  {
                    method: "prompts/get",
                    params: {
                      name: promptSummary.name,
                      arguments: currentVarValues,
                    },
                  },
                  null,
                  2,
                )}
              </pre>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {versions.length < 2 ? (
            <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] px-4 py-5 text-[12.5px] text-[var(--text-muted)]">
              Only one version exists for this prompt. Create a new version to compare changes.
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 flex-wrap text-[12px]">
                <label className="inline-flex items-center gap-1.5">
                  <span className="text-[var(--text-secondary)]">From:</span>
                  <select
                    aria-label="Diff base version"
                    value={diffBaseVer}
                    onChange={(e) => setDiffBaseVer(e.target.value)}
                    className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 font-mono text-[12px]"
                  >
                    {versions.map((v) => (
                      <option key={String(v.version)} value={String(v.version)}>
                        v{String(v.version)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="inline-flex items-center gap-1.5">
                  <span className="text-[var(--text-secondary)]">To:</span>
                  <select
                    aria-label="Diff target version"
                    value={diffTargetVer}
                    onChange={(e) => setDiffTargetVer(e.target.value)}
                    className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 font-mono text-[12px]"
                  >
                    {versions.map((v) => (
                      <option key={String(v.version)} value={String(v.version)}>
                        v{String(v.version)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {diffLoading ? (
                <div className="text-[12.5px] text-[var(--text-muted)] py-4">
                  Loading version diff...
                </div>
              ) : diffBaseDetail && diffTargetDetail ? (
                <PromptDiffView
                  baseLabel={`v${diffBaseVer}`}
                  targetLabel={`v${diffTargetVer}`}
                  baseTemplate={diffBaseDetail.template}
                  targetTemplate={diffTargetDetail.template}
                />
              ) : null}
            </>
          )}
        </div>
      )}

      {/* Flexible Alias Manager & MLflow UI Link */}
      <div className="pt-3 border-t border-[var(--border-hairline)] space-y-2.5">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mr-1">
              Aliases on v{activeVersionStr}:
            </span>
            {activeAliases.length === 0 ? (
              <span className="text-[12px] text-[var(--text-muted)]">None</span>
            ) : (
              activeAliases.map((al) => (
                <span
                  key={al}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-[color-mix(in_srgb,var(--ok)_35%,transparent)] bg-[var(--ok-soft)] text-[var(--ok)] font-mono text-[11px]"
                >
                  @{al}
                  {mutationsEnabled && (
                    <button
                      type="button"
                      disabled={aliasBusy}
                      aria-label={`Remove alias ${al}`}
                      onClick={() => handleDeleteAlias(al)}
                      className="hover:opacity-75 cursor-pointer"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </span>
              ))
            )}
          </div>

          <a
            href={`${mlflowUiBase}/#/prompts/${encodeURIComponent(promptSummary.name)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[12px] text-[var(--accent)] hover:underline"
          >
            Open in MLflow UI <ArrowUpRight className="w-3.5 h-3.5" />
          </a>
        </div>

        {mutationsEnabled && detail?.version && (
          <div className="flex items-center gap-2 flex-wrap">
            {(["production", "staging", "champion"] as const).map((presetAlias) => (
              <button
                key={presetAlias}
                type="button"
                disabled={aliasBusy}
                onClick={() => handleSetAlias(presetAlias)}
                className="px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--ok)] font-mono text-[11.5px] cursor-pointer disabled:opacity-50"
              >
                Set @{presetAlias}
              </button>
            ))}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSetAlias(customAlias);
              }}
              className="inline-flex items-center gap-1.5 ml-auto"
            >
              <input
                type="text"
                value={customAlias}
                onChange={(e) => setCustomAlias(e.target.value)}
                placeholder="custom-alias"
                aria-label="Custom alias name"
                className="w-32 rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2 py-1 font-mono text-[11.5px]"
              />
              <button
                type="submit"
                disabled={aliasBusy || !customAlias.trim()}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-[var(--accent)] text-white text-[11.5px] font-medium disabled:opacity-50 cursor-pointer"
              >
                <Plus className="w-3 h-3" />
                Apply
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
