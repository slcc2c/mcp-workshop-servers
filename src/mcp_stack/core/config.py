"""Configuration management using Pydantic Settings with optional YAML overlay."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ClientPolicy(BaseModel):
    """Per-client authorization and rate-limit policy."""

    client_id: str
    client_name: str
    allowed_servers: list[str] = Field(default_factory=lambda: ["*"])
    rate_limit_max: int = 100
    rate_limit_window_s: int = 60


class UpstreamServerConfig(BaseModel):
    """External HTTP or stdio MCP server federated through the gateway."""

    transport: Literal["http", "stdio"]
    url: str | None = None
    headers: dict[str, SecretStr] = Field(default_factory=dict)
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    cwd: Path | None = None
    env: dict[str, SecretStr] = Field(default_factory=dict)
    enabled: bool = True
    compose_into_full: bool = True
    profiles: list[str] = Field(default_factory=lambda: ["studio"])
    timeout_s: float = 5.0
    registry_name: str | None = None
    governance: str = "external-proxy"
    description: str = ""


class GatewaySettings(BaseModel):
    """HTTP + Streamable HTTP gateway configuration."""

    host: str = "127.0.0.1"
    port: int = 8090
    log_level: str = "INFO"
    log_json: bool = False
    auth_enabled: bool = False
    allow_unauthenticated_non_loopback: bool = False
    ui_session_ttl_s: int = 43200
    ui_session_secret: SecretStr | None = None
    eval_regression_threshold: float = 1.0
    admin_tools_enabled: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:*", "http://127.0.0.1:*"]
    )
    enabled_servers: list[str] = Field(
        default_factory=lambda: [
            "unity_catalog",
            "mlflow",
            "memory",
            "filesystem",
            "github",
            "docker",
            "postgresql",
            "redis",
            "mongodb",
            "neo4j",
            "kubernetes",
            "jupyter",
        ]
    )
    enable_photos_on_macos: bool = True
    enable_xcode_on_macos: bool = True
    default_client_profile: str = "core"
    profiles: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "discover": ["gateway"],
            "core": [
                "unity_catalog",
                "mlflow",
                "mlflow_upstream",
                "memory",
                "filesystem",
                "github",
            ],
            "data": [
                "unity_catalog",
                "mlflow",
                "postgresql",
                "redis",
                "mongodb",
                "neo4j",
                "jupyter",
            ],
            "ops": ["docker", "kubernetes", "filesystem", "github"],
            "macos": ["photos", "xcodebuild", "filesystem"],
        }
    )
    clients: dict[str, ClientPolicy] = Field(default_factory=dict)
    upstream_servers: dict[str, UpstreamServerConfig] = Field(default_factory=dict)

    @property
    def is_loopback(self) -> bool:
        return self.host.strip().lower() in LOOPBACK_HOSTS

    @property
    def effective_auth_enabled(self) -> bool:
        if self.auth_enabled:
            return True
        return bool(not self.is_loopback and not self.allow_unauthenticated_non_loopback)


class MLflowSettings(BaseModel):
    """MLflow 3.x tracking, tracing, registry, and upstream MCP proxy configuration."""

    tracking_uri: str = "http://localhost:5002"
    mcp_url: str = "http://localhost:9012/mcp"
    experiment_name: str = "mcp-workshop-servers"
    tracing_enabled: bool = True
    proxy_upstream_mcp: bool = True
    allow_mutations: bool = False
    registry_uri: str | None = None
    circuit_breaker_cooldown_s: float = 60.0


class UnityCatalogSettings(BaseModel):
    """Unity Catalog OSS or Databricks UC configuration."""

    mode: Literal["oss", "databricks"] = "oss"
    base_url: str = "http://localhost:8080"
    api_prefix: str = "/api/2.1/unity-catalog"
    token: SecretStr | None = None
    databricks_host: str | None = None
    databricks_profile: str | None = None
    allow_mutations: bool = False
    enable_function_execution: bool = True
    dynamic_function_tools: bool = True
    function_allowlist: list[str] = Field(
        default_factory=lambda: ["unity.default", "workshop.default"]
    )
    allow_obo_passthrough: bool = True
    execution_mode: Literal["sandbox", "local"] = "sandbox"
    volume_local_prefix_map: dict[str, str] = Field(default_factory=dict)

    @property
    def effective_base_url(self) -> str:
        if self.mode == "databricks" and self.databricks_host:
            return self.databricks_host.rstrip("/")
        return self.base_url.rstrip("/")

    @property
    def effective_api_base(self) -> str:
        prefix = "/" + self.api_prefix.strip("/")
        return f"{self.effective_base_url}{prefix}"

    @property
    def effective_registry_uri(self) -> str:
        if self.mode == "databricks":
            return "databricks-uc"
        return f"uc:{self.effective_base_url}"


class MemorySettings(BaseModel):
    """SQLite + FTS5 memory server configuration."""

    db_path: Path = Path("data/memory.db")
    legacy_json_path: Path = Path("data/memory.json")
    uc_export_volume: str | None = None


class FilesystemSettings(BaseModel):
    """Sandboxed filesystem server configuration."""

    allowed_paths: list[Path] = Field(default_factory=lambda: [Path.cwd()])
    blocked_paths: list[str] = Field(
        default_factory=lambda: ["/etc", "/var", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc"]
    )
    max_file_size: int = 10_485_760


class GitHubSettings(BaseModel):
    """GitHub REST v3 server configuration."""

    token: SecretStr | None = None
    api_url: str = "https://api.github.com"


class DockerSettings(BaseModel):
    """Docker Engine MCP server configuration."""

    host: str = "unix:///var/run/docker.sock"
    default_memory: str = "2g"
    default_cpus: float = 1.0
    allowed_images: list[str] = Field(
        default_factory=lambda: [
            "node:*",
            "python:*",
            "nginx:*",
            "redis:*",
            "postgres:*",
            "mysql:*",
            "ubuntu:*",
            "alpine:*",
            "mongo:*",
            "hello-world:*",
            "ghcr.io/astral-sh/*",
        ]
    )


class PhotosSettings(BaseModel):
    """macOS Apple Photos MCP server configuration."""

    export_root: Path | None = None
    timeout_seconds: float = 45.0


class PostgreSQLSettings(BaseModel):
    """PostgreSQL MCP server configuration."""

    url: SecretStr | None = None
    allow_mutations: bool = False
    max_rows: int = 1000
    timeout_seconds: float = 30.0


class RedisSettings(BaseModel):
    """Redis MCP server configuration."""

    url: SecretStr | None = None
    allow_mutations: bool = False
    max_keys: int = 500
    timeout_seconds: float = 10.0


class MongoDBSettings(BaseModel):
    """MongoDB MCP server configuration."""

    uri: SecretStr | None = None
    database: str = "mcp_workshop"
    allow_mutations: bool = False
    max_docs: int = 500
    timeout_seconds: float = 10.0


class Neo4jSettings(BaseModel):
    """Neo4j graph database MCP server configuration."""

    uri: str | None = None
    user: str = "neo4j"
    password: SecretStr | None = None
    database: str = "neo4j"
    allow_mutations: bool = False
    max_records: int = 500
    timeout_seconds: float = 15.0


class KubernetesSettings(BaseModel):
    """Kubernetes cluster MCP server configuration."""

    kubeconfig: Path | None = None
    context: str | None = None
    allowed_namespaces: list[str] = Field(default_factory=lambda: ["default"])
    allow_mutations: bool = False
    timeout_seconds: float = 30.0


class JupyterSettings(BaseModel):
    """Jupyter notebook and kernel MCP server configuration."""

    notebook_dir: Path | None = None
    allow_execution: bool = False
    kernel_timeout_seconds: float = 30.0
    max_output_chars: int = 50_000


class XcodeSettings(BaseModel):
    """macOS Xcode / Swift / Simulator MCP server configuration."""

    allowed_roots: list[Path] | None = None
    allow_mutations: bool = False
    timeout_seconds: float = 300.0


class SecretsSettings(BaseModel):
    """Secret resolution & optional 1Password CLI configuration."""

    onepassword_enabled: bool = False
    onepassword_cli: str = "op"
    onepassword_allowed_vaults: list[str] = Field(
        default_factory=lambda: ["AI", "Server-Configurations"]
    )
    cache_ttl_seconds: int = 300


class MCPStackSettings(BaseSettings):
    """Top-level configuration aggregated from env, .env, and optional YAML."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    mlflow: MLflowSettings = Field(default_factory=MLflowSettings)
    unity_catalog: UnityCatalogSettings = Field(default_factory=UnityCatalogSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    filesystem: FilesystemSettings = Field(default_factory=FilesystemSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    docker: DockerSettings = Field(default_factory=DockerSettings)
    photos: PhotosSettings = Field(default_factory=PhotosSettings)
    postgresql: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    mongodb: MongoDBSettings = Field(default_factory=MongoDBSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    kubernetes: KubernetesSettings = Field(default_factory=KubernetesSettings)
    jupyter: JupyterSettings = Field(default_factory=JupyterSettings)
    xcode: XcodeSettings = Field(default_factory=XcodeSettings)
    secrets: SecretsSettings = Field(default_factory=SecretsSettings)

    @property
    def effective_mlflow_registry_uri(self) -> str:
        return self.mlflow.registry_uri or self.unity_catalog.effective_registry_uri


def _parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts


def _parse_kv_map(value: str | None) -> dict[str, str] | None:
    if value is None:
        return None
    mapping: dict[str, str] = {}
    for item in value.split(","):
        cleaned = item.strip()
        if not cleaned or "=" not in cleaned:
            continue
        k, v = cleaned.split("=", 1)
        if k.strip() and v.strip():
            mapping[k.strip()] = v.strip()
    return mapping


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _default_clients() -> dict[str, ClientPolicy]:
    specs = [
        ("antigravity", "Antigravity IDE", "MCP_ANTIGRAVITY_AUTH_TOKEN", ["*"], 200),
        ("gemini", "Gemini CLI", "MCP_GEMINI_AUTH_TOKEN", ["*"], 200),
        ("claude", "Claude Desktop / Code", "MCP_CLAUDE_AUTH_TOKEN", ["*"], 200),
        ("cursor", "Cursor IDE", "MCP_CURSOR_AUTH_TOKEN", ["*"], 150),
        ("codex", "Codex CLI", "MCP_CODEX_AUTH_TOKEN", ["*"], 200),
        ("openai", "OpenAI", "MCP_OPENAI_AUTH_TOKEN", ["github", "filesystem", "memory"], 100),
        ("default", "Default Client", "MCP_DEFAULT_AUTH_TOKEN", ["github", "filesystem"], 50),
        ("legacy", "Legacy Client", "AUTH_TOKEN", ["*"], 100),
    ]
    clients: dict[str, ClientPolicy] = {}
    for client_id, client_name, env_var, allowed, rate_max in specs:
        token = os.getenv(env_var, "").strip()
        if token:
            clients[token] = ClientPolicy(
                client_id=client_id,
                client_name=client_name,
                allowed_servers=allowed,
                rate_limit_max=rate_max,
            )
    return clients


def load_settings(config_file: Path | None = None, *, load_dotenv: bool = True) -> MCPStackSettings:
    """Load settings from optional YAML overlay, .env, and flat environment variables."""
    if load_dotenv:
        from dotenv import load_dotenv as _load_dotenv

        _load_dotenv(override=False)

    yaml_path = config_file
    if yaml_path is None:
        env_cfg = os.getenv("MCP_CONFIG_FILE")
        if env_cfg:
            yaml_path = Path(env_cfg)
        elif Path("config/services.yaml").exists():
            yaml_path = Path("config/services.yaml")

    raw: dict[str, Any] = {}
    if yaml_path is not None and yaml_path.exists():
        loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded

    local_cfg_raw = os.getenv("MCP_LOCAL_CONFIG_PATH")
    local_yaml_path = Path(local_cfg_raw) if local_cfg_raw else Path("config/gateway.local.yaml")
    if local_yaml_path.exists():
        loaded_local = yaml.safe_load(local_yaml_path.read_text(encoding="utf-8"))
        if isinstance(loaded_local, dict):
            raw = _deep_merge(raw, loaded_local)

    env_overrides: dict[str, Any] = {
        "gateway": {},
        "mlflow": {},
        "unity_catalog": {},
        "memory": {},
        "filesystem": {},
        "github": {},
        "docker": {},
        "photos": {},
        "postgresql": {},
        "redis": {},
        "mongodb": {},
        "neo4j": {},
        "kubernetes": {},
        "jupyter": {},
        "xcode": {},
        "secrets": {},
    }

    if val := os.getenv("MCP_GATEWAY_HOST"):
        env_overrides["gateway"]["host"] = val
    if val := os.getenv("MCP_GATEWAY_PORT"):
        env_overrides["gateway"]["port"] = int(val)
    if val := os.getenv("MCP_LOG_LEVEL"):
        env_overrides["gateway"]["log_level"] = val
    if (b := _parse_bool(os.getenv("MCP_LOG_JSON"))) is not None:
        env_overrides["gateway"]["log_json"] = b
    if (b := _parse_bool(os.getenv("MCP_AUTH_ENABLED"))) is not None:
        env_overrides["gateway"]["auth_enabled"] = b
    if (b := _parse_bool(os.getenv("MCP_ALLOW_UNAUTHENTICATED_NON_LOOPBACK"))) is not None:
        env_overrides["gateway"]["allow_unauthenticated_non_loopback"] = b
    if val := os.getenv("GATEWAY_UI_SESSION_TTL_S"):
        env_overrides["gateway"]["ui_session_ttl_s"] = int(val)
    if val := os.getenv("GATEWAY_UI_SESSION_SECRET"):
        env_overrides["gateway"]["ui_session_secret"] = val
    if val := os.getenv("GATEWAY_EVAL_REGRESSION_THRESHOLD"):
        env_overrides["gateway"]["eval_regression_threshold"] = float(val)
    if (b := _parse_bool(os.getenv("MCP_GATEWAY_ADMIN_TOOLS_ENABLED"))) is not None:
        env_overrides["gateway"]["admin_tools_enabled"] = b
    if (items := _split_csv(os.getenv("MCP_ENABLED_SERVERS"))) is not None:
        env_overrides["gateway"]["enabled_servers"] = items
    if (items := _split_csv(os.getenv("MCP_CORS_ORIGINS"))) is not None:
        env_overrides["gateway"]["cors_origins"] = items
    if (b := _parse_bool(os.getenv("MCP_ENABLE_PHOTOS_ON_MACOS"))) is not None:
        env_overrides["gateway"]["enable_photos_on_macos"] = b
    if (b := _parse_bool(os.getenv("MCP_ENABLE_XCODE_ON_MACOS"))) is not None:
        env_overrides["gateway"]["enable_xcode_on_macos"] = b
    if val := os.getenv("MCP_DEFAULT_CLIENT_PROFILE"):
        env_overrides["gateway"]["default_client_profile"] = val.strip()
    if val := os.getenv("MCP_PROFILES_JSON"):
        loaded_profiles = json.loads(val)
        if not isinstance(loaded_profiles, dict) or not all(
            isinstance(k, str)
            and isinstance(v, list)
            and all(isinstance(s, str) for s in v)
            for k, v in loaded_profiles.items()
        ):
            raise ValueError("MCP_PROFILES_JSON must map profile names to lists of server keys")
        env_overrides["gateway"]["profiles"] = loaded_profiles

    if val := os.getenv("MLFLOW_TRACKING_URI"):
        env_overrides["mlflow"]["tracking_uri"] = val
    if val := os.getenv("MLFLOW_MCP_URL"):
        env_overrides["mlflow"]["mcp_url"] = val
    if val := os.getenv("MLFLOW_EXPERIMENT_NAME"):
        env_overrides["mlflow"]["experiment_name"] = val
    if (b := _parse_bool(os.getenv("MLFLOW_TRACING_ENABLED"))) is not None:
        env_overrides["mlflow"]["tracing_enabled"] = b
    if (b := _parse_bool(os.getenv("MLFLOW_PROXY_UPSTREAM_MCP"))) is not None:
        env_overrides["mlflow"]["proxy_upstream_mcp"] = b
    if (b := _parse_bool(os.getenv("MLFLOW_ALLOW_MUTATIONS"))) is not None:
        env_overrides["mlflow"]["allow_mutations"] = b
    if val := os.getenv("MLFLOW_REGISTRY_URI"):
        env_overrides["mlflow"]["registry_uri"] = val
    if val := os.getenv("MLFLOW_CIRCUIT_BREAKER_COOLDOWN_S"):
        env_overrides["mlflow"]["circuit_breaker_cooldown_s"] = float(val)

    if val := os.getenv("UC_MODE"):
        env_overrides["unity_catalog"]["mode"] = val
    if val := os.getenv("UC_BASE_URL"):
        env_overrides["unity_catalog"]["base_url"] = val
    if val := os.getenv("UC_API_PREFIX"):
        env_overrides["unity_catalog"]["api_prefix"] = val
    if val := os.getenv("UC_TOKEN"):
        env_overrides["unity_catalog"]["token"] = val
    if val := os.getenv("UC_DATABRICKS_HOST"):
        env_overrides["unity_catalog"]["databricks_host"] = val
    if val := os.getenv("UC_DATABRICKS_PROFILE"):
        env_overrides["unity_catalog"]["databricks_profile"] = val
    if (b := _parse_bool(os.getenv("UC_ALLOW_MUTATIONS"))) is not None:
        env_overrides["unity_catalog"]["allow_mutations"] = b
    if (b := _parse_bool(os.getenv("UC_ENABLE_FUNCTION_EXECUTION"))) is not None:
        env_overrides["unity_catalog"]["enable_function_execution"] = b
    if (b := _parse_bool(os.getenv("UC_DYNAMIC_FUNCTION_TOOLS"))) is not None:
        env_overrides["unity_catalog"]["dynamic_function_tools"] = b
    if (items := _split_csv(os.getenv("UC_FUNCTION_ALLOWLIST"))) is not None:
        env_overrides["unity_catalog"]["function_allowlist"] = items
    if (b := _parse_bool(os.getenv("UC_ALLOW_OBO_PASSTHROUGH"))) is not None:
        env_overrides["unity_catalog"]["allow_obo_passthrough"] = b
    if val := os.getenv("UC_EXECUTION_MODE"):
        env_overrides["unity_catalog"]["execution_mode"] = val
    if (kv := _parse_kv_map(os.getenv("UC_VOLUME_LOCAL_PREFIX_MAP"))) is not None:
        env_overrides["unity_catalog"]["volume_local_prefix_map"] = kv

    if val := os.getenv("MEMORY_DB_PATH"):
        env_overrides["memory"]["db_path"] = Path(val)
    if val := os.getenv("MEMORY_LEGACY_JSON_PATH"):
        env_overrides["memory"]["legacy_json_path"] = Path(val)
    if val := os.getenv("MEMORY_UC_EXPORT_VOLUME"):
        env_overrides["memory"]["uc_export_volume"] = val

    if (items := _split_csv(os.getenv("ALLOWED_PATHS"))) is not None:
        env_overrides["filesystem"]["allowed_paths"] = [Path(p) for p in items]
    if val := os.getenv("MAX_FILE_SIZE"):
        env_overrides["filesystem"]["max_file_size"] = int(val)

    gh_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") or os.getenv("GITHUB_TOKEN")
    if gh_token:
        env_overrides["github"]["token"] = gh_token
    if val := os.getenv("GITHUB_API_URL"):
        env_overrides["github"]["api_url"] = val

    if val := os.getenv("DOCKER_HOST"):
        env_overrides["docker"]["host"] = val
    if val := os.getenv("DOCKER_DEFAULT_MEMORY"):
        env_overrides["docker"]["default_memory"] = val
    if val := os.getenv("DOCKER_DEFAULT_CPUS"):
        env_overrides["docker"]["default_cpus"] = float(val)
    if (items := _split_csv(os.getenv("DOCKER_ALLOWED_IMAGES"))) is not None:
        env_overrides["docker"]["allowed_images"] = items

    if val := os.getenv("PHOTOS_EXPORT_ROOT"):
        env_overrides["photos"]["export_root"] = Path(val)
    if val := os.getenv("PHOTOS_TIMEOUT_SECONDS"):
        env_overrides["photos"]["timeout_seconds"] = float(val)

    if val := os.getenv("POSTGRES_URL"):
        env_overrides["postgresql"]["url"] = val
    if (b := _parse_bool(os.getenv("POSTGRES_ALLOW_MUTATIONS"))) is not None:
        env_overrides["postgresql"]["allow_mutations"] = b
    if val := os.getenv("POSTGRES_MAX_ROWS"):
        env_overrides["postgresql"]["max_rows"] = int(val)
    if val := os.getenv("POSTGRES_TIMEOUT_S"):
        env_overrides["postgresql"]["timeout_seconds"] = float(val)

    if val := os.getenv("REDIS_URL"):
        env_overrides["redis"]["url"] = val
    if (b := _parse_bool(os.getenv("REDIS_ALLOW_MUTATIONS"))) is not None:
        env_overrides["redis"]["allow_mutations"] = b
    if val := os.getenv("REDIS_MAX_KEYS"):
        env_overrides["redis"]["max_keys"] = int(val)

    if val := os.getenv("MONGODB_URI"):
        env_overrides["mongodb"]["uri"] = val
    if val := os.getenv("MONGODB_DATABASE"):
        env_overrides["mongodb"]["database"] = val
    if (b := _parse_bool(os.getenv("MONGODB_ALLOW_MUTATIONS"))) is not None:
        env_overrides["mongodb"]["allow_mutations"] = b
    if val := os.getenv("MONGODB_MAX_DOCS"):
        env_overrides["mongodb"]["max_docs"] = int(val)

    if val := os.getenv("NEO4J_URI"):
        env_overrides["neo4j"]["uri"] = val
    if val := os.getenv("NEO4J_USER"):
        env_overrides["neo4j"]["user"] = val
    if val := os.getenv("NEO4J_PASSWORD"):
        env_overrides["neo4j"]["password"] = val
    if val := os.getenv("NEO4J_DATABASE"):
        env_overrides["neo4j"]["database"] = val
    if (b := _parse_bool(os.getenv("NEO4J_ALLOW_MUTATIONS"))) is not None:
        env_overrides["neo4j"]["allow_mutations"] = b

    if val := os.getenv("KUBECONFIG"):
        env_overrides["kubernetes"]["kubeconfig"] = Path(val)
    if val := os.getenv("K8S_CONTEXT"):
        env_overrides["kubernetes"]["context"] = val
    if (items := _split_csv(os.getenv("K8S_ALLOWED_NAMESPACES"))) is not None:
        env_overrides["kubernetes"]["allowed_namespaces"] = items
    if (b := _parse_bool(os.getenv("K8S_ALLOW_MUTATIONS"))) is not None:
        env_overrides["kubernetes"]["allow_mutations"] = b

    if val := os.getenv("JUPYTER_NOTEBOOK_DIR"):
        env_overrides["jupyter"]["notebook_dir"] = Path(val)
    if (b := _parse_bool(os.getenv("JUPYTER_ALLOW_EXECUTION"))) is not None:
        env_overrides["jupyter"]["allow_execution"] = b
    if val := os.getenv("JUPYTER_KERNEL_TIMEOUT_S"):
        env_overrides["jupyter"]["kernel_timeout_seconds"] = float(val)

    if (items := _split_csv(os.getenv("XCODE_ALLOWED_ROOTS"))) is not None:
        env_overrides["xcode"]["allowed_roots"] = [Path(p) for p in items]
    if (b := _parse_bool(os.getenv("XCODE_ALLOW_MUTATIONS"))) is not None:
        env_overrides["xcode"]["allow_mutations"] = b
    if val := os.getenv("XCODE_TIMEOUT_S"):
        env_overrides["xcode"]["timeout_seconds"] = float(val)

    if (b := _parse_bool(os.getenv("OP_ENABLED"))) is not None:
        env_overrides["secrets"]["onepassword_enabled"] = b
    if val := os.getenv("OP_CLI_PATH"):
        env_overrides["secrets"]["onepassword_cli"] = val
    if (items := _split_csv(os.getenv("OP_ALLOWED_VAULTS"))) is not None:
        env_overrides["secrets"]["onepassword_allowed_vaults"] = items
    if val := os.getenv("OP_CACHE_TTL_SECONDS"):
        env_overrides["secrets"]["cache_ttl_seconds"] = int(val)

    cleaned_overrides = {k: v for k, v in env_overrides.items() if v}
    merged = _deep_merge(raw, cleaned_overrides)

    settings = MCPStackSettings(**merged)
    if not settings.gateway.clients:
        settings.gateway.clients = _default_clients()
    return settings


_SENSITIVE_KEY_MARKERS = ("auth", "token", "secret", "key", "password")


def _is_secret_reference(raw_value: str) -> bool:
    stripped = raw_value.strip()
    if stripped.lower().startswith("bearer "):
        stripped = stripped[7:].strip()
    return stripped.startswith(("env:", "op://"))


def validate_upstream_secret_refs(cfg: UpstreamServerConfig) -> None:
    """Reject raw secret literals in upstream headers and sensitive env vars."""
    for h_key, h_val in cfg.headers.items():
        if any(m in h_key.lower() for m in _SENSITIVE_KEY_MARKERS):
            raw = h_val.get_secret_value()
            if raw.strip() and not _is_secret_reference(raw):
                raise ValueError(
                    f"Header '{h_key}' must use env:VAR or op://vault/item/field, not a raw secret"
                )
    for e_key, e_val in cfg.env.items():
        if any(m in e_key.lower() for m in _SENSITIVE_KEY_MARKERS):
            raw = e_val.get_secret_value()
            if raw.strip() and not _is_secret_reference(raw):
                raise ValueError(
                    f"Env '{e_key}' must use env:VAR or op://vault/item/field, not a raw secret"
                )


def serialize_upstream_config(cfg: UpstreamServerConfig) -> dict[str, Any]:
    """Serialize an UpstreamServerConfig without exposing resolved secrets."""
    validate_upstream_secret_refs(cfg)
    payload: dict[str, Any] = {
        "transport": cfg.transport,
        "enabled": cfg.enabled,
        "compose_into_full": cfg.compose_into_full,
        "profiles": list(cfg.profiles),
        "timeout_s": cfg.timeout_s,
        "governance": cfg.governance,
    }
    if cfg.url:
        payload["url"] = cfg.url
    if cfg.headers:
        payload["headers"] = {k: v.get_secret_value() for k, v in cfg.headers.items()}
    if cfg.command:
        payload["command"] = cfg.command
    if cfg.args:
        payload["args"] = list(cfg.args)
    if cfg.cwd is not None:
        payload["cwd"] = str(cfg.cwd)
    if cfg.env:
        payload["env"] = {k: v.get_secret_value() for k, v in cfg.env.items()}
    if cfg.registry_name:
        payload["registry_name"] = cfg.registry_name
    if cfg.description:
        payload["description"] = cfg.description
    return payload


def save_local_upstreams(
    path: Path,
    upstreams: dict[str, UpstreamServerConfig],
) -> Path:
    """Atomically write upstream_servers into gitignored local YAML config."""
    import tempfile

    raw: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    gw_sec = raw.setdefault("gateway", {})
    if not isinstance(gw_sec, dict):
        gw_sec = {}
        raw["gateway"] = gw_sec

    serialized: dict[str, Any] = {}
    for slug, cfg in upstreams.items():
        clean_slug = slug.strip().replace("_", "-").lower()
        serialized[clean_slug] = serialize_upstream_config(cfg)
    gw_sec["upstream_servers"] = serialized

    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(raw, sort_keys=False)
    fd, tmp_name = tempfile.mkstemp(prefix=".gateway-local-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return path
