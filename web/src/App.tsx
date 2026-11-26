import { Component, useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "./lib/api";
import type {
  AuthState,
  EvalRunItem,
  HealthResponse,
  NavTab,
  ReadyResponse,
  RegistryResponse,
  ThemeMode,
  ToolItem,
  WatchdogResponse,
} from "./types";
import { AuthModal } from "./components/AuthModal";
import { CommandPalette } from "./components/CommandPalette";
import { Layout } from "./components/Layout";
import { ClientsView } from "./views/ClientsView";
import { OverviewView } from "./views/OverviewView";
import { PlaygroundView } from "./views/PlaygroundView";
import { RegistryView } from "./views/RegistryView";
import { TracesView } from "./views/TracesView";
import { UpstreamsView } from "./views/UpstreamsView";

const VALID_TABS = new Set<NavTab>([
  "overview",
  "playground",
  "traces",
  "registry",
  "upstreams",
  "clients",
]);

function readInitialTab(): NavTab {
  const hash = window.location.hash.replace("#", "").trim() as NavTab;
  if (VALID_TABS.has(hash)) return hash;
  const parts = window.location.pathname.replace(/^\/ui\/?/, "").split("/").filter(Boolean);
  const candidate = parts[0] as NavTab | undefined;
  return candidate && VALID_TABS.has(candidate) ? candidate : "overview";
}

function readInitialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem("mcp_wb_theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // ignore
  }
  return "dark";
}

class WorkbenchErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[var(--bg-canvas)] text-[var(--text-primary)] p-6">
          <div className="max-w-lg w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] p-5 space-y-3">
            <div className="font-semibold text-[15px] text-[var(--err)]">
              Control Plane Render Error
            </div>
            <pre className="rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] p-3 font-mono text-[12px] whitespace-pre-wrap break-words">
              {this.state.error.message}
            </pre>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>(readInitialTab);
  const [theme, setTheme] = useState<ThemeMode>(readInitialTheme);
  const [autoRefreshMs, setAutoRefreshMs] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const [auth, setAuth] = useState<AuthState>({
    authenticated: false,
    authEnabled: true,
    clientId: null,
    clientName: null,
    allowedServers: [],
    mlflowMutationsEnabled: false,
  });
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [watchdog, setWatchdog] = useState<WatchdogResponse | null>(null);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [profileCounts, setProfileCounts] = useState<Record<string, number>>({});
  const [evalHistory, setEvalHistory] = useState<EvalRunItem[]>([]);
  const [registry, setRegistry] = useState<RegistryResponse | null>(null);

  const [profileFilter, setProfileFilter] = useState("");
  const [serverFilter, setServerFilter] = useState("");
  const [selectedToolKey, setSelectedToolKey] = useState<string | null>(null);
  const [selectedPromptName, setSelectedPromptName] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("mcp_wb_theme", theme);
    } catch {
      // ignore
    }
  }, [theme]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  function navigateTab(tab: NavTab) {
    setActiveTab(tab);
    window.location.hash = tab;
  }

  const loadToolsOnly = useCallback(async (prof: string, srv: string) => {
    try {
      const res = await api.tools({ profile: prof || undefined, server: srv || undefined });
      setTools(res.tools || []);
      setProfileCounts(res.profileCounts || {});
    } catch {
      // ignore if unauthenticated
    }
  }, []);

  const refreshAll = useCallback(async () => {
    const [h, r, me] = await Promise.all([
      api.health().catch(() => null),
      api.ready().catch(() => null),
      api.authMe().catch(() => null),
    ]);
    if (h) setHealth(h);
    if (r) setReady(r);
    if (me) setAuth(me);

    const canFetchAuthed = me ? !me.authEnabled || me.authenticated : false;
    if (!canFetchAuthed) return;

    const [wd, tl, tr, reg] = await Promise.all([
      api.watchdog().catch(() => null),
      api.tools({ profile: profileFilter || undefined, server: serverFilter || undefined }).catch(() => null),
      api.traces({ limit: "15" }).catch(() => null),
      api.registry().catch(() => null),
    ]);
    if (wd) setWatchdog(wd);
    if (tl) {
      setTools(tl.tools || []);
      setProfileCounts(tl.profileCounts || {});
    }
    if (tr) {
      setEvalHistory(tr.evalHistory || tr.evalRuns || []);
    }
    if (reg) setRegistry(reg);
  }, [profileFilter, serverFilter]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    if (!autoRefreshMs) return;
    const id = window.setInterval(() => {
      refreshAll();
    }, autoRefreshMs);
    return () => window.clearInterval(id);
  }, [autoRefreshMs, refreshAll]);

  useEffect(() => {
    if (auth.authenticated || !auth.authEnabled) {
      loadToolsOnly(profileFilter, serverFilter);
    }
  }, [profileFilter, serverFilter, auth.authenticated, auth.authEnabled, loadToolsOnly]);

  async function handleLoginToken(token: string) {
    setAuthError(null);
    try {
      const state = await api.loginToken(token);
      setAuth(state);
      await refreshAll();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  }

  async function handleLogout() {
    await api.logout();
    setWatchdog(null);
    setTools([]);
    setRegistry(null);
    await refreshAll();
  }

  return (
    <Layout
      activeTab={activeTab}
      onSelectTab={navigateTab}
      theme={theme}
      onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      version={health?.version || "2.3.0"}
      readyStatus={ready?.status || "checking"}
      auth={auth}
      autoRefreshMs={autoRefreshMs}
      onChangeAutoRefresh={setAutoRefreshMs}
      onRefreshAll={() => refreshAll()}
      onOpenPalette={() => setPaletteOpen(true)}
      onOpenAuthModal={() => {
        setAuthError(null);
        setAuthModalOpen(true);
      }}
      onLogout={handleLogout}
    >
      {auth.authEnabled && !auth.authenticated && (
        <div className="rounded-xl border border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--warn-soft)] p-4 flex items-center justify-between gap-3 flex-wrap">
          <div className="text-[13px]">
            Gateway auth is active. Sign in via <code className="font-mono">mcp-stack ui open</code> or enter a client Bearer token to access Playground, Traces, Registry, and Admin tools.
          </div>
          <button
            type="button"
            onClick={() => setAuthModalOpen(true)}
            className="px-3.5 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
          >
            Sign In
          </button>
        </div>
      )}

      {activeTab === "overview" && (
        <OverviewView
          auth={auth}
          health={health}
          ready={ready}
          watchdog={watchdog}
          evalHistory={evalHistory}
          profileCounts={profileCounts}
          onOpenPlaygroundServer={(slug) => {
            setProfileFilter("");
            setServerFilter(slug);
            setSelectedToolKey(null);
            navigateTab("playground");
          }}
          onProbeUpstream={async (slug) => {
            await api.probeUpstream(slug);
            await refreshAll();
          }}
          onNavigateTraces={() => navigateTab("traces")}
          onAfterAction={refreshAll}
        />
      )}

      {activeTab === "playground" && (
        <PlaygroundView
          tools={tools}
          servers={health?.servers || []}
          profiles={health?.profiles || []}
          profileFilter={profileFilter}
          serverFilter={serverFilter}
          selectedToolKey={selectedToolKey}
          onChangeProfileFilter={(p) => {
            setProfileFilter(p);
            setSelectedToolKey(null);
          }}
          onChangeServerFilter={(s) => {
            setServerFilter(s);
            setSelectedToolKey(null);
          }}
          onSelectToolKey={setSelectedToolKey}
          onAfterRun={() => refreshAll()}
        />
      )}

      {activeTab === "traces" && <TracesView />}

      {activeTab === "registry" && (
        <RegistryView
          registry={registry}
          initialPromptName={selectedPromptName}
          onReload={async () => {
            const reg = await api.registry();
            setRegistry(reg);
          }}
        />
      )}

      {activeTab === "upstreams" && <UpstreamsView onAfterChange={refreshAll} />}

      {activeTab === "clients" && <ClientsView profileCounts={profileCounts} />}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        servers={health?.servers || []}
        tools={tools}
        prompts={registry?.prompts || []}
        onSelectTab={navigateTab}
        onSelectTool={(srv, toolName) => {
          setProfileFilter("");
          setServerFilter(srv);
          setSelectedToolKey(toolName ? `${srv}.${toolName}` : null);
          navigateTab("playground");
        }}
        onSelectPrompt={(name) => {
          setSelectedPromptName(name);
          navigateTab("registry");
        }}
      />

      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSubmitToken={handleLoginToken}
        error={authError}
      />
    </Layout>
  );
}

export function RootApp() {
  return (
    <WorkbenchErrorBoundary>
      <App />
    </WorkbenchErrorBoundary>
  );
}
