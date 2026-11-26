import { useMemo, useState } from "react";
import { Pause, Play, Radio, Trash2, X } from "lucide-react";
import type { ActivityEvent } from "../types";
import { StatusBadge } from "./StatusDot";

type ActivityFilter = "all" | "tool_call" | "agent_turn" | "probe" | "eval" | "profile";

const FILTERS: Array<{ id: ActivityFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "tool_call", label: "Tool calls" },
  { id: "agent_turn", label: "Agent turns" },
  { id: "probe", label: "Probes" },
  { id: "eval", label: "Evals" },
  { id: "profile", label: "Profiles" },
];

function formatClock(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso.slice(11, 19);
  }
}

function statusTone(status: string): "ok" | "warn" | "err" | "neutral" {
  const s = (status || "").toLowerCase();
  if (s === "ok" || s === "connected" || s === "ready" || s === "done") return "ok";
  if (s === "auth_required" || s === "degraded") return "warn";
  if (s === "error" || s === "failed" || s === "unreachable") return "err";
  return "neutral";
}

export function ActivityDrawer({
  open,
  onClose,
  events,
  paused,
  streamState,
  onTogglePause,
  onClear,
  onInspectTrace,
}: {
  open: boolean;
  onClose: () => void;
  events: ActivityEvent[];
  paused: boolean;
  streamState: "live" | "connecting" | "offline";
  onTogglePause: () => void;
  onClear: () => void;
  onInspectTrace: (traceId: string) => void;
}) {
  const [filter, setFilter] = useState<ActivityFilter>("all");

  const filtered = useMemo(() => {
    const list = filter === "all" ? events : events.filter((e) => e.kind === filter);
    return [...list].reverse();
  }, [events, filter]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="Live Activity Stream"
      className="fixed inset-0 z-50 flex justify-end bg-black/45"
      onClick={onClose}
    >
      <aside
        className="w-full max-w-[460px] h-full bg-[var(--bg-surface)] border-l border-[var(--border-hairline)] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Radio
              className={`w-4 h-4 shrink-0 ${
                streamState === "live"
                  ? "text-[var(--ok)]"
                  : streamState === "connecting"
                    ? "text-[var(--warn)]"
                    : "text-[var(--text-muted)]"
              }`}
            />
            <div>
              <h2 className="text-[14px] font-semibold m-0">Live Activity</h2>
              <div className="text-[11px] text-[var(--text-muted)]">
                {streamState === "live"
                  ? "Connected to SSE ops stream"
                  : streamState === "connecting"
                    ? "Connecting to SSE ops stream"
                    : "Stream offline"}{" "}
                · {events.length} events
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onTogglePause}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[11.5px] cursor-pointer"
            >
              {paused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
              {paused ? "Resume" : "Pause"}
            </button>
            <button
              type="button"
              onClick={onClear}
              aria-label="Clear activity stream"
              className="p-1.5 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close activity drawer"
              className="p-1.5 rounded-md hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="px-4 py-2 border-b border-[var(--border-hairline)] flex items-center gap-1.5 flex-wrap bg-[var(--bg-subtle)]">
          {FILTERS.map((f) => {
            const active = filter === f.id;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                className={`px-2 py-0.5 rounded-md text-[11px] font-medium cursor-pointer transition-colors ${
                  active
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--border-hairline)]"
                }`}
              >
                {f.label}
              </button>
            );
          })}
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {filtered.length === 0 ? (
            <div className="text-center py-12 text-[12.5px] text-[var(--text-muted)]">
              No activity events captured yet.
            </div>
          ) : (
            filtered.map((ev) => (
              <div
                key={ev.id}
                data-testid="activity-event-row"
                className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] p-2.5 text-[12px] space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-mono text-[10.5px] text-[var(--text-muted)]">
                      {formatClock(ev.ts)}
                    </span>
                    <StatusBadge label={ev.kind} tone="accent" />
                    <StatusBadge label={ev.status} tone={statusTone(ev.status)} />
                  </div>
                  {typeof ev.durationMs === "number" && (
                    <span className="font-mono text-[11px] text-[var(--text-muted)] tabular-nums">
                      {Math.round(ev.durationMs)} ms
                    </span>
                  )}
                </div>

                <div className="text-[12px] text-[var(--text-primary)] break-words">
                  {ev.summary}
                </div>

                <div className="flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)] font-mono flex-wrap">
                  <span>
                    actor={ev.actor}
                    {ev.server ? ` · ${ev.server}${ev.tool ? `.${ev.tool}` : ""}` : ""}
                    {ev.profile ? ` · profile=${ev.profile}` : ""}
                  </span>
                  {ev.traceId && (
                    <button
                      type="button"
                      onClick={() => {
                        onInspectTrace(ev.traceId!);
                        onClose();
                      }}
                      className="text-[var(--accent)] hover:underline cursor-pointer"
                    >
                      Trace {ev.traceId.slice(0, 12)}
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}
