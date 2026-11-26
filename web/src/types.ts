export type NavTab =
  | "overview"
  | "playground"
  | "traces"
  | "registry"
  | "upstreams"
  | "clients";

export type ThemeMode = "dark" | "light";

export interface AuthState {
  authenticated: boolean;
  authEnabled: boolean;
  clientId: string | null;
  clientName: string | null;
  allowedServers: string[];
  authMethod?: string;
  mlflowMutationsEnabled: boolean;
  adminToolsEnabled?: boolean;
}

export interface ServerInventoryItem {
  key: string;
  slug: string;
  route: string;
  status: string;
  connectionStatus?: string;
  external?: boolean;
  transport?: string;
  target?: string;
  governance?: string;
  description?: string;
  registryName?: string | null;
  toolCount?: number;
  sampleTools?: string[];
  missingEnv?: string[];
  detail?: string | null;
  error?: string | null;
}

export interface ProfileInventoryItem {
  name: string;
  route: string;
  servers: string[];
  includesUpstreamMcp?: boolean;
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  composedRoute: string;
  defaultProfile: string;
  servers: ServerInventoryItem[];
  profiles: ProfileInventoryItem[];
}

export interface ReadyResponse {
  status: string;
  timestamp: string;
  checks: Record<
    string,
    {
      healthy?: boolean;
      reachable?: boolean;
      status_code?: number;
      url?: string;
      error?: string;
      detail?: string;
    }
  >;
}

export interface ToolItem {
  name: string;
  server: string;
  description: string;
  parameters: {
    type?: string;
    properties?: Record<string, SchemaProperty>;
    required?: string[];
    [key: string]: unknown;
  };
}

export interface SchemaProperty {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  format?: string;
  items?: SchemaProperty;
  [key: string]: unknown;
}

export interface ToolsResponse {
  totalTools: number;
  profileCounts: Record<string, number>;
  tools: ToolItem[];
}

export interface MCPContentBlock {
  type: "text" | "image" | "resource";
  text?: string | null;
  mimeType?: string | null;
  data?: string;
  uri?: string;
}

export interface CallToolResponse {
  ok: boolean;
  policyRefusal: boolean;
  server: string;
  tool: string;
  durationMs: number;
  truncated?: boolean;
  result?: unknown;
  structuredContent?: unknown;
  contentBlocks?: MCPContentBlock[];
  error?: string | { code?: string; message?: string };
}

export interface PlaygroundHistoryEntry {
  id: string;
  timestamp: string;
  server: string;
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  durationMs: number;
}

export interface TraceSummary {
  traceId: string;
  name?: string | null;
  state: string;
  durationMs: number | null;
  timestampMs?: number | null;
  server?: string | null;
  tool?: string | null;
  user?: string | null;
  modelId?: string | null;
  policyRefusal?: boolean;
  spanName?: string | null;
  requestPreview?: string | null;
  responsePreview?: string | null;
}

export interface EvalRunItem {
  run_id?: string;
  runId?: string;
  run_name?: string | null;
  runName?: string | null;
  timestamp_ms?: number | null;
  startTimeMs?: number | null;
  min_score?: number | null;
  minScore?: number | null;
  metrics?: Record<string, number>;
}

export interface ExperimentOption {
  id: string;
  name: string;
}

export interface TracesResponse {
  available: boolean;
  experiment?: string | null;
  experimentId?: string | null;
  experiments?: ExperimentOption[];
  traces: TraceSummary[];
  evalRuns?: EvalRunItem[];
  evalHistory?: EvalRunItem[];
  facets?: {
    servers?: string[];
    users?: string[];
    modelIds?: string[];
    models?: string[];
  };
  error?: string;
}

export interface TraceSpanItem {
  spanId: string;
  parentId?: string | null;
  name: string;
  spanType?: string;
  status?: string;
  durationMs?: number | null;
  attributes?: Record<string, unknown>;
  inputs?: unknown;
  outputs?: unknown;
  events?: Array<Record<string, unknown>>;
}

export interface TraceDetailResponse {
  traceId: string;
  state: string;
  durationMs: number | null;
  tags?: Record<string, string>;
  assessments?: Array<Record<string, unknown>>;
  spans: TraceSpanItem[];
}

export interface MCPRegistryServer {
  name: string;
  version?: string | null;
  url?: string | null;
  aliases?: Record<string, string>;
  tags?: Record<string, string>;
}

export interface RegistryPromptItem {
  name: string;
  versions?: Array<{ version: number | string; aliases?: string[] }>;
}

export interface RegistryResponse {
  available: boolean;
  mutationsEnabled?: boolean;
  experiment?: string | null;
  mcpServers: MCPRegistryServer[];
  prompts: RegistryPromptItem[];
  loggedModels: Array<{ modelId: string; name?: string | null; sourceRunId?: string | null }>;
  registeredModels: Array<{ name: string; latestVersions?: Array<{ version: string; currentStage?: string }> }>;
  error?: string;
}

export interface PromptDetailResponse {
  name: string;
  version?: string | number | null;
  template: string;
  commitMessage?: string | null;
  tags?: Record<string, string>;
  uri?: string | null;
}

export interface UpstreamConfigItem {
  slug: string;
  transport: "http" | "stdio";
  url?: string | null;
  headers?: Record<string, string>;
  command?: string | null;
  args?: string[];
  cwd?: string | null;
  env?: Record<string, string>;
  enabled: boolean;
  compose_into_full?: boolean;
  profiles: string[];
  timeout_s?: number;
  registry_name?: string | null;
  governance: string;
  description: string;
  route: string;
  connectionStatus: string;
  toolCount: number;
  sampleTools?: string[];
  missingEnv?: string[];
  detail?: string | null;
}

export interface WatchdogResponse {
  overall?: string;
  lastRunAt?: string | null;
  lastActions?: Record<string, string>;
  actions?: Record<string, string>;
  components?: Record<string, Record<string, unknown>>;
  evalRegression?: {
    status?: string;
    threshold?: number;
    run_id?: string | null;
    run_name?: string | null;
    min_score?: number | null;
    metrics?: Record<string, number>;
    failing_metrics?: Record<string, number>;
  };
  eval_regression?: {
    status?: string;
    threshold?: number;
    run_id?: string | null;
    run_name?: string | null;
    min_score?: number | null;
    metrics?: Record<string, number>;
    failing_metrics?: Record<string, number>;
  };
  lastRun?: string;
}
