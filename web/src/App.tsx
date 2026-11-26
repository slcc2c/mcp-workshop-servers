import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./lib/api";
import { parseWorkbenchUrl, syncWorkbenchUrl } from "./lib/urlState";
import { resolveMlflowUiUrl } from "./lib/urls";
import type {
  ActivityEvent,
  AuthState,
  EvalRunItem,
  HealthResponse,
  NavTab,
  PlaygroundPresetItem,
  PlaygroundReplayRequest,
  PlaygroundSubTab,
  ReadyResponse,
  RegistryResponse,
  RegistrySubTab,
  ThemeMode,
  ToolItem,
  UpstreamsSubTab,
  WatchdogResponse,
} from "./types";
import { ActivityDrawer } from "./components/ActivityDrawer";
import { AgentChatPanel } from "./components/AgentChatPanel";
import { AuthModal } from "./components/AuthModal";
import { CommandPalette } from "./components/CommandPalette";
import { Layout } from "./components/Layout";
import { ShortcutsModal } from "./components/ShortcutsModal";
import { ChatView } from "./views/ChatView";
import { ClientsView } from "./views/ClientsView";
import { EvalsView } from "./views/EvalsView";
import { OverviewView } from "./views/OverviewView";
import { PlaygroundView } from "./views/PlaygroundView";
import { RegistryView } from "./views/RegistryView";
import { TracesView } from "./views/TracesView";
import { UpstreamsView } from "./views/UpstreamsView";

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

const G_NAV_MAP: Record<string, NavTab> = {
  o: "overview",
  p: "playground",
  t: "traces",
  e: "evals",
  r: "registry",
  u: "upstreams",
  c: "clients",
};

function resolveInitialSub<T extends string>(raw: string | null | undefined, allowed: T[], fallback: T): T {
  return raw && (allowed as string[]).includes(raw) ? (raw as T) : fallback;
}

export function App() {
  const initialUrlState = useMemo(() => parseWorkbenchUrl(window.location), []);
  const [activeTab, setActiveTab] = useState<NavTab>(initialUrlState.tab);
  const [playgroundSubTab, setPlaygroundSubTab] = useState<PlaygroundSubTab>(() =>
    resolveInitialSub(initialUrlState.sub, ["tools", "agent", "omnigent"], "tools"),
  );
  const [registrySubTab, setRegistrySubTab] = useState<RegistrySubTab>(() =>
    resolveInitialSub(initialUrlState.sub, ["servers", "prompts", "models", "skills"], "servers"),
  );
  const [upstreamsSubTab, setUpstreamsSubTab] = useState<UpstreamsSubTab>(() =>
    resolveInitialSub(initialUrlState.sub, ["upstreams", "profiles"], "upstreams"),
  );
  const [theme, setTheme] = useState<ThemeMode>(readInitialTheme);
  const [autoRefreshMs, setAutoRefreshMs] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [activityPaused, setActivityPaused] = useState(false);
  const [activityEvents, setActivityEvents] = useState<ActivityEvent[]>([]);
  const [activityStreamState, setActivityStreamState] = useState<"live" | "connecting" | "offline">(
    "offline",
  );
  const activityPausedRef = useRef(false);
  activityPausedRef.current = activityPaused;
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
  const [presets, setPresets] = useState<PlaygroundPresetItem[]>([]);

  const [profileFilter, setProfileFilter] = useState(initialUrlState.profile || "");
  const [serverFilter, setServerFilter] = useState(initialUrlState.server || "");
  const [selectedToolKey, setSelectedToolKey] = useState<string | null>(
    initialUrlState.tool || null,
  );
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(
    initialUrlState.trace || null,
  );
  const [selectedPromptName, setSelectedPromptName] = useState<string | null>(
    initialUrlState.prompt || null,
  );
  const [selectedPromptVersion, setSelectedPromptVersion] = useState<string | null>(
    initialUrlState.version || null,
  );
  const [selectedChatSessionId, setSelectedChatSessionId] = useState<string | null>(
    initialUrlState.session || null,
  );
  const [replayRequest, setReplayRequest] = useState<PlaygroundReplayRequest | null>(null);

  const gChordActiveRef = useRef(false);
  const gChordTimerRef = useRef<number | null>(null);
  const replayNonceRef = useRef(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("mcp_wb_theme", theme);
    } catch {
      // ignore
    }
  }, [theme]);

  // Keep URL synchronized with deep-linkable workbench state
  useEffect(() => {
    const activeSub =
      activeTab === "playground"
        ? playgroundSubTab
        : activeTab === "registry"
          ? registrySubTab
          : activeTab === "upstreams"
            ? upstreamsSubTab
            : null;
    syncWorkbenchUrl({
      tab: activeTab,
      sub: activeSub,
      session: selectedChatSessionId,
      profile: profileFilter,
      server: serverFilter,
      tool: selectedToolKey,
      trace: selectedTraceId,
      prompt: selectedPromptName,
      version: selectedPromptVersion,
    });
  }, [
    activeTab,
    playgroundSubTab,
    registrySubTab,
    upstreamsSubTab,
    selectedChatSessionId,
    profileFilter,
    serverFilter,
    selectedToolKey,
    selectedTraceId,
    selectedPromptName,
    selectedPromptVersion,
  ]);

  // Listen to browser back/forward navigation
  useEffect(() => {
    function onPopState() {
      const parsed = parseWorkbenchUrl(window.location);
      setActiveTab(parsed.tab);
      if (parsed.tab === "playground") {
        setPlaygroundSubTab(
          resolveInitialSub<PlaygroundSubTab>(parsed.sub, ["tools", "agent", "omnigent"], "tools"),
        );
      } else if (parsed.tab === "registry") {
        setRegistrySubTab(
          resolveInitialSub<RegistrySubTab>(
            parsed.sub,
            ["servers", "prompts", "models", "skills"],
            "servers",
          ),
        );
      } else if (parsed.tab === "upstreams") {
        setUpstreamsSubTab(
          resolveInitialSub<UpstreamsSubTab>(parsed.sub, ["upstreams", "profiles"], "upstreams"),
        );
      }
      setSelectedChatSessionId(parsed.session || null);
      if (parsed.profile !== undefined) setProfileFilter(parsed.profile || "");
      if (parsed.server !== undefined) setServerFilter(parsed.server || "");
      setSelectedToolKey(parsed.tool || null);
      setSelectedTraceId(parsed.trace || null);
      setSelectedPromptName(parsed.prompt || null);
      setSelectedPromptVersion(parsed.version || null);
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigateTab = useCallback((tab: NavTab) => {
    setActiveTab(tab);
  }, []);

  // Global keyboard shortcuts (Cmd/Ctrl+K, g+<tab>, ?, /, Esc)
  useEffect(() => {
    function clearGChord() {
      gChordActiveRef.current = false;
      if (gChordTimerRef.current !== null) {
        window.clearTimeout(gChordTimerRef.current);
        gChordTimerRef.current = null;
      }
    }

    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        clearGChord();
        setShortcutsOpen(false);
        setPaletteOpen((v) => !v);
        return;
      }

      if (e.key === "Escape") {
        clearGChord();
        if (shortcutsOpen) {
          setShortcutsOpen(false);
          return;
        }
        if (paletteOpen) {
          setPaletteOpen(false);
          return;
        }
        if (authModalOpen) {
          setAuthModalOpen(false);
        }
        return;
      }

      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toUpperCase() || "";
      const isEditing =
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        Boolean(target?.isContentEditable);

      if (isEditing || e.metaKey || e.ctrlKey || e.altKey) {
        clearGChord();
        return;
      }

      if (gChordActiveRef.current) {
        const key = e.key.toLowerCase();
        clearGChord();
        if (key === "l") {
          e.preventDefault();
          setActivityOpen((v) => !v);
          return;
        }
        if (key === "a") {
          e.preventDefault();
          setPlaygroundSubTab("agent");
          navigateTab("playground");
          return;
        }
        if (key === "s") {
          e.preventDefault();
          setRegistrySubTab("skills");
          navigateTab("registry");
          return;
        }
        const dest = G_NAV_MAP[key];
        if (dest) {
          e.preventDefault();
          navigateTab(dest);
        }
        return;
      }

      if (e.key === "g") {
        gChordActiveRef.current = true;
        gChordTimerRef.current = window.setTimeout(clearGChord, 800);
        return;
      }

      if (e.key === "?") {
        e.preventDefault();
        setPaletteOpen(false);
        setShortcutsOpen((v) => !v);
        return;
      }

      if (e.key === "/") {
        const searchInput = document.querySelector<HTMLInputElement>(
          '[data-shortcut-search="true"]',
        );
        if (searchInput) {
          e.preventDefault();
          searchInput.focus();
          searchInput.select();
        }
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      clearGChord();
    };
  }, [paletteOpen, shortcutsOpen, authModalOpen, navigateTab]);

  const loadToolsOnly = useCallback(async (prof: string, srv: string) => {
    try {
      const res = await api.tools({ profile: prof || undefined, server: srv || undefined });
      setTools(res.tools || []);
      setProfileCounts(res.profileCounts || {});
    } catch {
      // ignore if unauthenticated
    }
  }, []);

  const reloadPresets = useCallback(async () => {
    try {
      const res = await api.presets();
      setPresets(res.presets || []);
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

    const [wd, tl, tr, reg, pr] = await Promise.all([
      api.watchdog().catch(() => null),
      api.tools({ profile: profileFilter || undefined, server: serverFilter || undefined }).catch(() => null),
      api.traces({ limit: "15" }).catch(() => null),
      api.registry().catch(() => null),
      api.presets().catch(() => null),
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
    if (pr) setPresets(pr.presets || []);
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

  useEffect(() => {
    if (!auth.authenticated && auth.authEnabled) {
      setActivityStreamState("offline");
      return;
    }
    if (typeof EventSource === "undefined") return;
    setActivityStreamState("connecting");
    const es = new EventSource("/api/v1/ops/stream", { withCredentials: true });
    es.addEventListener("snapshot", (evt) => {
      setActivityStreamState("live");
      if (activityPausedRef.current) return;
      try {
        const parsed = JSON.parse((evt as MessageEvent).data) as { events?: ActivityEvent[] };
        if (Array.isArray(parsed.events)) {
          setActivityEvents(parsed.events.slice(-200));
        }
      } catch {
        // ignore malformed frame
      }
    });
    es.addEventListener("activity", (evt) => {
      setActivityStreamState("live");
      if (activityPausedRef.current) return;
      try {
        const ev = JSON.parse((evt as MessageEvent).data) as ActivityEvent;
        setActivityEvents((prev) => [...prev.slice(-199), ev]);
      } catch {
        // ignore malformed frame
      }
    });
    es.onerror = () => {
      setActivityStreamState("offline");
    };
    return () => {
      es.close();
      setActivityStreamState("offline");
    };
  }, [auth.authenticated, auth.authEnabled]);

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
    setPresets([]);
    setRegistry(null);
    await refreshAll();
  }

  function handleInspectTrace(traceId: string) {
    setSelectedTraceId(traceId);
    navigateTab("traces");
  }

  function handleReplayInPlayground(req: Omit<PlaygroundReplayRequest, "nonce">) {
    replayNonceRef.current += 1;
    setProfileFilter("");
    setServerFilter("");
    setSelectedToolKey(`${req.server}.${req.tool}`);
    setReplayRequest({ ...req, nonce: replayNonceRef.current });
    setPlaygroundSubTab("tools");
    navigateTab("playground");
  }

  const mlflowUiBase = resolveMlflowUiUrl(health?.mlflowUiUrl);

  return (
    <Layout
      activeTab={activeTab}
      onSelectTab={navigateTab}
      theme={theme}
      onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      version={health?.version || "2.5.0"}
      readyStatus={ready?.status || "checking"}
      auth={auth}
      autoRefreshMs={autoRefreshMs}
      onChangeAutoRefresh={setAutoRefreshMs}
      onRefreshAll={() => refreshAll()}
      onOpenPalette={() => setPaletteOpen(true)}
      onOpenShortcuts={() => setShortcutsOpen(true)}
      onOpenAuthModal={() => {
        setAuthError(null);
        setAuthModalOpen(true);
      }}
      onLogout={handleLogout}
      activityCount={activityEvents.length}
      activityLive={activityStreamState === "live"}
      onOpenActivity={() => setActivityOpen(true)}
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
            setPlaygroundSubTab("tools");
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
        <div className="space-y-4">
          <div className="inline-flex rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-0.5">
            {(
              [
                ["tools", "Tool Playground"],
                ["agent", "Agent Server"],
                ["omnigent", "Omnigent Chat"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setPlaygroundSubTab(id)}
                className={`px-3 py-1.5 rounded-md text-[12.5px] font-medium cursor-pointer transition-colors ${
                  playgroundSubTab === id
                    ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {playgroundSubTab === "tools" && (
            <PlaygroundView
              tools={tools}
              servers={health?.servers || []}
              profiles={health?.profiles || []}
              presets={presets}
              profileFilter={profileFilter}
              serverFilter={serverFilter}
              selectedToolKey={selectedToolKey}
              replayRequest={replayRequest}
              onChangeProfileFilter={(p) => {
                setProfileFilter(p);
                setSelectedToolKey(null);
              }}
              onChangeServerFilter={(s) => {
                setServerFilter(s);
                setSelectedToolKey(null);
              }}
              onSelectToolKey={setSelectedToolKey}
              onPresetsChanged={reloadPresets}
              onInspectTrace={handleInspectTrace}
              onAfterRun={() => refreshAll()}
            />
          )}

          {playgroundSubTab === "agent" && (
            <AgentChatPanel
              profiles={health?.profiles || []}
              prompts={registry?.prompts || []}
              onInspectTrace={handleInspectTrace}
            />
          )}

          {playgroundSubTab === "omnigent" && (
            <ChatView
              authenticated={auth.authenticated || !auth.authEnabled}
              initialSessionId={selectedChatSessionId}
              onSelectSessionId={setSelectedChatSessionId}
              onInspectTrace={handleInspectTrace}
            />
          )}
        </div>
      )}

      {activeTab === "traces" && (
        <TracesView
          initialTraceId={selectedTraceId}
          mlflowUiBase={mlflowUiBase}
          onSelectTraceId={setSelectedTraceId}
          onReplayInPlayground={handleReplayInPlayground}
        />
      )}

      {activeTab === "evals" && (
        <EvalsView
          profiles={health?.profiles || []}
          onInspectTrace={handleInspectTrace}
          onAfterRun={refreshAll}
        />
      )}

      {activeTab === "registry" && (
        <RegistryView
          registry={registry}
          initialSubTab={registrySubTab}
          initialPromptName={selectedPromptName}
          initialPromptVersion={selectedPromptVersion}
          mlflowUiBase={mlflowUiBase}
          onChangeSubTab={setRegistrySubTab}
          onSelectPrompt={(name, ver) => {
            setSelectedPromptName(name);
            setSelectedPromptVersion(ver || null);
          }}
          onReload={async () => {
            const reg = await api.registry();
            setRegistry(reg);
          }}
        />
      )}

      {activeTab === "upstreams" && (
        <UpstreamsView
          initialSubTab={upstreamsSubTab}
          onChangeSubTab={setUpstreamsSubTab}
          profiles={health?.profiles || []}
          servers={health?.servers || []}
          profileCounts={profileCounts}
          onAfterChange={refreshAll}
        />
      )}

      {activeTab === "clients" && <ClientsView profileCounts={profileCounts} />}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        presets={presets}
        servers={health?.servers || []}
        tools={tools}
        prompts={registry?.prompts || []}
        onSelectTab={navigateTab}
        onSelectPreset={(preset) => {
          handleReplayInPlayground({
            server: preset.server,
            tool: preset.tool,
            arguments: preset.arguments || {},
            presetName: preset.name,
            autoRun: false,
          });
        }}
        onSelectTool={(srv, toolName) => {
          setProfileFilter("");
          setServerFilter(srv);
          setSelectedToolKey(toolName ? `${srv}.${toolName}` : null);
          setPlaygroundSubTab("tools");
          navigateTab("playground");
        }}
        onSelectPrompt={(name) => {
          setSelectedPromptName(name);
          setSelectedPromptVersion(null);
          setRegistrySubTab("prompts");
          navigateTab("registry");
        }}
      />

      <ActivityDrawer
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
        events={activityEvents}
        paused={activityPaused}
        streamState={activityStreamState}
        onTogglePause={() => setActivityPaused((p) => !p)}
        onClear={() => setActivityEvents([])}
        onInspectTrace={handleInspectTrace}
      />

      <ShortcutsModal open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />

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
