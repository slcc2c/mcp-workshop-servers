"""Docker Engine MCP server with lazy daemon connection, image allowlist, and resource caps."""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware


def _is_image_allowed(image: str, patterns: list[str]) -> bool:
    candidate = image if ":" in image else f"{image}:latest"
    return any(
        fnmatch.fnmatch(image, pat) or fnmatch.fnmatch(candidate, pat)
        for pat in patterns
    )


def create_docker_server(
    settings: MCPStackSettings,
    *,
    client_factory: Callable[[], Any] | None = None,
) -> FastMCP:
    """Create the Docker Engine MCP server."""
    docker_cfg = settings.docker
    mcp = FastMCP("docker")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "docker"))

    def _get_client() -> Any:
        try:
            if client_factory is not None:
                client = client_factory()
            else:
                import docker

                client = docker.DockerClient(base_url=docker_cfg.host)
            client.ping()
            return client
        except Exception as exc:
            raise ToolError(
                f"Docker daemon is unavailable at '{docker_cfg.host}': {exc}"
            ) from exc

    @mcp.tool()
    async def docker_list_containers(
        all: bool = False,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """List Docker containers."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            containers = client.containers.list(all=all, filters=filters or None)
            return [
                {
                    "id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if getattr(c.image, "tags", None) else str(c.image),
                }
                for c in containers
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_inspect_container(container_id: str) -> dict[str, Any]:
        """Inspect detailed metadata for a container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            return dict(c.attrs)

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_create_container(
        image: str,
        name: str | None = None,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        ports: dict[str, str] | None = None,
        volumes: dict[str, str] | None = None,
        working_dir: str | None = None,
        memory: str | None = None,
        cpus: float | None = None,
        auto_remove: bool = True,
        detach: bool = True,
    ) -> dict[str, Any]:
        """Create (and optionally start) a Docker container subject to image and resource limits."""
        if not _is_image_allowed(image, docker_cfg.allowed_images):
            raise ToolError(
                f"Image '{image}' is not in DOCKER_ALLOWED_IMAGES ({docker_cfg.allowed_images})"
            )

        mem_limit = memory or docker_cfg.default_memory
        cpu_limit = cpus if cpus is not None else docker_cfg.default_cpus
        nano_cpus = int(cpu_limit * 1_000_000_000)

        def _run() -> dict[str, Any]:
            client = _get_client()
            vol_binds = (
                {host: {"bind": cont, "mode": "rw"} for host, cont in volumes.items()}
                if volumes
                else None
            )
            container = client.containers.run(
                image=image,
                command=command,
                name=name,
                environment=env or {},
                ports=ports or None,
                volumes=vol_binds,
                working_dir=working_dir,
                mem_limit=mem_limit,
                nano_cpus=nano_cpus,
                auto_remove=auto_remove,
                detach=detach,
            )
            if detach:
                return {
                    "id": container.short_id,
                    "name": container.name,
                    "status": container.status,
                    "memLimit": mem_limit,
                    "cpus": cpu_limit,
                }
            return {
                "output": container.decode("utf-8", errors="replace")
                if isinstance(container, (bytes, bytearray))
                else str(container)
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_start_container(container_id: str) -> dict[str, Any]:
        """Start an existing Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            c.start()
            return {"id": c.short_id, "name": c.name, "started": True}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_stop_container(container_id: str, timeout: int = 10) -> dict[str, Any]:
        """Stop a running Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            c.stop(timeout=timeout)
            return {"id": c.short_id, "name": c.name, "stopped": True}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_restart_container(container_id: str, timeout: int = 10) -> dict[str, Any]:
        """Restart a Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            c.restart(timeout=timeout)
            return {"id": c.short_id, "name": c.name, "restarted": True}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_remove_container(
        container_id: str,
        force: bool = False,
        volumes: bool = False,
    ) -> dict[str, Any]:
        """Remove a Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            c.remove(force=force, v=volumes)
            return {"containerId": container_id, "removed": True}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_container_logs(
        container_id: str,
        tail: int = 100,
        timestamps: bool = False,
    ) -> dict[str, Any]:
        """Fetch recent logs from a Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            raw = c.logs(tail=tail, timestamps=timestamps)
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            return {"containerId": container_id, "logs": text}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_container_stats(container_id: str) -> dict[str, Any]:
        """Get a one-shot resource usage snapshot for a Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            return dict(c.stats(stream=False))

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_exec(
        container_id: str,
        command: list[str],
        user: str | None = None,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command inside a running Docker container."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            c = client.containers.get(container_id)
            res = c.exec_run(
                cmd=command,
                user=user or "",
                workdir=working_dir,
                environment=env or {},
            )
            out = (
                res.output.decode("utf-8", errors="replace")
                if isinstance(res.output, bytes)
                else str(res.output)
            )
            return {"exitCode": res.exit_code, "output": out}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_list_images(all: bool = False) -> list[dict[str, Any]]:
        """List local Docker images."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            imgs = client.images.list(all=all)
            return [
                {
                    "id": img.short_id,
                    "tags": img.tags,
                }
                for img in imgs
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_pull_image(image: str, tag: str = "latest") -> dict[str, Any]:
        """Pull an allowlisted Docker image."""
        full = f"{image}:{tag}" if ":" not in image else image
        if not _is_image_allowed(full, docker_cfg.allowed_images):
            raise ToolError(f"Image '{full}' is not in DOCKER_ALLOWED_IMAGES")

        def _run() -> dict[str, Any]:
            client = _get_client()
            img = client.images.pull(image, tag=tag if ":" not in image else None)
            return {"id": img.short_id, "tags": img.tags}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_remove_image(
        image_id: str,
        force: bool = False,
        no_prune: bool = False,
    ) -> dict[str, Any]:
        """Remove a Docker image."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            client.images.remove(image=image_id, force=force, noprune=no_prune)
            return {"imageId": image_id, "removed": True}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_list_volumes() -> list[dict[str, Any]]:
        """List Docker volumes."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            return [
                {"name": v.name, "driver": v.attrs.get("Driver")}
                for v in client.volumes.list()
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_create_volume(
        name: str,
        driver: str = "local",
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a Docker volume."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            vol = client.volumes.create(name=name, driver=driver, labels=labels or {})
            return {"name": vol.name, "driver": vol.attrs.get("Driver")}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_remove_volume(volume_name: str, force: bool = False) -> dict[str, Any]:
        """Remove a Docker volume."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            vol = client.volumes.get(volume_name)
            vol.remove(force=force)
            return {"volumeName": volume_name, "removed": True}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_list_networks() -> list[dict[str, Any]]:
        """List Docker networks."""

        def _run() -> list[dict[str, Any]]:
            client = _get_client()
            return [
                {"id": n.short_id, "name": n.name, "driver": n.attrs.get("Driver")}
                for n in client.networks.list()
            ]

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_create_network(
        name: str,
        driver: str = "bridge",
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a Docker network."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            net = client.networks.create(name=name, driver=driver, labels=labels or {})
            return {"id": net.short_id, "name": net.name}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def docker_remove_network(network_id: str) -> dict[str, Any]:
        """Remove a Docker network."""

        def _run() -> dict[str, Any]:
            client = _get_client()
            net = client.networks.get(network_id)
            net.remove()
            return {"networkId": network_id, "removed": True}

        return await asyncio.to_thread(_run)

    return mcp
