import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ExternalLink,
  Inbox,
  MessageSquarePlus,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Workflow,
  X,
} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { StatusBadge } from "../components/StatusDot";
import { callOmnigent } from "../lib/omnigentChat";
import type {
  OmnigentInboxResponse,
  OmnigentPendingElicitation,
  OmnigentProject,
  OmnigentSessionDetail,
  OmnigentSessionRow,
  OmnigentStatus,
  OmnigentWorkflow,
} from "../types";

const QUICK_PROMPTS = [
  "Check printer & MLflow health",
  "Review open PRs across repos",
  "Check Linear SPE queue",
];

function sessionTone(status?: string | null): "ok" | "warn" | "err" | "neutral" | "accent" {
  const s = (status || "").toLowerCase();
  if (s === "running" || s === "active") return "accent";
  if (s === "idle" || s === "completed" || s === "ok") return "ok";
  if (s === "failed" || s === "error") return "err";
  return "neutral";
}

function elicitationIdOf(el: OmnigentPendingElicitation, idx: number): string {
  return String(el.elicitation_id || el.data?.elicitation_id || el.id || `elicit-${idx}`);
}

function elicitationPromptOf(el: OmnigentPendingElicitation): string {
  if (typeof el.message === "string" && el.message.trim()) return el.message;
  if (typeof el.data?.message === "string" && el.data.message.trim()) return el.data.message;
  if (typeof el.title === "string" && el.title.trim()) return el.title;
  return JSON.stringify(el);
}

function asArray<T>(val: unknown): T[] {
  return Array.isArray(val) ? (val as T[]) : [];
}

function friendlyErrorBanner(raw: string): string {
  if (raw.includes("SERVER_NOT_FOUND") || raw.includes("Unknown 'omnigent'")) {
    return `${raw} — restart mcp-workshop-gateway (launchctl kickstart -k gui/501/com.spencer.mcp-workshop-gateway) so /servers/omnigent/mcp is active.`;
  }
  return raw;
}

export function ChatView({
  authenticated = true,
  initialSessionId,
  onSelectSessionId,
  onInspectTrace,
}: {
  authenticated?: boolean;
  initialSessionId: string | null;
  onSelectSessionId: (id: string | null) => void;
  onInspectTrace: (traceId: string) => void;
}) {
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);

  const [hubStatus, setHubStatus] = useState<OmnigentStatus | null>(null);
  const [projects, setProjects] = useState<OmnigentProject[]>([]);
  const [workflows, setWorkflows] = useState<OmnigentWorkflow[]>([]);
  const [sessions, setSessions] = useState<OmnigentSessionRow[]>([]);
  const [inbox, setInbox] = useState<OmnigentInboxResponse | null>(null);

  const [projectFilter, setProjectFilter] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(initialSessionId);
  const [activeSession, setActiveSession] = useState<OmnigentSessionDetail | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);

  // New session composer state
  const [newProjectId, setNewProjectId] = useState("");
  const [newWorkflow, setNewWorkflow] = useState("");
  const [newModelOverride, setNewModelOverride] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Follow-up composer state
  const [followUpText, setFollowUpText] = useState("");
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [markingInboxId, setMarkingInboxId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedSessionId(initialSessionId);
  }, [initialSessionId]);

  const loadWorkspace = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    else setRefreshing(true);
    setErrorMsg(null);
    try {
      const [statusRes, projectsRes, workflowsRes, sessionsRes, inboxRes] = await Promise.all([
        callOmnigent<OmnigentStatus>("omnigent_get_status", {}),
        callOmnigent<OmnigentProject[]>("omnigent_list_projects", {}),
        callOmnigent<OmnigentWorkflow[]>("omnigent_list_workflows", {}),
        callOmnigent<OmnigentSessionRow[]>("omnigent_list_sessions", { limit: 30 }),
        callOmnigent<OmnigentInboxResponse>("omnigent_list_inbox", {
          status: "unread",
          limit: 20,
        }),
      ]);
      if (!mountedRef.current) return;
      setHubStatus(statusRes.data);
      setProjects(asArray<OmnigentProject>(projectsRes.data));
      setWorkflows(asArray<OmnigentWorkflow>(workflowsRes.data));
      setSessions(asArray<OmnigentSessionRow>(sessionsRes.data));
      setInbox(
        inboxRes.data && typeof inboxRes.data === "object"
          ? {
              ...inboxRes.data,
              items: asArray(inboxRes.data.items),
            }
          : null,
      );
      setLastTraceId(
        inboxRes.traceId || sessionsRes.traceId || statusRes.traceId || null,
      );
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(friendlyErrorBanner(err instanceof Error ? err.message : String(err)));
    } finally {
      if (mountedRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  const loadSessionDetail = useCallback(async (sessionId: string, quiet = false) => {
    if (!quiet) setSessionLoading(true);
    try {
      const res = await callOmnigent<OmnigentSessionDetail>("omnigent_get_session", {
        session_id: sessionId,
        tail_items: 30,
      });
      if (!mountedRef.current) return;
      setActiveSession(
        res.data && typeof res.data === "object"
          ? {
              ...res.data,
              pendingElicitations: asArray(res.data.pendingElicitations),
              recentMessages: asArray(res.data.recentMessages),
            }
          : null,
      );
      if (res.traceId) setLastTraceId(res.traceId);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(friendlyErrorBanner(err instanceof Error ? err.message : String(err)));
    } finally {
      if (mountedRef.current && !quiet) {
        setSessionLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!authenticated) {
      setLoading(false);
      setErrorMsg(null);
      return;
    }
    void loadWorkspace(true);
  }, [authenticated, loadWorkspace]);

  useEffect(() => {
    if (!authenticated || !selectedSessionId) {
      if (!selectedSessionId) setActiveSession(null);
      return;
    }
    void loadSessionDetail(selectedSessionId);
  }, [authenticated, selectedSessionId, loadSessionDetail]);

  // Poll running session transcript every 3s cleanly until settled
  useEffect(() => {
    if (!selectedSessionId || activeSession?.status?.toLowerCase() !== "running") {
      return;
    }
    const timer = window.setInterval(() => {
      void loadSessionDetail(selectedSessionId, true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selectedSessionId, activeSession?.status, loadSessionDetail]);

  const selectSession = useCallback(
    (sid: string | null) => {
      setSelectedSessionId(sid);
      onSelectSessionId(sid);
      setErrorMsg(null);
    },
    [onSelectSessionId],
  );

  const filteredSessions = useMemo(() => {
    if (!projectFilter) return sessions;
    return sessions.filter((s) => s.projectId === projectFilter);
  }, [sessions, projectFilter]);

  const mutationsEnabled = hubStatus?.mutationsEnabled ?? true;

  const handleStartSession = async () => {
    const prompt = newPrompt.trim();
    if (!prompt && !newWorkflow) return;
    if (!mutationsEnabled) return;

    setSubmitting(true);
    setErrorMsg(null);
    try {
      let createdId: string | undefined;
      let createdTrace: string | null = null;
      if (newWorkflow) {
        const res = await callOmnigent<{ id: string }>("omnigent_run_workflow", {
          workflow: newWorkflow,
          details: prompt,
          ...(newProjectId ? { project: newProjectId } : {}),
          ...(newModelOverride ? { model_override: newModelOverride } : {}),
        });
        createdId = res.data.id;
        createdTrace = res.traceId;
      } else {
        const res = await callOmnigent<{ id: string }>("omnigent_start_session", {
          prompt,
          ...(newProjectId ? { project: newProjectId } : {}),
          ...(newModelOverride ? { model_override: newModelOverride } : {}),
        });
        createdId = res.data.id;
        createdTrace = res.traceId;
      }
      if (!mountedRef.current) return;
      if (createdTrace) setLastTraceId(createdTrace);
      setNewPrompt("");
      if (createdId) {
        selectSession(createdId);
      }
      await loadWorkspace(false);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(friendlyErrorBanner(err instanceof Error ? err.message : String(err)));
    } finally {
      if (mountedRef.current) setSubmitting(false);
    }
  };

  const handleSendFollowUp = async () => {
    const msg = followUpText.trim();
    if (!msg || !selectedSessionId || !mutationsEnabled) return;
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await callOmnigent<Record<string, unknown>>("omnigent_send_message", {
        session_id: selectedSessionId,
        message: msg,
      });
      if (!mountedRef.current) return;
      if (res.traceId) setLastTraceId(res.traceId);
      setFollowUpText("");
      await loadSessionDetail(selectedSessionId, true);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(friendlyErrorBanner(err instanceof Error ? err.message : String(err)));
    } finally {
      if (mountedRef.current) setSubmitting(false);
    }
  };

  const handleResolveApproval = async (
    elicitationId: string,
    action: "accept" | "decline",
  ) => {
    if (!selectedSessionId || !mutationsEnabled) return;
    setResolvingId(elicitationId);
    setErrorMsg(null);
    try {
      const res = await callOmnigent<Record<string, unknown>>("omnigent_resolve_approval", {
        session_id: selectedSessionId,
        elicitation_id: elicitationId,
        action,
      });
      if (!mountedRef.current) return;
      if (res.traceId) setLastTraceId(res.traceId);
      await loadSessionDetail(selectedSessionId, true);
      await loadWorkspace(false);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(friendlyErrorBanner(err instanceof Error ? err.message : String(err)));
    } finally {
      if (mountedRef.current) setResolvingId(null);
    }
  };

  const handleMarkInboxRead = async (itemId: string) => {
    if (!mutationsEnabled) return;
    setMarkingInboxId(itemId);
    setErrorMsg(null);
    try {
      const res = await callOmnigent<Record<string, unknown>>("omnigent_mark_inbox_item", {
        item_id: itemId,
        status: "read",
      });
      if (!mountedRef.current) return;
      if (res.traceId) setLastTraceId(res.traceId);
      await loadWorkspace(false);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(friendlyErrorBanner(err instanceof Error ? err.message : String(err)));
    } finally {
      if (mountedRef.current) setMarkingInboxId(null);
    }
  };

  const onlineHostName = hubStatus?.onlineHosts?.[0]?.name || "No host online";

  return (
    <div className="space-y-4">
      {errorMsg && (
        <div
          role="alert"
          className="rounded-xl border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] px-4 py-3 text-[12.5px] text-[var(--err)] flex items-start gap-2.5"
        >
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1 break-words">{errorMsg}</div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left Sidebar: Hub Status, Sessions & Inbox */}
        <div className="lg:col-span-4 space-y-4">
          <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[13px] font-semibold">Omnigent Hub</div>
                <div className="text-[11.5px] font-mono text-[var(--text-muted)] truncate">
                  {hubStatus
                    ? `v${hubStatus.serverVersion || "?"} · ${onlineHostName}`
                    : loading
                      ? "Connecting…"
                      : "Unavailable"}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {hubStatus && (
                  <StatusBadge
                    label={hubStatus.mutationsEnabled ? "Writable" : "Read-only"}
                    tone={hubStatus.mutationsEnabled ? "ok" : "warn"}
                  />
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => selectSession(null)}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12.5px] font-medium hover:opacity-90 cursor-pointer"
              >
                <MessageSquarePlus className="w-3.5 h-3.5" />
                <span>New Session</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  void loadWorkspace(false);
                  if (selectedSessionId) void loadSessionDetail(selectedSessionId);
                }}
                disabled={refreshing}
                aria-label="Refresh Omnigent Chat"
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[12px] text-[var(--text-secondary)] cursor-pointer disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                <span>Refresh</span>
              </button>
            </div>
          </div>

          {/* Sessions List */}
          <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5 space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[12.5px] font-semibold">
                Sessions ({filteredSessions.length})
              </div>
              <select
                aria-label="Filter sessions by project"
                value={projectFilter}
                onChange={(e) => setProjectFilter(e.target.value)}
                className="max-w-[170px] rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-2 py-1 text-[11.5px] text-[var(--text-primary)]"
              >
                <option value="">All projects</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1 max-h-[300px] overflow-y-auto pr-0.5">
              {filteredSessions.length === 0 ? (
                <div className="text-[12px] text-[var(--text-muted)] py-3 text-center">
                  {loading ? "Loading sessions…" : "No matching sessions"}
                </div>
              ) : (
                filteredSessions.map((s) => {
                  const active = s.id === selectedSessionId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => selectSession(s.id)}
                      className={`w-full text-left px-2.5 py-2 rounded-lg border transition-colors cursor-pointer ${
                        active
                          ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                          : "border-transparent hover:bg-[var(--bg-hover)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[12.5px] font-medium text-[var(--text-primary)] truncate">
                          {s.title || s.id}
                        </span>
                        <StatusBadge
                          label={s.status || "idle"}
                          tone={sessionTone(s.status)}
                        />
                      </div>
                      <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
                        <span className="truncate font-mono">{s.agentName || "polly"}</span>
                        {(s.pendingApprovals || 0) > 0 && (
                          <span className="px-1.5 py-0.2 rounded bg-[var(--warn-soft)] text-[var(--warn)] font-medium shrink-0">
                            {s.pendingApprovals} pending
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Unread Inbox */}
          <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3.5 space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[12.5px] font-semibold">
                <Inbox className="w-3.5 h-3.5 text-[var(--accent)]" />
                <span>Unread Inbox ({inbox?.unreadCount ?? 0})</span>
              </div>
            </div>

            <div className="space-y-2 max-h-[240px] overflow-y-auto pr-0.5">
              {!inbox || inbox.items.length === 0 ? (
                <div className="text-[12px] text-[var(--text-muted)] py-2 text-center">
                  {loading ? "Loading inbox…" : "No unread items"}
                </div>
              ) : (
                inbox.items.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-2.5 space-y-1.5"
                  >
                    <div className="text-[12px] font-medium text-[var(--text-primary)] leading-snug">
                      {item.title || item.id}
                    </div>
                    <div className="flex items-center gap-2 pt-0.5">
                      {item.sourceSessionId && (
                        <button
                          type="button"
                          onClick={() => selectSession(item.sourceSessionId || null)}
                          className="text-[11px] font-medium text-[var(--accent)] hover:underline cursor-pointer"
                        >
                          Open
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={!mutationsEnabled || markingInboxId === item.id}
                        onClick={() => void handleMarkInboxRead(item.id)}
                        className="text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer disabled:opacity-40"
                      >
                        {markingInboxId === item.id ? "Marking…" : "Mark read"}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Main Panel: New Session Composer or Active Session Transcript */}
        <div className="lg:col-span-8">
          {!selectedSessionId ? (
            <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 space-y-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h2 className="text-[15px] font-semibold m-0">Start Omnigent Session</h2>
                  <p className="text-[12px] text-[var(--text-secondary)] m-0 mt-0.5">
                    Launches Polly or a saved multi-step workflow on macstudio.local with your server-wide policies and MLflow tracing.
                  </p>
                </div>
                {lastTraceId && (
                  <button
                    type="button"
                    onClick={() => onInspectTrace(lastTraceId)}
                    className="text-[11.5px] font-mono text-[var(--accent)] hover:underline cursor-pointer shrink-0"
                  >
                    Inspect trace
                  </button>
                )}
              </div>

              {!mutationsEnabled && (
                <div className="rounded-lg border border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--warn-soft)] px-3 py-2 text-[12px] text-[var(--warn)]">
                  Omnigent mutations are currently disabled (OMNIGENT_ALLOW_MUTATIONS=false). Start/send/approval controls are locked.
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <label className="block space-y-1">
                  <span className="text-[11.5px] font-medium text-[var(--text-secondary)]">
                    Project
                  </span>
                  <select
                    aria-label="Project"
                    value={newProjectId}
                    onChange={(e) => setNewProjectId(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[12.5px] text-[var(--text-primary)]"
                  >
                    <option value="">Default workspace</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block space-y-1">
                  <span className="text-[11.5px] font-medium text-[var(--text-secondary)] inline-flex items-center gap-1">
                    <Workflow className="w-3 h-3" /> Saved Workflow
                  </span>
                  <select
                    aria-label="Saved Workflow"
                    value={newWorkflow}
                    onChange={(e) => setNewWorkflow(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[12.5px] text-[var(--text-primary)]"
                  >
                    <option value="">None (direct chat)</option>
                    {workflows.map((w) => (
                      <option key={w.id} value={w.name}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block space-y-1">
                  <span className="text-[11.5px] font-medium text-[var(--text-secondary)]">
                    Model Override
                  </span>
                  <select
                    aria-label="Model Override"
                    value={newModelOverride}
                    onChange={(e) => setNewModelOverride(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[12.5px] text-[var(--text-primary)]"
                  >
                    <option value="">Default</option>
                    <option value="opus">opus</option>
                    <option value="sonnet">sonnet</option>
                    <option value="haiku">haiku</option>
                  </select>
                </label>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {QUICK_PROMPTS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => setNewPrompt(q)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-[var(--border-hairline)] bg-[var(--bg-subtle)] hover:border-[var(--border-strong)] text-[11.5px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
                  >
                    <Sparkles className="w-3 h-3 text-[var(--accent)]" />
                    <span>{q}</span>
                  </button>
                ))}
              </div>

              <div className="space-y-2">
                <textarea
                  aria-label="Task prompt"
                  rows={5}
                  value={newPrompt}
                  onChange={(e) => setNewPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                      e.preventDefault();
                      void handleStartSession();
                    }
                  }}
                  placeholder={
                    newWorkflow
                      ? "Optional details/target (e.g. SPE-1706 or PR URL)…"
                      : "Describe what Polly should investigate, build, or check…"
                  }
                  className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                />
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-[var(--text-muted)]">
                    Press ⌘Enter / Ctrl+Enter to submit
                  </span>
                  <button
                    type="button"
                    disabled={
                      !mutationsEnabled ||
                      submitting ||
                      (!newPrompt.trim() && !newWorkflow)
                    }
                    onClick={() => void handleStartSession()}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-[var(--accent)] text-white text-[12.5px] font-medium hover:opacity-90 cursor-pointer disabled:opacity-45"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>
                      {submitting
                        ? "Launching…"
                        : newWorkflow
                          ? "Run workflow"
                          : "Start session"}
                    </span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] flex flex-col">
              {/* Session Header */}
              <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-[14.5px] font-semibold m-0 truncate">
                      {activeSession?.title || selectedSessionId}
                    </h2>
                    <StatusBadge
                      label={activeSession?.status || (sessionLoading ? "loading" : "idle")}
                      tone={sessionTone(activeSession?.status)}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-[var(--text-muted)]">
                    {activeSession?.agentName && <span>{activeSession.agentName}</span>}
                    {activeSession?.llmModel && <span>· {activeSession.llmModel}</span>}
                    {activeSession?.gitBranch && <span>· {activeSession.gitBranch}</span>}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {lastTraceId && (
                    <button
                      type="button"
                      onClick={() => onInspectTrace(lastTraceId)}
                      className="px-2.5 py-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[11.5px] font-mono text-[var(--accent)] cursor-pointer"
                    >
                      Inspect trace
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void loadSessionDetail(selectedSessionId)}
                    className="p-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[var(--text-secondary)] cursor-pointer"
                    aria-label="Reload session"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${sessionLoading ? "animate-spin" : ""}`} />
                  </button>
                  {activeSession?.sessionUrl && (
                    <a
                      href={activeSession.sessionUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[11.5px] text-[var(--text-primary)]"
                    >
                      <span>Open in Omnigent</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>

              {/* Pending Approval Banner */}
              {activeSession && activeSession.pendingElicitations.length > 0 && (
                <div className="px-4 py-3 border-b border-[color-mix(in_srgb,var(--warn)_30%,transparent)] bg-[var(--warn-soft)] space-y-2">
                  <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--warn)]">
                    <ShieldAlert className="w-4 h-4 shrink-0" />
                    <span>
                      Pending Approval ({activeSession.pendingElicitations.length})
                    </span>
                  </div>
                  {activeSession.pendingElicitations.map((el, idx) => {
                    const eid = elicitationIdOf(el, idx);
                    const busy = resolvingId === eid;
                    return (
                      <div
                        key={eid}
                        className="rounded-lg border border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--bg-surface)] p-2.5 flex flex-wrap items-center justify-between gap-2"
                      >
                        <div className="min-w-0 flex-1 text-[12px] text-[var(--text-primary)] break-words">
                          {elicitationPromptOf(el)}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            type="button"
                            disabled={!mutationsEnabled || busy}
                            onClick={() => void handleResolveApproval(eid, "accept")}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-[var(--ok)] text-white text-[11.5px] font-medium cursor-pointer disabled:opacity-45"
                          >
                            <Check className="w-3 h-3" />
                            <span>Approve</span>
                          </button>
                          <button
                            type="button"
                            disabled={!mutationsEnabled || busy}
                            onClick={() => void handleResolveApproval(eid, "decline")}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[11.5px] text-[var(--err)] font-medium cursor-pointer disabled:opacity-45"
                          >
                            <X className="w-3 h-3" />
                            <span>Decline</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Transcript */}
              <div className="p-4 space-y-3 max-h-[520px] overflow-y-auto">
                {sessionLoading && !activeSession ? (
                  <div className="text-[12.5px] text-[var(--text-muted)] py-6 text-center">
                    Loading session transcript…
                  </div>
                ) : !activeSession || activeSession.recentMessages.length === 0 ? (
                  <div className="text-[12.5px] text-[var(--text-muted)] py-6 text-center">
                    No messages yet in this session.
                  </div>
                ) : (
                  activeSession.recentMessages.map((msg, idx) => {
                    const isUser = (msg.role || "").toLowerCase() === "user";
                    return (
                      <div
                        key={msg.id || `${idx}`}
                        className={`rounded-xl border px-3.5 py-2.5 text-[12.5px] ${
                          isUser
                            ? "border-[color-mix(in_srgb,var(--accent)_35%,transparent)] bg-[var(--accent-soft)] ml-6"
                            : "border-[var(--border-hairline)] bg-[var(--bg-subtle)] mr-6"
                        }`}
                      >
                        <div className="text-[10.5px] font-mono uppercase tracking-wider text-[var(--text-muted)] mb-1">
                          {isUser ? "You" : activeSession.agentName || "Assistant"}
                        </div>
                        <div className="max-w-none text-[var(--text-primary)] leading-relaxed break-words [&>p]:my-1.5 [&>p:first-child]:mt-0 [&>p:last-child]:mb-0 [&>pre]:rounded-lg [&>pre]:p-2.5 [&>pre]:bg-[var(--code-bg)] [&>pre]:overflow-x-auto">
                          <Markdown remarkPlugins={[remarkGfm]}>{msg.text}</Markdown>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Follow-up Composer */}
              <div className="p-3.5 border-t border-[var(--border-hairline)] space-y-2">
                {!mutationsEnabled && (
                  <div className="text-[11.5px] text-[var(--warn)]">
                    Follow-up messages disabled (OMNIGENT_ALLOW_MUTATIONS=false).
                  </div>
                )}
                <div className="flex items-end gap-2">
                  <textarea
                    aria-label="Follow-up message"
                    rows={2}
                    value={followUpText}
                    onChange={(e) => setFollowUpText(e.target.value)}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                        e.preventDefault();
                        void handleSendFollowUp();
                      }
                    }}
                    placeholder="Send a follow-up message… (⌘Enter / Ctrl+Enter)"
                    className="flex-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-3 py-2 text-[12.5px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
                  />
                  <button
                    type="button"
                    disabled={!mutationsEnabled || submitting || !followUpText.trim()}
                    onClick={() => void handleSendFollowUp()}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-[var(--accent)] text-white text-[12.5px] font-medium hover:opacity-90 cursor-pointer disabled:opacity-45 shrink-0"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>{submitting ? "Sending…" : "Send"}</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
