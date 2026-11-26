import type { NavTab } from "../types";

export const VALID_TABS = new Set<NavTab>([
  "overview",
  "chat",
  "playground",
  "traces",
  "registry",
  "upstreams",
  "clients",
  "skills",
]);

export interface UrlWorkbenchState {
  tab: NavTab;
  session?: string | null;
  tool?: string | null;
  server?: string | null;
  profile?: string | null;
  trace?: string | null;
  prompt?: string | null;
  version?: string | null;
}

/** Parse deep-link workbench state from /ui/<tab>?... (falling back to legacy #<tab>). */
export function parseWorkbenchUrl(loc: Pick<Location, "pathname" | "search" | "hash">): UrlWorkbenchState {
  const parts = (loc.pathname || "").replace(/^\/ui\/?/, "").split("/").filter(Boolean);
  const pathCandidate = parts[0] as NavTab | undefined;
  const hashCandidate = (loc.hash || "").replace("#", "").trim() as NavTab;
  const tab: NavTab =
    pathCandidate && VALID_TABS.has(pathCandidate)
      ? pathCandidate
      : VALID_TABS.has(hashCandidate)
        ? hashCandidate
        : "overview";

  const params = new URLSearchParams(loc.search || "");
  const session = params.get("session");
  return {
    tab,
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

  if (state.tab === "chat") {
    if (state.session) params.set("session", state.session);
  } else if (state.tab === "playground") {
    if (state.profile) params.set("profile", state.profile);
    if (state.server) params.set("server", state.server);
    if (state.tool) params.set("tool", state.tool);
  } else if (state.tab === "traces") {
    if (state.trace) params.set("trace", state.trace);
  } else if (state.tab === "registry") {
    if (state.prompt) params.set("prompt", state.prompt);
    if (state.prompt && state.version) params.set("version", state.version);
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
