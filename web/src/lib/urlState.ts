import type { NavTab } from "../types";

export const VALID_TABS = new Set<NavTab>([
  "overview",
  "playground",
  "traces",
  "evals",
  "registry",
  "upstreams",
  "clients",
]);

const LEGACY_TAB_MAP: Record<string, { tab: NavTab; sub?: string }> = {
  chat: { tab: "playground", sub: "omnigent" },
  agent: { tab: "playground", sub: "agent" },
  skills: { tab: "registry", sub: "skills" },
  profiles: { tab: "upstreams", sub: "profiles" },
};

export interface UrlWorkbenchState {
  tab: NavTab;
  sub?: string | null;
  session?: string | null;
  tool?: string | null;
  server?: string | null;
  profile?: string | null;
  trace?: string | null;
  prompt?: string | null;
  version?: string | null;
}

/** Parse deep-link workbench state from /ui/<tab>?... (falling back to legacy routes and #<tab>). */
export function parseWorkbenchUrl(loc: Pick<Location, "pathname" | "search" | "hash">): UrlWorkbenchState {
  const parts = (loc.pathname || "").replace(/^\/ui\/?/, "").split("/").filter(Boolean);
  const pathRaw = (parts[0] || "").trim();
  const hashRaw = (loc.hash || "").replace("#", "").trim();
  const candidate = pathRaw || hashRaw;

  const params = new URLSearchParams(loc.search || "");
  let tab: NavTab = "overview";
  let sub: string | null = params.get("sub");

  if (candidate && VALID_TABS.has(candidate as NavTab)) {
    tab = candidate as NavTab;
  } else if (candidate && LEGACY_TAB_MAP[candidate]) {
    tab = LEGACY_TAB_MAP[candidate].tab;
    sub = sub || LEGACY_TAB_MAP[candidate].sub || null;
  }

  const session = params.get("session");
  return {
    tab,
    ...(sub ? { sub } : {}),
    ...(session !== null ? { session } : {}),
    tool: params.get("tool"),
    server: params.get("server"),
    profile: params.get("profile"),
    trace: params.get("trace"),
    prompt: params.get("prompt"),
    version: params.get("version"),
  };
}

/** Build a clean URL string for the active tab and contextual parameters. */
export function buildWorkbenchUrl(state: UrlWorkbenchState): string {
  const basePath = state.tab === "overview" ? "/ui" : `/ui/${state.tab}`;
  const params = new URLSearchParams();

  if (state.tab === "playground") {
    if (state.sub && state.sub !== "tools") params.set("sub", state.sub);
    if (state.session) params.set("session", state.session);
    if (state.profile) params.set("profile", state.profile);
    if (state.server) params.set("server", state.server);
    if (state.tool) params.set("tool", state.tool);
  } else if (state.tab === "traces") {
    if (state.trace) params.set("trace", state.trace);
  } else if (state.tab === "registry") {
    if (state.sub && state.sub !== "servers") params.set("sub", state.sub);
    if (state.prompt) params.set("prompt", state.prompt);
    if (state.prompt && state.version) params.set("version", state.version);
  } else if (state.tab === "upstreams") {
    if (state.sub && state.sub !== "upstreams") params.set("sub", state.sub);
  }

  const qs = params.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

/** Sync URL without full navigation. */
export function syncWorkbenchUrl(state: UrlWorkbenchState, push = false): void {
  if (typeof window === "undefined") return;
  const next = buildWorkbenchUrl(state);
  const current = `${window.location.pathname}${window.location.search}`;
  if (current === next && !window.location.hash) return;
  if (push) {
    window.history.pushState(null, "", next);
  } else {
    window.history.replaceState(null, "", next);
  }
}
