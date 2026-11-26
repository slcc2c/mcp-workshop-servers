import type { ReactNode } from "react";
import {
  Activity,
  Bot,
  Boxes,
  Compass,
  Database,
  LogOut,
  Menu,
  Moon,
  Network,
  RefreshCw,
  Search,
  Sun,
  Terminal,
  X,
} from "lucide-react";
import { useState } from "react";
import type { AuthState, NavTab, ThemeMode } from "../types";
import { StatusBadge } from "./StatusDot";

const NAV_ITEMS: Array<{ id: NavTab; label: string; icon: ReactNode }> = [
  { id: "overview", label: "Overview", icon: <Compass className="w-4 h-4" /> },
  { id: "playground", label: "Playground", icon: <Terminal className="w-4 h-4" /> },
  { id: "traces", label: "Traces & Evals", icon: <Activity className="w-4 h-4" /> },
  { id: "registry", label: "MLflow Registry", icon: <Database className="w-4 h-4" /> },
  { id: "upstreams", label: "Upstreams", icon: <Network className="w-4 h-4" /> },
  { id: "clients", label: "Agents & Clients", icon: <Bot className="w-4 h-4" /> },
];

export function Layout({
  activeTab,
  onSelectTab,
  theme,
  onToggleTheme,
  version,
  readyStatus,
  auth,
  autoRefreshMs,
  onChangeAutoRefresh,
  onRefreshAll,
  onOpenPalette,
  onOpenAuthModal,
  onLogout,
  children,
}: {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  theme: ThemeMode;
  onToggleTheme: () => void;
  version: string;
  readyStatus: string;
  auth: AuthState;
  autoRefreshMs: number;
  onChangeAutoRefresh: (ms: number) => void;
  onRefreshAll: () => void;
  onOpenPalette: () => void;
  onOpenAuthModal: () => void;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const activeTitle = NAV_ITEMS.find((i) => i.id === activeTab)?.label || "Overview";

  const sidebarBody = (
    <div className="flex flex-col h-full justify-between p-3">
      <div className="space-y-4">
        <div className="flex items-center gap-2.5 px-2 py-1.5">
          <div className="w-7 h-7 rounded-lg bg-[var(--accent-soft)] border border-[color-mix(in_srgb,var(--accent)_35%,transparent)] flex items-center justify-center shrink-0">
            <Boxes className="w-4 h-4 text-[var(--accent)]" />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-[13px] tracking-tight truncate">MCP Gateway</div>
            <div className="text-[11px] font-mono text-[var(--text-muted)]">v{version}</div>
          </div>
        </div>

        <nav className="space-y-0.5" aria-label="Control Plane sections">
          {NAV_ITEMS.map((item) => {
            const isActive = item.id === activeTab;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onSelectTab(item.id);
                  setMobileNavOpen(false);
                }}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors cursor-pointer ${
                  isActive
                    ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                {item.icon}
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      <div className="space-y-2 pt-3 border-t border-[var(--border-hairline)]">
        <div className="px-2 py-1.5 rounded-lg bg-[var(--bg-subtle)] space-y-1">
          <div className="text-[11px] text-[var(--text-muted)]">Session</div>
          <div className="text-[12px] font-medium truncate">
            {auth.authenticated ? auth.clientName || auth.clientId || "Authenticated" : "Signed out"}
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:block w-[224px] shrink-0 border-r border-[var(--border-hairline)] bg-[var(--bg-surface)] sticky top-0 h-screen">
        {sidebarBody}
      </aside>

      {/* Mobile Drawer */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex">
          <div className="w-[240px] bg-[var(--bg-surface)] border-r border-[var(--border-hairline)] h-full relative">
            <button
              type="button"
              onClick={() => setMobileNavOpen(false)}
              className="absolute top-3 right-3 p-1 text-[var(--text-secondary)]"
            >
              <X className="w-4 h-4" />
            </button>
            {sidebarBody}
          </div>
          <div className="flex-1 bg-black/50" onClick={() => setMobileNavOpen(false)} />
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-20 h-14 px-4 md:px-6 border-b border-[var(--border-hairline)] bg-[color-mix(in_srgb,var(--bg-surface)_90%,transparent)] backdrop-blur-md flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              className="lg:hidden p-1.5 rounded-md border border-[var(--border-hairline)] text-[var(--text-secondary)]"
            >
              <Menu className="w-4 h-4" />
            </button>
            <h1 className="text-[14.5px] font-semibold tracking-tight truncate m-0">
              {activeTitle}
            </h1>
            <StatusBadge
              label={readyStatus.toUpperCase()}
              tone={readyStatus === "ready" ? "ok" : "warn"}
            />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={onOpenPalette}
              className="hidden sm:inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[12px] text-[var(--text-secondary)] cursor-pointer"
            >
              <Search className="w-3.5 h-3.5" />
              <span>Search</span>
              <kbd className="px-1.5 py-0.2 rounded bg-[var(--bg-subtle)] font-mono text-[10.5px]">
                ⌘K
              </kbd>
            </button>

            <select
              aria-label="Auto refresh interval"
              value={String(autoRefreshMs)}
              onChange={(e) => onChangeAutoRefresh(Number(e.target.value))}
              className="rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] px-2 py-1.5 text-[12px] text-[var(--text-secondary)] focus:outline-none"
            >
              <option value="0">Refresh: Off</option>
              <option value="15000">15s</option>
              <option value="60000">60s</option>
            </select>

            <button
              type="button"
              onClick={onRefreshAll}
              title="Refresh all data"
              className="p-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>

            <button
              type="button"
              onClick={onToggleTheme}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              aria-label="Toggle theme"
              className="p-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              {theme === "dark" ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            </button>

            {auth.authEnabled && !auth.authenticated ? (
              <button
                type="button"
                onClick={onOpenAuthModal}
                className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-semibold cursor-pointer"
              >
                Sign In
              </button>
            ) : (
              auth.authEnabled && (
                <button
                  type="button"
                  onClick={onLogout}
                  title="Sign out"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)] text-[12px] text-[var(--text-secondary)] cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden md:inline">Logout</span>
                </button>
              )
            )}
          </div>
        </header>

        <main className="flex-1 p-4 md:p-6 max-w-[1440px] w-full mx-auto space-y-5">
          {children}
        </main>
      </div>
    </div>
  );
}
