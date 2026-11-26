import type {
  AuthState,
  CallToolResponse,
  HealthResponse,
  PlaygroundPresetItem,
  PromptDetailResponse,
  ReadyResponse,
  RegistryResponse,
  ToolsResponse,
  TraceDetailResponse,
  TracesResponse,
  UpstreamConfigItem,
  WatchdogResponse,
} from "../types";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  const method = String(options.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    headers.set("X-Requested-With", "mcp-ui");
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }
  const res = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const text = await res.text();
  let json: any = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  if (!res.ok) {
    const errObj = json?.error;
    const msg =
      typeof errObj === "string"
        ? errObj
        : errObj?.message || `HTTP ${res.status} ${res.statusText}`;
    throw new ApiError(msg, res.status, typeof errObj === "object" ? errObj?.code : undefined);
  }
  return json as T;
}

export const api = {
  authMe: () => apiFetch<AuthState>("/api/v1/auth/me"),
  loginToken: (token: string) =>
    apiFetch<AuthState>("/api/v1/auth/session", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  logout: () => apiFetch<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),
  health: () => apiFetch<HealthResponse>("/health"),
  ready: () => apiFetch<ReadyResponse>("/ready"),
  watchdog: () => apiFetch<WatchdogResponse>("/api/v1/watchdog"),
  tools: (params?: { profile?: string; server?: string; q?: string }) => {
    const usp = new URLSearchParams();
    if (params?.profile) usp.set("profile", params.profile);
    if (params?.server) usp.set("server", params.server);
    if (params?.q) usp.set("q", params.q);
    const qs = usp.toString();
    return apiFetch<ToolsResponse>(`/api/v1/tools${qs ? `?${qs}` : ""}`);
  },
  callTool: (server: string, tool: string, args: Record<string, unknown>) =>
    apiFetch<CallToolResponse>("/api/v1/actions/call-tool", {
      method: "POST",
      body: JSON.stringify({ server, tool, arguments: args }),
    }),
  runUcRefresh: () => apiFetch<Record<string, unknown>>("/api/v1/actions/refresh-uc", { method: "POST" }),
  runWatchdog: (dryRun = true) =>
    apiFetch<WatchdogResponse>("/api/v1/actions/watchdog", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    }),
  runTraceEval: (limit = 20) =>
    apiFetch<Record<string, unknown>>("/api/v1/actions/eval", {
      method: "POST",
      body: JSON.stringify({ limit }),
    }),
  runBenchmark: (withLlmJudge = false, judgeModel?: string) =>
    apiFetch<Record<string, unknown>>("/api/v1/actions/benchmark", {
      method: "POST",
      body: JSON.stringify({
        with_llm_judge: withLlmJudge,
        ...(judgeModel ? { judge_model: judgeModel } : {}),
      }),
    }),
  traces: (params: Record<string, string>) => {
    const usp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v) usp.set(k, v);
    }
    const qs = usp.toString();
    return apiFetch<TracesResponse>(`/api/v1/traces${qs ? `?${qs}` : ""}`);
  },
  traceDetail: (traceId: string, experimentId?: string | null) => {
    const qs = experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : "";
    return apiFetch<TraceDetailResponse>(`/api/v1/traces/${encodeURIComponent(traceId)}${qs}`);
  },
  logFeedback: (traceId: string, body: { name: string; value: boolean | string; rationale?: string }) =>
    apiFetch<Record<string, unknown>>(`/api/v1/traces/${encodeURIComponent(traceId)}/feedback`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  logExpectation: (traceId: string, body: { name: string; value: string }) =>
    apiFetch<Record<string, unknown>>(`/api/v1/traces/${encodeURIComponent(traceId)}/expectation`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  setTraceTag: (traceId: string, body: { key: string; value: string }) =>
    apiFetch<Record<string, unknown>>(`/api/v1/traces/${encodeURIComponent(traceId)}/tag`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  promoteTraceDataset: (traceId: string) =>
    apiFetch<Record<string, unknown>>(
      `/api/v1/traces/${encodeURIComponent(traceId)}/promote-to-dataset`,
      { method: "POST" },
    ),
  presets: () => apiFetch<{ path: string; presets: PlaygroundPresetItem[] }>("/api/v1/presets"),
  createPreset: (body: {
    name: string;
    server: string;
    tool: string;
    arguments: Record<string, unknown>;
    description?: string;
    pinned?: boolean;
  }) =>
    apiFetch<{ preset: PlaygroundPresetItem }>("/api/v1/presets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updatePreset: (
    id: string,
    body: Partial<{
      name: string;
      server: string;
      tool: string;
      arguments: Record<string, unknown>;
      description: string;
      pinned: boolean;
    }>,
  ) =>
    apiFetch<{ preset: PlaygroundPresetItem }>(`/api/v1/presets/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deletePreset: (id: string) =>
    apiFetch<{ deleted: string }>(`/api/v1/presets/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  registry: () => apiFetch<RegistryResponse>("/api/v1/mlflow/registry"),
  promptDetail: (name: string, versionOrAlias = "latest") =>
    apiFetch<PromptDetailResponse>(
      `/api/v1/mlflow/prompts/${encodeURIComponent(name)}?version_or_alias=${encodeURIComponent(versionOrAlias)}`,
    ),
  createPrompt: (body: { name: string; template: string; commitMessage?: string; alias?: string }) =>
    apiFetch<PromptDetailResponse & { created?: boolean }>("/api/v1/mlflow/prompts", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  promotePromptAlias: (name: string, version: number | string, alias = "production") =>
    apiFetch<Record<string, unknown>>(
      `/api/v1/mlflow/prompts/${encodeURIComponent(name)}/alias`,
      {
        method: "POST",
        body: JSON.stringify({ alias, version: Number(version) }),
      },
    ),
  deletePromptAlias: (name: string, alias: string) =>
    apiFetch<{ deleted: boolean; name: string; alias: string }>(
      `/api/v1/mlflow/prompts/${encodeURIComponent(name)}/alias/${encodeURIComponent(alias)}`,
      { method: "DELETE" },
    ),
  promoteModelAlias: (name: string, version: string, alias = "production") =>
    apiFetch<Record<string, unknown>>(
      `/api/v1/mlflow/models/${encodeURIComponent(name)}/alias`,
      {
        method: "POST",
        body: JSON.stringify({ alias, version }),
      },
    ),
  upstreams: () => apiFetch<{ configPath: string; upstreams: UpstreamConfigItem[] }>("/api/v1/upstreams"),
  upsertUpstream: (slug: string, payload: Record<string, unknown>) =>
    apiFetch<{ upstream: UpstreamConfigItem }>(`/api/v1/upstreams/${encodeURIComponent(slug)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteUpstream: (slug: string) =>
    apiFetch<{ deleted: string }>(`/api/v1/upstreams/${encodeURIComponent(slug)}`, {
      method: "DELETE",
    }),
  probeUpstream: (slug: string) =>
    apiFetch<{ upstream: UpstreamConfigItem }>(
      `/api/v1/upstreams/${encodeURIComponent(slug)}/probe`,
      { method: "POST" },
    ),
  clientConfigs: (profile?: string) =>
    apiFetch<{
      defaultProfile: string;
      selectedProfile: string;
      profiles: Array<{ name: string; route: string; servers: string[] }>;
      configs: Record<string, string>;
    }>(`/api/v1/clients/configs${profile ? `?profile=${encodeURIComponent(profile)}` : ""}`),
  verifyClient: (client: string, profile?: string) =>
    apiFetch<{
      ok: boolean;
      client: string;
      profile: string;
      url: string;
      authStatus: string;
      protocolVersion?: string;
      toolCount?: number;
      latencyMs: number;
      error?: string;
    }>("/api/v1/clients/verify", {
      method: "POST",
      body: JSON.stringify({ client, ...(profile ? { profile } : {}) }),
    }),
};
