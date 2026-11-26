import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Play } from "lucide-react";
import { api } from "../lib/api";
import { CopyButton } from "../components/CopyButton";
import { StatusBadge } from "../components/StatusDot";

const CLIENT_ORDER = [
  { id: "antigravity", label: "Antigravity" },
  { id: "codex", label: "Codex CLI" },
  { id: "claude-code", label: "Claude Code" },
  { id: "cursor", label: "Cursor" },
  { id: "gemini-cli", label: "Gemini CLI" },
  { id: "claude-desktop", label: "Claude Desktop" },
] as const;

export function ClientsView({ profileCounts }: { profileCounts: Record<string, number> }) {
  const [selectedProfile, setSelectedProfile] = useState("studio");
  const [selectedClient, setSelectedClient] = useState("antigravity");
  const [profiles, setProfiles] = useState<Array<{ name: string; route: string; servers: string[] }>>([]);
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [verifying, setVerifying] = useState(false);
  const [verifyRes, setVerifyRes] = useState<{
    ok: boolean;
    client: string;
    profile: string;
    url: string;
    authStatus: string;
    protocolVersion?: string;
    toolCount?: number;
    latencyMs: number;
    error?: string;
  } | null>(null);

  const load = useCallback(async (prof: string) => {
    const res = await api.clientConfigs(prof);
    setProfiles(res.profiles || []);
    setConfigs(res.configs || {});
  }, []);

  useEffect(() => {
    load(selectedProfile).catch(() => {});
  }, [selectedProfile, load]);

  async function handleVerify() {
    setVerifying(true);
    setVerifyRes(null);
    try {
      const res = await api.verifyClient(selectedClient, selectedProfile);
      setVerifyRes(res);
    } finally {
      setVerifying(false);
    }
  }

  const snippet = configs[selectedClient] || "";
  const installCmd = `uv run mcp-stack config install --client ${selectedClient} --profile ${selectedProfile}`;
  const verifyCmd = `uv run mcp-stack config verify --client ${selectedClient} --profile ${selectedProfile}`;

  return (
    <div className="space-y-4">
      {/* Profile Selector */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <h2 className="text-[14px] font-semibold m-0">Agent Onboarding & Tool Budgets</h2>
            <p className="text-[12px] text-[var(--text-secondary)] m-0 mt-0.5">
              Choose a curated profile (or <code className="font-mono">discover</code> for 6-tool lean discovery + on-demand search) to minimize agent context overhead.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-[12px] text-[var(--text-secondary)]">Profile</label>
            <select
              aria-label="Target client profile"
              value={selectedProfile}
              onChange={(e) => {
                setSelectedProfile(e.target.value);
                setVerifyRes(null);
              }}
              className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 font-mono text-[12.5px]"
            >
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({profileCounts[p.name] ?? "?"} tools)
                </option>
              ))}
              <option value="full">full (all mounted tools)</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {CLIENT_ORDER.map((cli) => (
            <button
              key={cli.id}
              type="button"
              onClick={() => {
                setSelectedClient(cli.id);
                setVerifyRes(null);
              }}
              className={`px-3 py-1.5 rounded-lg border text-[12.5px] font-medium cursor-pointer transition-colors ${
                selectedClient === cli.id
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {cli.label}
            </button>
          ))}
        </div>
      </section>

      {/* Config Snippet & Live Verify */}
      <section className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-5 space-y-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="font-mono text-[13.5px] font-semibold">
            {CLIENT_ORDER.find((c) => c.id === selectedClient)?.label} · profile={selectedProfile}
          </div>
          <div className="flex items-center gap-2">
            <CopyButton text={snippet} label="Copy config" compact />
            <button
              type="button"
              disabled={verifying || selectedClient === "claude-desktop"}
              onClick={handleVerify}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12px] font-semibold cursor-pointer"
            >
              <Play className="w-3.5 h-3.5" />
              {verifying ? "Testing MCP handshake..." : "Test Live Connection"}
            </button>
          </div>
        </div>

        {verifyRes && (
          <div
            className={`rounded-lg border p-3.5 flex items-center justify-between gap-3 flex-wrap ${
              verifyRes.ok
                ? "border-[color-mix(in_srgb,var(--ok)_35%,transparent)] bg-[var(--ok-soft)]"
                : "border-[color-mix(in_srgb,var(--err)_35%,transparent)] bg-[var(--err-soft)]"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <CheckCircle2
                className={`w-4 h-4 shrink-0 ${verifyRes.ok ? "text-[var(--ok)]" : "text-[var(--err)]"}`}
              />
              <div className="text-[12.5px]">
                <div className="font-medium">
                  {verifyRes.ok
                    ? `Handshake OK (${verifyRes.toolCount} tools discovered in ${verifyRes.latencyMs} ms)`
                    : `Connection failed: ${verifyRes.error}`}
                </div>
                <div className="font-mono text-[11px] text-[var(--text-secondary)]">
                  {verifyRes.url} · protocol={verifyRes.protocolVersion || "n/a"} · auth={verifyRes.authStatus}
                </div>
              </div>
            </div>
            <StatusBadge label={verifyRes.ok ? "CONNECTED" : "FAILED"} tone={verifyRes.ok ? "ok" : "err"} />
          </div>
        )}

        <pre className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words m-0 overflow-x-auto">
          {snippet || "Loading snippet..."}
        </pre>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
          <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[11px] text-[var(--text-muted)]">Safe Install (with backup)</div>
              <div className="font-mono text-[11.5px] truncate">{installCmd}</div>
            </div>
            <CopyButton text={installCmd} label="Copy" compact />
          </div>
          <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-subtle)] p-3 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[11px] text-[var(--text-muted)]">CLI Probe</div>
              <div className="font-mono text-[11.5px] truncate">{verifyCmd}</div>
            </div>
            <CopyButton text={verifyCmd} label="Copy" compact />
          </div>
        </div>
      </section>
    </div>
  );
}
