export type NavTab =
  | "overview"
  | "playground"
  | "traces"
  | "evals"
  | "registry"
  | "upstreams"
  | "clients";

export type PlaygroundSubTab = "tools" | "agent" | "omnigent";
export type RegistrySubTab = "servers" | "prompts" | "models" | "skills";
export type UpstreamsSubTab = "upstreams" | "profiles";

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
  builtin?: boolean;
  allowTools?: string[];
  denyTools?: string[];
  toolCount?: number;
  estimatedSchemaTokens?: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  composedRoute: string;
  defaultProfile: string;
  mlflowUiUrl?: string | null;
  mlflowExperimentName?: string | null;
  mlflowExperimentId?: string | null;
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
  profileTokenBudgets?: Record<string, number>;
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
  traceId?: string | null;
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
  policyRefusal?: boolean;
  durationMs: number;
  responsePreview?: string;
  traceId?: string | null;
}

export interface PlaygroundPresetItem {
  id: string;
  name: string;
  server: string;
  tool: string;
  arguments: Record<string, unknown>;
  description: string;
  pinned: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PlaygroundReplayRequest {
  server: string;
  tool: string;
  arguments: Record<string, unknown>;
  presetName?: string;
  autoRun?: boolean;
  nonce: number;
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
  startTimeMs?: number | null;
  endTimeMs?: number | null;
  attributes?: Record<string, unknown>;
  inputs?: unknown;
  outputs?: unknown;
  events?: Array<Record<string, unknown>>;
}

export interface TraceDetailResponse {
  traceId: string;
  state: string;
  policyRefusal?: boolean;
  durationMs: number | null;
  timestampMs?: number | null;
  server?: string | null;
  tool?: string | null;
  user?: string | null;
  sessionId?: string | null;
  modelId?: string | null;
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

export interface PromptVersionSummary {
  version: number | string;
  aliases?: string[];
  commitMessage?: string | null;
  creationTimestamp?: number | null;
}

export interface RegistryPromptItem {
  name: string;
  description?: string | null;
  tags?: Record<string, string>;
  versions?: PromptVersionSummary[];
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
  rawToolCount?: number;
  exposedToolCount?: number;
  filteredOutCount?: number;
  allow_tools?: string[];
  deny_tools?: string[];
  authReasonCode?: string | null;
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

export interface ClientAuditDuplicate {
  client: string;
  path: string;
  server: string;
  target: string;
  reason: string;
}

export interface ClientAuditRepoShadow {
  repo: string;
  path: string;
  server: string;
  target: string;
  reason: string;
}

export interface ClientAuditResponse {
  clients: Array<{
    client: string;
    path: string;
    exists: boolean;
    error?: string | null;
    servers: Array<{
      name: string;
      target: string;
      shadowed: boolean;
      reason: string;
    }>;
  }>;
  duplicates: ClientAuditDuplicate[];
  repoShadows: ClientAuditRepoShadow[];
  summary: {
    totalClients: number;
    shadowedClientEntries: number;
    repoShadows: number;
  };
}

export interface SkillMatrixEntry {
  name: string;
  frontmatterName: string;
  description: string;
  sourceId: string;
  sourceKind: string;
  owner: string;
  canonicalPath: string;
  hash: string;
  atelierManaged: boolean;
  targets: Record<string, string>;
}

export interface SkillCollisionItem {
  group: string;
  kind: string;
  names?: string[];
  canonicalOwner?: string;
  occurrences: Array<{
    layer: string;
    path: string;
    origin?: string;
  }>;
  recommendation: string;
}

export interface SkillAuditResponse {
  available: boolean;
  manifestPath?: string;
  error?: string;
  summary?: {
    canonicalSkills: number;
    targets: number;
    syncedLinks: number;
    driftIssues: number;
    collisions: number;
    legacyItems: number;
    repoDualCopies: number;
    pluginSkills: number;
  };
  sourceWarnings?: string[];
  skills?: SkillMatrixEntry[];
  targets?: Record<
    string,
    {
      dir: string;
      exists: boolean;
      expectedCount: number;
      counts: Record<string, number>;
      extraUnmanaged: string[];
    }
  >;
  targetIssues?: Array<{
    target: string;
    skill: string;
    status: string;
    path: string;
    detail: string;
  }>;
  collisions?: SkillCollisionItem[];
  legacyItems?: Array<{
    root: string;
    skill: string;
    path: string;
    reason: string;
  }>;
  repoDualCopies?: Array<{
    repo: string;
    skill: string;
    paths: string[];
    allSymlinks: boolean;
  }>;
}

export interface SkillSyncResponse {
  dryRun: boolean;
  quarantineLegacy: boolean;
  quarantineBatch: string | null;
  manifestFile: string | null;
  manifestPath?: string;
  sourceWarnings: string[];
  actionCount: number;
  quarantinedCount: number;
  symlinkedCount: number;
  actions: Array<Record<string, unknown>>;
}

export interface OmnigentHostSummary {
  id: string;
  name?: string | null;
  status?: string | null;
}

export interface OmnigentStatus {
  ok: boolean;
  serverVersion?: string | null;
  singleUser?: boolean;
  onlineHosts: OmnigentHostSummary[];
  unreadInboxCount: number;
  automationsTotal: number;
  automationsActive: number;
  automationsPaused: number;
  baseUrl?: string;
  publicUrl?: string;
  mutationsEnabled: boolean;
}

export interface OmnigentProject {
  id: string;
  name: string;
  workspace?: string | null;
  agentId?: string | null;
  hostId?: string | null;
  useWorktree?: boolean | null;
  baseBranch?: string | null;
  icon?: string | null;
}

export interface OmnigentSessionRow {
  id: string;
  title?: string | null;
  status?: string | null;
  agentName?: string | null;
  projectId?: string | null;
  workspace?: string | null;
  pendingApprovals?: number;
  archived?: boolean;
  updatedAt?: number | null;
  sessionUrl?: string | null;
}

export interface OmnigentMessage {
  id?: string | null;
  role?: string | null;
  text: string;
  createdAt?: number | null;
}

export interface OmnigentPendingElicitation {
  id?: string;
  elicitation_id?: string;
  title?: string;
  message?: string;
  data?: {
    elicitation_id?: string;
    message?: string;
    tool_name?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface OmnigentSessionDetail {
  id: string;
  title?: string | null;
  status?: string | null;
  agentName?: string | null;
  llmModel?: string | null;
  projectId?: string | null;
  workspace?: string | null;
  gitBranch?: string | null;
  archived?: boolean;
  pendingElicitations: OmnigentPendingElicitation[];
  sessionUrl?: string | null;
  recentMessages: OmnigentMessage[];
}

export interface OmnigentWorkflow {
  id: string;
  name: string;
  description?: string | null;
}

export interface OmnigentInboxItem {
  id: string;
  status?: string | null;
  kind?: string | null;
  title?: string | null;
  topic?: string | null;
  bodyMd?: string | null;
  sourceSessionId?: string | null;
  createdAt?: number | null;
}

export interface OmnigentInboxResponse {
  unreadCount: number;
  items: OmnigentInboxItem[];
  pendingApprovalSessions: OmnigentSessionRow[];
}

export interface SkillRegistryCapability {
  supported: boolean;
  serverVersion?: string | null;
  requiredVersion?: string;
  trackingUri?: string;
  reason?: string | null;
}

export interface SkillRegistryVersion {
  version: string | number;
  status?: string | null;
  aliases?: string[];
  source?: string | null;
  creationTimestamp?: number | null;
  lastUpdatedTimestamp?: number | null;
}

export interface SkillRegistryItem {
  name: string;
  organization?: string | null;
  description?: string | null;
  latestVersion?: string | null;
  aliases?: Record<string, string | number>;
  tags?: Record<string, string>;
}

export interface SkillRegistryListResponse {
  supported: boolean;
  serverVersion?: string | null;
  requiredVersion?: string;
  reason?: string | null;
  skills: SkillRegistryItem[];
}

export interface SkillRegistryDetailResponse {
  supported?: boolean;
  name: string;
  organization?: string | null;
  description?: string | null;
  aliases?: Record<string, string | number>;
  tags?: Record<string, string>;
  versions: SkillRegistryVersion[];
  selectedVersion?: SkillRegistryVersion | null;
  skillMd?: string | null;
}

export interface AgentStatusResponse {
  reachable: boolean;
  agentUrl: string;
  defaultProfile: string;
  defaultModel: string;
  llmBaseUrl: string;
  maxToolRounds: number;
  detail?: string | null;
}

export interface EvalDatasetSummary {
  datasetId: string;
  name: string;
  experimentIds?: string[];
  recordCount?: number | null;
  lastUpdateTime?: number | null;
  createdBy?: string | null;
  tags?: Record<string, string>;
}

export interface EvalDatasetRecord {
  datasetRecordId?: string | null;
  inputs: Record<string, unknown>;
  expectations?: Record<string, unknown>;
}

export interface EvalDatasetDetailResponse {
  datasetId: string;
  name: string;
  recordCount: number;
  records: EvalDatasetRecord[];
  tags?: Record<string, string>;
}

export interface EvalRunRowItem {
  evalId?: string | null;
  traceId?: string | null;
  request?: string | null;
  response?: string | null;
  assessments?: Array<{
    name?: string | null;
    value?: unknown;
    rationale?: string | null;
    typesafeProbability?: number | null;
  }>;
  typesafeProbability?: number | null;
  passed?: boolean | null;
}

export interface EvalRunDetailResponse {
  runId: string;
  runName?: string | null;
  status?: string | null;
  startTimeMs?: number | null;
  endTimeMs?: number | null;
  minScore?: number | null;
  metrics: Record<string, number>;
  params: Record<string, string>;
  tags: Record<string, string>;
  rows: EvalRunRowItem[];
}

export interface EvalCompareDelta {
  metric: string;
  baseline: number | null;
  candidate: number | null;
  delta: number | null;
}

export interface EvalRunCompareResponse {
  runA: EvalRunDetailResponse;
  runB: EvalRunDetailResponse;
  deltas: EvalCompareDelta[];
}

export interface SecretsHealthResponse {
  onepasswordEnabled: boolean;
  mode: string;
  serviceAccountConfigured: boolean;
  cliPath: string;
  cliAvailable: boolean;
  allowedVaults: string[];
  cacheEntries: number;
  cacheTtlSeconds: number;
  lastSuccessAt?: string | null;
  lastErrorCode?: string | null;
  lastError?: string | null;
  authRequiredUpstreams: Array<{
    slug: string;
    detail?: string | null;
    authReasonCode?: string | null;
    missingEnv?: string[];
  }>;
}

export interface OpsMetricsBucket {
  ts: string;
  totalCalls: number;
  errorCount: number;
  errorRate: number;
  p50Ms: number;
  p95Ms: number;
}

export interface OpsMetricsSeriesResponse {
  bucketSeconds: number;
  buckets: OpsMetricsBucket[];
  totalRecorded: number;
}

export interface ActivityEvent {
  id: string;
  ts: string;
  kind: string;
  actor: string;
  server?: string | null;
  tool?: string | null;
  profile?: string | null;
  status: string;
  durationMs?: number | null;
  traceId?: string | null;
  summary: string;
  meta?: Record<string, unknown>;
}
