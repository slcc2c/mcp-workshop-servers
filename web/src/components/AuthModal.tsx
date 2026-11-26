import { useState } from "react";
import { KeyRound, X } from "lucide-react";

export function AuthModal({
  open,
  onClose,
  onSubmitToken,
  error,
}: {
  open: boolean;
  onClose: () => void;
  onSubmitToken: (token: string) => Promise<void>;
  error?: string | null;
}) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    try {
      await onSubmitToken(token.trim());
      setToken("");
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-xs p-4">
      <div className="w-full max-w-md rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] p-5 shadow-2xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-[14.5px]">
            <KeyRound className="w-4 h-4 text-[var(--accent)]" />
            Sign in to Gateway Control Plane
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-[12.5px] text-[var(--text-secondary)] leading-relaxed">
          Paste a client Bearer token (stored strictly in an <code className="font-mono">HttpOnly</code> session cookie), or mint a 60s login link with{" "}
          <code className="font-mono text-[var(--text-primary)]">mcp-stack ui open</code>.
        </p>

        {error && (
          <div className="rounded-lg border border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)] px-3 py-2 text-[12px] text-[var(--err)]">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            autoFocus
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="MCP_CODEX_AUTH_TOKEN or client token"
            className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-2 font-mono text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !token.trim()}
              className="px-4 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12.5px] font-semibold disabled:opacity-50 cursor-pointer"
            >
              {busy ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
