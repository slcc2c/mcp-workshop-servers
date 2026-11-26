"""Typer CLI for mcp-workshop-stack (serve, doctor, registry, config)."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
import typer
import uvicorn

from mcp_stack import __version__
from mcp_stack.client_configs import (
    audit_client_configs,
    discover_live_tool_catalog,
    generate_client_configs,
    install_client_configs,
    install_shell_hook,
    verify_client_connection,
    write_client_configs,
)
from mcp_stack.core.config import load_settings
from mcp_stack.core.logging import configure_logging
from mcp_stack.evals import (
    GOLDEN_DATASET_NAME,
    register_experiment_scorers,
    run_golden_benchmark,
    run_trace_evaluation,
    sync_golden_dataset,
)
from mcp_stack.gateway.app import build_gateway_app, build_server_instance
from mcp_stack.gateway.upstreams import probe_all_upstreams
from mcp_stack.registry import sync_mcp_registry
from mcp_stack.servers.mlflow_server import probe_mcp_http_endpoint
from mcp_stack.servers.unity_catalog import UCClientAdapter
from mcp_stack.service import (
    get_service_status,
    install_launchagents,
    restart_launchagents,
    rotate_service_logs,
    tail_service_logs,
)
from mcp_stack.skills import (
    audit_skills,
    load_skills_manifest,
    promote_skill,
    resolve_manifest_path,
    rollback_quarantine,
    sync_skills,
)
from mcp_stack.uc_bootstrap import bootstrap_oss_unity_catalog
from mcp_stack.watchdog import run_watchdog_once

app = typer.Typer(
    name="mcp-stack",
    help="Modern Python FastMCP + MLflow 3.x + Unity Catalog MCP stack CLI.",
    no_args_is_help=True,
)
registry_app = typer.Typer(help="Open MCP Registry manifest and MLflow MCP Registry commands.")
config_app = typer.Typer(help="Generate and install AI client configurations.")
service_app = typer.Typer(help="Manage macOS LaunchAgents and log rotation.")
eval_app = typer.Typer(help="Run MLflow 3.x GenAI trace evaluations.")
uc_app = typer.Typer(help="Unity Catalog bootstrap and helper commands.")
ui_app = typer.Typer(help="Open and manage the Gateway Web Dashboard.")
upstream_app = typer.Typer(help="Inspect, probe, and onboard federated external MCP servers.")
skills_app = typer.Typer(
    help="Audit, sync, promote, and de-duplicate agent skills across harnesses."
)
app.add_typer(registry_app, name="registry")
app.add_typer(config_app, name="config")
app.add_typer(service_app, name="service")
app.add_typer(eval_app, name="eval")
app.add_typer(uc_app, name="uc")
app.add_typer(ui_app, name="ui")
app.add_typer(upstream_app, name="upstream")
app.add_typer(skills_app, name="skills")


@app.command("serve")
def serve(
    target: str = typer.Argument(
        ...,
        help=(
            "Server name: gateway, unity-catalog, mlflow, memory, filesystem, "
            "github, docker, postgresql, redis, mongodb, neo4j, kubernetes, jupyter, "
            "photos, xcodebuild, omnigent"
        ),
    ),
    transport: Literal["stdio", "http"] = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport for individual servers (gateway always runs Streamable HTTP)",
    ),
    host: str | None = typer.Option(None, "--host", help="Bind host for HTTP servers"),
    port: int | None = typer.Option(None, "--port", help="Bind port for HTTP servers"),
    reload: bool = typer.Option(False, "--reload", help="Enable uvicorn auto-reload (gateway)"),
) -> None:
    """Serve the unified HTTP gateway or an individual MCP server over stdio or HTTP."""
    settings = load_settings()
    configure_logging(settings.gateway.log_level, json_format=settings.gateway.log_json)

    normalized = target.strip().lower()
    if normalized == "gateway":
        bind_host = host or settings.gateway.host
        bind_port = port or settings.gateway.port
        if host is not None:
            settings.gateway.host = host
        if port is not None:
            settings.gateway.port = port

        if reload:
            uvicorn.run(
                "mcp_stack.cli:_create_reload_app",
                factory=True,
                host=bind_host,
                port=bind_port,
                reload=True,
                loop="asyncio",
                log_config=None,
            )
        else:
            gw_app = build_gateway_app(settings)
            uvicorn.run(
                gw_app,
                host=bind_host,
                port=bind_port,
                loop="asyncio",
                log_config=None,
            )
        return

    server, _adapter = build_server_instance(normalized, settings)
    if transport == "stdio":
        server.run(transport="stdio", show_banner=False)
    else:
        bind_host = host or "127.0.0.1"
        bind_port = port or 8091
        server.run(
            transport="streamable-http",
            show_banner=False,
            host=bind_host,
            port=bind_port,
        )


def _create_reload_app():
    settings = load_settings()
    configure_logging(settings.gateway.log_level, json_format=settings.gateway.log_json)
    return build_gateway_app(settings)


async def _run_doctor(
    *,
    uc_mode: str | None = None,
    databricks_profile: str | None = None,
) -> dict[str, object]:
    settings = load_settings()
    if uc_mode in {"oss", "databricks"}:
        settings.unity_catalog.mode = uc_mode  # type: ignore[assignment]
    if databricks_profile:
        settings.unity_catalog.databricks_profile = databricks_profile

    checks: dict[str, object] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "uv": shutil.which("uv"),
        "op_cli": shutil.which(settings.secrets.onepassword_cli),
        "photos_osascript": shutil.which("osascript") if sys.platform == "darwin" else None,
        "xcodebuild": shutil.which("xcodebuild") if sys.platform == "darwin" else None,
        "mlflow_tracking_uri": settings.mlflow.tracking_uri,
        "mlflow_registry_uri": settings.effective_mlflow_registry_uri,
        "uc_mode": settings.unity_catalog.mode,
        "uc_api_base": settings.unity_catalog.effective_api_base,
    }

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            r = await client.get(
                f"{settings.mlflow.tracking_uri.rstrip('/')}/api/2.0/mlflow/experiments/search",
                params={"max_results": 1},
            )
            mlflow_check: dict[str, object] = {
                "ok": r.status_code == 200,
                "status": r.status_code,
            }
            if r.status_code != 200:
                mlflow_check["detail"] = r.text[:200]
            checks["mlflow_tracking"] = mlflow_check
        except Exception as exc:
            checks["mlflow_tracking"] = {"ok": False, "error": str(exc)}

        if settings.unity_catalog.mode == "databricks":
            checks["unity_catalog"] = await UCClientAdapter(settings).databricks_probe(
                profile=databricks_profile
            )
        else:
            try:
                r = await client.get(
                    f"{settings.unity_catalog.effective_api_base}/catalogs",
                    params={"max_results": 1},
                )
                checks["unity_catalog"] = {"ok": r.status_code == 200, "status": r.status_code}
            except Exception as exc:
                checks["unity_catalog"] = {"ok": False, "error": str(exc)}

    checks["mlflow_mcp_upstream"] = await probe_mcp_http_endpoint(
        settings.mlflow.mcp_url, timeout=2.0
    )

    try:
        import docker

        dcli = docker.DockerClient(base_url=settings.docker.host)
        dcli.ping()
        checks["docker"] = {"ok": True, "host": settings.docker.host}
    except Exception as exc:
        checks["docker"] = {"ok": False, "host": settings.docker.host, "error": str(exc)}

    return checks


@app.command("doctor")
def doctor(
    uc_mode: Literal["oss", "databricks"] | None = typer.Option(
        None, "--uc-mode", help="Override UC_MODE for diagnostics (oss | databricks)"
    ),
    databricks_profile: str | None = typer.Option(
        None, "--databricks-profile", help="Override UC_DATABRICKS_PROFILE for Databricks probe"
    ),
) -> None:
    """Inspect local Python, MLflow, mlflow[mcp], Unity Catalog, Docker, and macOS readiness."""
    configure_logging("WARNING")
    report = asyncio.run(
        _run_doctor(uc_mode=uc_mode, databricks_profile=databricks_profile)
    )
    typer.echo(json.dumps(report, indent=2))


@registry_app.command("sync")
def registry_sync(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Write manifests/*.server.json without calling MLflow"
    ),
    output_dir: Path = typer.Option(
        Path("manifests"), "--output-dir", help="Directory for generated server.json manifests"
    ),
) -> None:
    """Generate server.json manifests and sync them into MLflow 3.15+ MCP Registry."""
    settings = load_settings()
    configure_logging(settings.gateway.log_level, json_format=settings.gateway.log_json)
    res = sync_mcp_registry(settings, dry_run=dry_run, output_dir=output_dir)
    typer.echo(json.dumps(res, indent=2))


@config_app.command("generate")
def config_generate(
    target: str = typer.Option(
        "all",
        "--target",
        help=(
            "Target client: all | antigravity | claude-code | claude-desktop | "
            "codex | cursor | gemini-cli | omnigent"
        ),
    ),
    write: bool = typer.Option(
        False, "--write", help="Write generated configuration files to the workspace"
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Gateway toolset profile (discover | core | studio | data | ops | macos | full)",
    ),
    live_tools: bool = typer.Option(
        True,
        "--live-tools/--no-live-tools",
        help="Query running gateway /api/v1/tools when generating Omnigent registry",
    ),
    repo_root: Path = typer.Option(
        Path("."), "--repo-root", help="Repository root for launcher paths"
    ),
) -> None:
    """Generate MCP client configs for Antigravity, Codex, Claude, Cursor, Gemini, and Omnigent."""
    settings = load_settings()
    tool_catalog: dict[str, list[str]] | None = None
    if live_tools and target in {"all", "omnigent"}:
        try:
            tool_catalog = discover_live_tool_catalog(settings)
        except Exception:
            tool_catalog = None
    if write:
        written = write_client_configs(
            settings, repo_root=repo_root, target=target, profile=profile
        )
        typer.echo(json.dumps({"written": [str(p) for p in written]}, indent=2))
    else:
        rendered = generate_client_configs(
            settings, repo_root=repo_root, profile=profile, tool_catalog=tool_catalog
        )
        if target == "all":
            typer.echo(json.dumps(rendered, indent=2))
        else:
            if target not in rendered:
                raise typer.BadParameter(f"Unknown target '{target}'")
            typer.echo(rendered[target])


@config_app.command("install")
def config_install(
    client: list[str] = typer.Option(
        ...,
        "--client",
        help=(
            "Host client(s) to update: antigravity | codex | claude-code | "
            "claude-desktop | cursor | gemini-cli | omnigent"
        ),
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Gateway toolset profile (discover | core | studio | data | ops | macos | full)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview targets without writing"),
    prune_duplicates: bool = typer.Option(
        False,
        "--prune-duplicates",
        help="Remove shadowed direct MCP entries already served by mcp-server gateway",
    ),
    live_tools: bool = typer.Option(
        True,
        "--live-tools/--no-live-tools",
        help="Query running gateway /api/v1/tools when generating Omnigent registry",
    ),
    sync_atelier_template: bool = typer.Option(
        False,
        "--sync-atelier-template",
        help="Mirror generated Omnigent registry into ~/repos/atelier/config/omnigent/",
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", help="Repository root path"),
) -> None:
    """Safely install env-var Bearer/stdio/registry entries into local host client configs."""
    settings = load_settings()
    tool_catalog: dict[str, list[str]] | None = None
    if live_tools and (
        prune_duplicates or any(c.strip().lower() == "omnigent" for c in client)
    ):
        try:
            tool_catalog = discover_live_tool_catalog(settings)
        except Exception:
            tool_catalog = None
    atelier_tpl = (
        (settings.skills.repos_root.expanduser() / "atelier/config/omnigent/mcp_registry.yaml")
        if sync_atelier_template
        else None
    )
    res = install_client_configs(
        settings,
        repo_root=repo_root,
        clients=client,
        profile=profile,
        dry_run=dry_run,
        prune_duplicates=prune_duplicates,
        tool_catalog=tool_catalog,
        sync_atelier_template=atelier_tpl,
    )
    typer.echo(json.dumps(res, indent=2))


@config_app.command("audit")
def config_audit(
    repos_root: Path | None = typer.Option(
        None, "--repos-root", help="Repos root to scan for repo-local .mcp.json/.codex shadows"
    ),
) -> None:
    """Audit live MCP client configs and repo overrides for duplicated/shadowed servers."""
    settings = load_settings()
    configure_logging("WARNING")
    res = audit_client_configs(settings, repos_root=repos_root)
    typer.echo(json.dumps(res, indent=2))


@config_app.command("verify")
def config_verify(
    client: str = typer.Option(
        "codex",
        "--client",
        help=(
            "Client identity to test: antigravity | codex | claude-code | "
            "cursor | gemini-cli | omnigent"
        ),
    ),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Gateway toolset profile to probe (defaults to configured profile)",
    ),
) -> None:
    """Perform a live Streamable HTTP MCP initialize + tools/list probe against the gateway."""
    settings = load_settings()
    configure_logging("WARNING")
    res = asyncio.run(verify_client_connection(settings, client=client, profile=profile))
    typer.echo(json.dumps(res, indent=2))
    if not res.get("ok"):
        raise typer.Exit(code=1)


@config_app.command("install-shell-hook")
def config_install_shell_hook(
    shell_rc: Path | None = typer.Option(
        None, "--shell-rc", help="Shell RC path (defaults to ~/.zshrc)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    repo_root: Path = typer.Option(Path("."), "--repo-root", help="Repository root path"),
) -> None:
    """Idempotently install guarded MCP_*_AUTH_TOKEN autoload block into ~/.zshrc."""
    res = install_shell_hook(repo_root=repo_root, shell_rc=shell_rc, dry_run=dry_run)
    typer.echo(json.dumps(res, indent=2))


@service_app.command("status")
def service_status() -> None:
    """Show macOS LaunchAgent and gateway readiness status."""
    settings = load_settings()
    typer.echo(json.dumps(get_service_status(settings), indent=2))


@service_app.command("install")
def service_install(
    repo_root: Path = typer.Option(Path("."), "--repo-root", help="Repository root path"),
) -> None:
    """Install and bootstrap macOS LaunchAgents in dependency order."""
    settings = load_settings()
    typer.echo(json.dumps(install_launchagents(settings, repo_root.resolve()), indent=2))


@service_app.command("restart")
def service_restart() -> None:
    """Kickstart both macOS LaunchAgents and verify gateway /ready."""
    settings = load_settings()
    typer.echo(json.dumps(restart_launchagents(settings), indent=2))


@service_app.command("logs")
def service_logs(
    service: str = typer.Option("all", "--service", help="all | gateway | mlflow-mcp | watchdog"),
    lines: int = typer.Option(40, "--lines", help="Number of trailing log lines"),
) -> None:
    """Print recent LaunchAgent stdout/stderr log lines."""
    for fname, content in tail_service_logs(service=service, lines=lines).items():
        typer.echo(f"=== {fname} ===")
        typer.echo(content)


@service_app.command("rotate-logs")
def service_rotate_logs(
    max_mb: float = typer.Option(10.0, "--max-mb", help="Rotate logs larger than N MiB"),
    keep: int = typer.Option(3, "--keep", help="Archived log generations to keep"),
) -> None:
    """Rotate oversized LaunchAgent log files."""
    typer.echo(json.dumps(rotate_service_logs(max_mb=max_mb, keep=keep), indent=2))


@service_app.command("watchdog-once")
def service_watchdog_once(
    threshold: int = typer.Option(2, "--threshold", help="Consecutive failures before recovery"),
    cooldown: float = typer.Option(180.0, "--cooldown", help="Minimum seconds between restarts"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report actions without restarting"),
) -> None:
    """Run one LaunchAgent watchdog probe and cooldown-guarded recovery pass."""
    settings = load_settings()
    configure_logging("WARNING")
    res = run_watchdog_once(
        settings,
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
        dry_run=dry_run,
    )
    typer.echo(json.dumps(res, indent=2))


@eval_app.command("run")
def eval_run(
    experiment: str | None = typer.Option(None, "--experiment", help="MLflow experiment name"),
    limit: int = typer.Option(20, "--limit", help="Max recent traces to evaluate"),
    latency_sla_ms: float = typer.Option(5000.0, "--latency-sla-ms", help="Latency threshold ms"),
    with_llm_judge: bool = typer.Option(
        False, "--with-llm-judge", help="Include local Ollama / MLflow judge scorer"
    ),
    judge_model: str | None = typer.Option(
        None,
        "--judge-model",
        help="Optional judge model URI (default: ollama:/qwen3.8:27b)",
    ),
) -> None:
    """Evaluate recent gateway traces with mlflow.genai.evaluate() and @scorers."""
    settings = load_settings()
    configure_logging("WARNING")
    res = run_trace_evaluation(
        settings,
        experiment_name=experiment,
        limit=limit,
        latency_sla_ms=latency_sla_ms,
        with_llm_judge=with_llm_judge,
        judge_model=judge_model,
    )
    typer.echo(json.dumps(res, indent=2))


@eval_app.command("sync-dataset")
def eval_sync_dataset(
    experiment: str | None = typer.Option(None, "--experiment", help="MLflow experiment name"),
    dataset_name: str = typer.Option(
        GOLDEN_DATASET_NAME, "--dataset", help="MLflow GenAI evaluation dataset name"
    ),
) -> None:
    """Create or update the golden MCP benchmark dataset in MLflow 3.x."""
    settings = load_settings()
    configure_logging("WARNING")
    res = sync_golden_dataset(settings, experiment_name=experiment, dataset_name=dataset_name)
    typer.echo(json.dumps(res, indent=2))


@eval_app.command("sync-scorers")
def eval_sync_scorers(
    experiment: str | None = typer.Option(None, "--experiment", help="MLflow experiment name"),
) -> None:
    """Register deterministic scorers on the target MLflow experiment."""
    settings = load_settings()
    configure_logging("WARNING")
    res = register_experiment_scorers(settings, experiment_name=experiment)
    typer.echo(json.dumps(res, indent=2))


@eval_app.command("benchmark")
def eval_benchmark(
    experiment: str | None = typer.Option(None, "--experiment", help="MLflow experiment name"),
    dataset_name: str = typer.Option(
        GOLDEN_DATASET_NAME, "--dataset", help="MLflow GenAI evaluation dataset name"
    ),
    latency_sla_ms: float = typer.Option(5000.0, "--latency-sla-ms", help="Latency threshold ms"),
    with_llm_judge: bool = typer.Option(
        False, "--with-llm-judge", help="Include local Ollama / MLflow judge scorer"
    ),
    judge_model: str | None = typer.Option(
        None,
        "--judge-model",
        help="Optional judge model URI (default: ollama:/qwen3.8:27b)",
    ),
) -> None:
    """Run the executable golden dataset benchmark via mlflow.genai.evaluate()."""
    settings = load_settings()
    configure_logging("WARNING")
    res = run_golden_benchmark(
        settings,
        experiment_name=experiment,
        dataset_name=dataset_name,
        latency_sla_ms=latency_sla_ms,
        with_llm_judge=with_llm_judge,
        judge_model=judge_model,
    )
    typer.echo(json.dumps(res, indent=2))


@uc_app.command("bootstrap")
def uc_bootstrap() -> None:
    """Idempotently bootstrap workshop catalog, memory_snapshots volume, and sample UDFs."""
    settings = load_settings()
    configure_logging("WARNING")
    res = asyncio.run(bootstrap_oss_unity_catalog(settings))
    typer.echo(json.dumps(res, indent=2))


@ui_app.command("open")
def ui_open(
    client: str | None = typer.Option(
        None, "--client", help="Client ID whose Gateway policy should sign into /ui (e.g. codex)"
    ),
    public_url: str | None = typer.Option(
        None, "--public-url", help="Override public origin for login link (e.g. https://mcp.slcc2c.com)"
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Print one-time login URL without opening system browser"
    ),
) -> None:
    """Mint a 60s single-use cookie login URL for /ui without copying Bearer tokens."""
    settings = load_settings()
    configure_logging("WARNING")

    target_host = "127.0.0.1" if settings.gateway.host == "0.0.0.0" else settings.gateway.host
    base_url = f"http://{target_host}:{settings.gateway.port}"
    req_headers: dict[str, str] = {}
    chosen_id = "local"

    if settings.gateway.effective_auth_enabled:
        selected: tuple[str, str] | None = None
        if client:
            for tok, pol in settings.gateway.clients.items():
                if pol.client_id == client:
                    selected = (tok, pol.client_id)
                    break
            if selected is None:
                typer.echo(f"Unknown client_id '{client}'", err=True)
                raise typer.Exit(code=1)
        else:
            for tok, pol in settings.gateway.clients.items():
                if pol.client_id == "codex":
                    selected = (tok, pol.client_id)
                    break
            if selected is None and settings.gateway.clients:
                tok, pol = next(iter(settings.gateway.clients.items()))
                selected = (tok, pol.client_id)
        if selected is None:
            typer.echo("No Gateway client tokens configured", err=True)
            raise typer.Exit(code=1)
        req_headers["Authorization"] = f"Bearer {selected[0]}"
        chosen_id = selected[1]

    resp = httpx.post(f"{base_url}/api/v1/auth/login-link", headers=req_headers, timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    login_url = str(data["url"])
    override_origin = (public_url or settings.gateway.public_url or "").strip().rstrip("/")
    if override_origin:
        orig_parts = urlsplit(login_url)
        target_parts = urlsplit(override_origin)
        if target_parts.scheme and target_parts.netloc:
            login_url = urlunsplit(
                (
                    target_parts.scheme,
                    target_parts.netloc,
                    orig_parts.path,
                    orig_parts.query,
                    orig_parts.fragment,
                )
            )
    opened = False
    if not no_browser:
        opened = bool(webbrowser.open(login_url))

    typer.echo(
        json.dumps(
            {
                "opened": opened,
                "url": login_url,
                "client_id": data.get("clientId", chosen_id),
                "expires_in_seconds": data.get("expiresInSeconds", 60),
            },
            indent=2,
        )
    )


@ui_app.command("build")
def ui_build(
    web_dir: Path = typer.Option(Path("web"), "--web-dir", help="Frontend SPA workspace directory"),
    install: bool = typer.Option(False, "--install", help="Run pnpm install before building"),
) -> None:
    """Build the React + Vite Control Plane SPA into src/mcp_stack/gateway/static."""
    import subprocess

    pnpm = shutil.which("pnpm")
    if not pnpm:
        typer.echo("pnpm is required to build the UI (`corepack enable pnpm`).", err=True)
        raise typer.Exit(code=1)
    if not web_dir.exists():
        typer.echo(f"Frontend workspace not found: {web_dir}", err=True)
        raise typer.Exit(code=1)

    if install:
        subprocess.run([pnpm, "--dir", str(web_dir), "install", "--frozen-lockfile"], check=True)
    subprocess.run([pnpm, "--dir", str(web_dir), "build"], check=True)
    static_dir = Path("src/mcp_stack/gateway/static")
    typer.echo(
        json.dumps(
            {
                "built": (static_dir / "index.html").exists(),
                "output_dir": str(static_dir.resolve()),
            },
            indent=2,
        )
    )


@upstream_app.command("list")
def upstream_list() -> None:
    """List configured federated external MCP servers."""
    settings = load_settings()
    configure_logging("WARNING")
    items = [
        {
            "name": name,
            "transport": cfg.transport,
            "target": cfg.url if cfg.transport == "http" else cfg.command,
            "args": cfg.args,
            "cwd": str(cfg.cwd) if cfg.cwd else None,
            "enabled": cfg.enabled,
            "profiles": cfg.profiles,
            "registry_name": cfg.registry_name,
        }
        for name, cfg in settings.gateway.upstream_servers.items()
    ]
    typer.echo(json.dumps({"upstreams": items}, indent=2))


@upstream_app.command("probe")
def upstream_probe() -> None:
    """Probe live reachability and tool counts for configured external MCP servers."""
    settings = load_settings()
    configure_logging("WARNING")
    res = asyncio.run(probe_all_upstreams(settings))
    typer.echo(json.dumps({"upstreams": res}, indent=2))


@upstream_app.command("add")
def upstream_add(
    name: str = typer.Argument(..., help="Short slug for the upstream server (e.g. printer)"),
    transport: Literal["http", "stdio"] = typer.Option("http", "--transport"),
    url: str | None = typer.Option(None, "--url", help="Streamable HTTP endpoint URL"),
    command: str | None = typer.Option(None, "--command", help="Stdio executable command"),
    arg: list[str] = typer.Option([], "--arg", help="Repeatable stdio CLI arguments"),
    cwd: Path | None = typer.Option(None, "--cwd", help="Optional stdio working directory"),
    profile: list[str] = typer.Option(
        ["studio"], "--profile", help="Profiles including this server"
    ),
    registry_name: str | None = typer.Option(
        None, "--registry-name", help="Optional MLflow MCP Registry name"
    ),
    governance: str = typer.Option("external-proxy", "--governance"),
    description: str = typer.Option("", "--description"),
    config_file: Path = typer.Option(
        Path("config/gateway.local.yaml"), "--config-file", help="Target local YAML file"
    ),
) -> None:
    """Add or update an external MCP server inside gitignored config/gateway.local.yaml."""
    import yaml

    if transport == "http" and not url:
        typer.echo("--url is required when --transport=http", err=True)
        raise typer.Exit(code=2)
    if transport == "stdio" and not command:
        typer.echo("--command is required when --transport=stdio", err=True)
        raise typer.Exit(code=2)

    raw: dict[str, object] = {}
    if config_file.exists():
        loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    gw_sec = raw.setdefault("gateway", {})
    assert isinstance(gw_sec, dict)
    up_sec = gw_sec.setdefault("upstream_servers", {})
    assert isinstance(up_sec, dict)

    entry: dict[str, object] = {
        "transport": transport,
        "enabled": True,
        "profiles": list(profile) or ["studio"],
        "governance": governance,
    }
    if url:
        entry["url"] = url
    if command:
        entry["command"] = command
    if arg:
        entry["args"] = list(arg)
    if cwd is not None:
        entry["cwd"] = str(cwd)
    if registry_name:
        entry["registry_name"] = registry_name
    if description:
        entry["description"] = description

    clean_slug = name.strip().replace("_", "-").lower()
    up_sec[clean_slug] = entry
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    typer.echo(json.dumps({"saved": clean_slug, "config_file": str(config_file)}, indent=2))


@skills_app.command("audit")
def skills_audit(
    manifest: Path | None = typer.Option(
        None, "--manifest", help="Path to skills-manifest.yaml"
    ),
    repos_root: Path | None = typer.Option(
        None, "--repos-root", help="Repos root to scan for repo-local skill shadows"
    ),
) -> None:
    """Run a 5-layer audit of canonical skills, harness symlinks, plugins, repos, and aliases."""
    settings = load_settings()
    configure_logging("WARNING")
    mpath = resolve_manifest_path(manifest, configured=settings.skills.manifest_path)
    loaded = load_skills_manifest(mpath)
    report = audit_skills(
        loaded,
        repos_root=repos_root or settings.skills.repos_root,
    )
    report["manifestPath"] = str(mpath)
    typer.echo(json.dumps(report, indent=2))


@skills_app.command("sync")
def skills_sync(
    apply: bool = typer.Option(
        False, "--apply", help="Apply symlink projections & move replaced copies to quarantine"
    ),
    quarantine_legacy: bool = typer.Option(
        False,
        "--quarantine-legacy",
        help="Also move stale skills from legacy_cleanup_roots into recoverable quarantine",
    ),
    target: list[str] = typer.Option(
        [], "--target", help="Optional specific target ID(s) from manifest"
    ),
    manifest: Path | None = typer.Option(
        None, "--manifest", help="Path to skills-manifest.yaml"
    ),
) -> None:
    """Project canonical skill symlinks across harnesses (dry-run by default)."""
    settings = load_settings()
    configure_logging("WARNING")
    mpath = resolve_manifest_path(manifest, configured=settings.skills.manifest_path)
    loaded = load_skills_manifest(mpath)
    res = sync_skills(
        loaded,
        dry_run=not apply,
        quarantine_legacy=quarantine_legacy,
        targets=target or None,
    )
    res["manifestPath"] = str(mpath)
    typer.echo(json.dumps(res, indent=2))


@skills_app.command("promote")
def skills_promote(
    source_or_name: str = typer.Argument(
        ..., help="Skill path or quarantined/legacy skill name to promote into canonical store"
    ),
    name: str | None = typer.Option(None, "--name", help="Override target skill directory name"),
    apply: bool = typer.Option(False, "--apply", help="Write changes instead of dry-run"),
    manifest: Path | None = typer.Option(
        None, "--manifest", help="Path to skills-manifest.yaml"
    ),
) -> None:
    """Promote a skill into canonical atelier storage, register it, and project symlinks."""
    settings = load_settings()
    configure_logging("WARNING")
    mpath = resolve_manifest_path(manifest, configured=settings.skills.manifest_path)
    res = promote_skill(mpath, source_or_name, skill_name=name, dry_run=not apply)
    typer.echo(json.dumps(res, indent=2))


@skills_app.command("rollback")
def skills_rollback(
    quarantine_dir: Path = typer.Argument(
        ..., help="Quarantine batch directory containing manifest.json"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Restore quarantined entries instead of dry-run"
    ),
) -> None:
    """Restore skills moved during a previous quarantine batch."""
    res = rollback_quarantine(quarantine_dir, dry_run=not apply)
    typer.echo(json.dumps(res, indent=2))


if __name__ == "__main__":
    app()
