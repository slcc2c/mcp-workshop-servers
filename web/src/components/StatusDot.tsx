import type { ReactNode } from "react";

export type SemanticTone = "ok" | "warn" | "err" | "neutral" | "accent";

const TONE_MAP: Record<SemanticTone, { dot: string; text: string; bg: string; border: string }> = {
  ok: {
    dot: "bg-[var(--ok)]",
    text: "text-[var(--ok)]",
    bg: "bg-[var(--ok-soft)]",
    border: "border-[color-mix(in_srgb,var(--ok)_28%,transparent)]",
  },
  warn: {
    dot: "bg-[var(--warn)]",
    text: "text-[var(--warn)]",
    bg: "bg-[var(--warn-soft)]",
    border: "border-[color-mix(in_srgb,var(--warn)_28%,transparent)]",
  },
  err: {
    dot: "bg-[var(--err)]",
    text: "text-[var(--err)]",
    bg: "bg-[var(--err-soft)]",
    border: "border-[color-mix(in_srgb,var(--err)_28%,transparent)]",
  },
  accent: {
    dot: "bg-[var(--accent)]",
    text: "text-[var(--accent)]",
    bg: "bg-[var(--accent-soft)]",
    border: "border-[color-mix(in_srgb,var(--accent)_28%,transparent)]",
  },
  neutral: {
    dot: "bg-[var(--text-muted)]",
    text: "text-[var(--text-secondary)]",
    bg: "bg-[var(--bg-subtle)]",
    border: "border-[var(--border-hairline)]",
  },
};

export function connectionTone(status?: string | null): SemanticTone {
  const s = (status || "").toLowerCase();
  if (s === "connected" || s === "ready" || s === "ok" || s === "healthy" || s === "enabled") {
    return "ok";
  }
  if (s === "auth_required" || s === "configured" || s === "degraded") return "warn";
  if (s === "disabled" || s === "unconfigured") return "neutral";
  if (s === "error" || s === "unreachable" || s === "down") return "err";
  return "neutral";
}

export function StatusBadge({
  label,
  tone = "neutral",
  title,
  icon,
}: {
  label: string;
  tone?: SemanticTone;
  title?: string;
  icon?: ReactNode;
}) {
  const s = TONE_MAP[tone];
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11.5px] font-medium whitespace-nowrap shrink-0 ${s.bg} ${s.text} ${s.border}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.dot}`} />
      {icon}
      <span>{label}</span>
    </span>
  );
}
