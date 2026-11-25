"""Kubernetes FastMCP server with namespace allowlists and read-only default gating."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.tracing import MLflowTracingMiddleware


def _require_mutations(settings: MCPStackSettings) -> None:
    if not settings.kubernetes.allow_mutations:
        raise ToolError(
            "Kubernetes mutations are disabled by policy. "
            "Set K8S_ALLOW_MUTATIONS=true to enable resource writes/deletes."
        )


def _check_namespace(settings: MCPStackSettings, namespace: str) -> str:
    ns = namespace.strip() or "default"
    allowed = settings.kubernetes.allowed_namespaces
    if "*" not in allowed and ns not in allowed:
        raise ToolError(
            f"Namespace '{ns}' is not in K8S_ALLOWED_NAMESPACES ({', '.join(allowed)})."
        )
    return ns


def create_kubernetes_server(
    settings: MCPStackSettings,
    *,
    api_factory: Callable[[], dict[str, Any]] | None = None,
) -> FastMCP:
    """Create the Kubernetes cluster MCP server."""
    mcp = FastMCP("kubernetes")
    mcp.add_middleware(MLflowTracingMiddleware(settings, "kubernetes"))

    def _apis() -> dict[str, Any]:
        if api_factory is not None:
            return api_factory()
        try:
            from kubernetes import client, config

            kube_cfg = settings.kubernetes.kubeconfig
            if kube_cfg is not None:
                config.load_kube_config(
                    config_file=str(kube_cfg),
                    context=settings.kubernetes.context,
                )
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config(context=settings.kubernetes.context)
            return {
                "core": client.CoreV1Api(),
                "apps": client.AppsV1Api(),
                "batch": client.BatchV1Api(),
                "version": client.VersionApi(),
            }
        except Exception as exc:
            raise ToolError(f"Kubernetes client unavailable: {exc}") from exc

    @mcp.tool()
    async def k8s_list_namespaces() -> dict[str, Any]:
        """List namespaces in the Kubernetes cluster."""
        def _run() -> list[str]:
            resp = _apis()["core"].list_namespace()
            return [item.metadata.name for item in resp.items]

        names = await asyncio.to_thread(_run)
        return {"namespaces": names, "count": len(names)}

    @mcp.tool()
    async def k8s_create_namespace(name: str) -> dict[str, Any]:
        """Create a Kubernetes namespace (requires K8S_ALLOW_MUTATIONS=true)."""
        _require_mutations(settings)

        def _run() -> str:
            from kubernetes import client as kclient

            body = kclient.V1Namespace(metadata=kclient.V1ObjectMeta(name=name))
            res = _apis()["core"].create_namespace(body=body)
            return str(res.metadata.name)

        created = await asyncio.to_thread(_run)
        return {"namespace": created, "created": True}

    @mcp.tool()
    async def k8s_list_pods(
        namespace: str = "default",
        label_selector: str | None = None,
    ) -> dict[str, Any]:
        """List pods in an allowed Kubernetes namespace."""
        ns = _check_namespace(settings, namespace)

        def _run() -> list[dict[str, Any]]:
            kwargs: dict[str, Any] = {}
            if label_selector:
                kwargs["label_selector"] = label_selector
            resp = _apis()["core"].list_namespaced_pod(ns, **kwargs)
            return [
                {
                    "name": p.metadata.name,
                    "phase": p.status.phase,
                    "node": p.spec.node_name,
                }
                for p in resp.items
            ]

        pods = await asyncio.to_thread(_run)
        return {"namespace": ns, "pods": pods, "count": len(pods)}

    @mcp.tool()
    async def k8s_create_pod(
        name: str,
        image: str,
        namespace: str = "default",
        command: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a single-container pod in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            from kubernetes import client as kclient

            container = kclient.V1Container(name=name, image=image, command=command)
            body = kclient.V1Pod(
                metadata=kclient.V1ObjectMeta(name=name),
                spec=kclient.V1PodSpec(containers=[container], restart_policy="Never"),
            )
            res = _apis()["core"].create_namespaced_pod(namespace=ns, body=body)
            return str(res.metadata.name)

        created = await asyncio.to_thread(_run)
        return {"namespace": ns, "pod": created, "created": True}

    @mcp.tool()
    async def k8s_delete_pod(name: str, namespace: str = "default") -> dict[str, Any]:
        """Delete a pod in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)
        await asyncio.to_thread(
            lambda: _apis()["core"].delete_namespaced_pod(name=name, namespace=ns)
        )
        return {"namespace": ns, "pod": name, "deleted": True}

    @mcp.tool()
    async def k8s_list_deployments(namespace: str = "default") -> dict[str, Any]:
        """List deployments in an allowed Kubernetes namespace."""
        ns = _check_namespace(settings, namespace)

        def _run() -> list[dict[str, Any]]:
            resp = _apis()["apps"].list_namespaced_deployment(ns)
            return [
                {
                    "name": d.metadata.name,
                    "replicas": d.spec.replicas,
                    "ready": d.status.ready_replicas or 0,
                }
                for d in resp.items
            ]

        items = await asyncio.to_thread(_run)
        return {"namespace": ns, "deployments": items}

    @mcp.tool()
    async def k8s_create_deployment(
        name: str,
        image: str,
        replicas: int = 1,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Create a Deployment in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            from kubernetes import client as kclient

            labels = {"app": name}
            body = kclient.V1Deployment(
                metadata=kclient.V1ObjectMeta(name=name),
                spec=kclient.V1DeploymentSpec(
                    replicas=replicas,
                    selector=kclient.V1LabelSelector(match_labels=labels),
                    template=kclient.V1PodTemplateSpec(
                        metadata=kclient.V1ObjectMeta(labels=labels),
                        spec=kclient.V1PodSpec(
                            containers=[kclient.V1Container(name=name, image=image)]
                        ),
                    ),
                ),
            )
            res = _apis()["apps"].create_namespaced_deployment(namespace=ns, body=body)
            return str(res.metadata.name)

        return {"namespace": ns, "deployment": await asyncio.to_thread(_run), "created": True}

    @mcp.tool()
    async def k8s_scale_deployment(
        name: str,
        replicas: int,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Scale a Deployment replica count in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)
        await asyncio.to_thread(
            lambda: _apis()["apps"].patch_namespaced_deployment_scale(
                name=name, namespace=ns, body={"spec": {"replicas": replicas}}
            )
        )
        return {"namespace": ns, "deployment": name, "replicas": replicas}

    @mcp.tool()
    async def k8s_delete_deployment(name: str, namespace: str = "default") -> dict[str, Any]:
        """Delete a Deployment in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)
        await asyncio.to_thread(
            lambda: _apis()["apps"].delete_namespaced_deployment(name=name, namespace=ns)
        )
        return {"namespace": ns, "deployment": name, "deleted": True}

    @mcp.tool()
    async def k8s_list_services(namespace: str = "default") -> dict[str, Any]:
        """List Services in an allowed namespace."""
        ns = _check_namespace(settings, namespace)

        def _run() -> list[dict[str, Any]]:
            resp = _apis()["core"].list_namespaced_service(ns)
            return [
                {
                    "name": s.metadata.name,
                    "type": s.spec.type,
                    "clusterIP": s.spec.cluster_ip,
                }
                for s in resp.items
            ]

        return {"namespace": ns, "services": await asyncio.to_thread(_run)}

    @mcp.tool()
    async def k8s_create_service(
        name: str,
        port: int,
        target_port: int | None = None,
        selector: dict[str, str] | None = None,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Create a ClusterIP Service in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            from kubernetes import client as kclient

            body = kclient.V1Service(
                metadata=kclient.V1ObjectMeta(name=name),
                spec=kclient.V1ServiceSpec(
                    selector=selector or {"app": name},
                    ports=[
                        kclient.V1ServicePort(port=port, target_port=target_port or port)
                    ],
                ),
            )
            res = _apis()["core"].create_namespaced_service(namespace=ns, body=body)
            return str(res.metadata.name)

        return {"namespace": ns, "service": await asyncio.to_thread(_run), "created": True}

    @mcp.tool()
    async def k8s_create_configmap(
        name: str,
        data: dict[str, str],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Create a ConfigMap in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            from kubernetes import client as kclient

            body = kclient.V1ConfigMap(metadata=kclient.V1ObjectMeta(name=name), data=data)
            res = _apis()["core"].create_namespaced_config_map(namespace=ns, body=body)
            return str(res.metadata.name)

        return {"namespace": ns, "configmap": await asyncio.to_thread(_run), "created": True}

    @mcp.tool()
    async def k8s_create_secret(
        name: str,
        string_data: dict[str, str],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Create an Opaque Secret in an allowed namespace (values masked in response)."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            from kubernetes import client as kclient

            body = kclient.V1Secret(
                metadata=kclient.V1ObjectMeta(name=name),
                string_data=string_data,
            )
            res = _apis()["core"].create_namespaced_secret(namespace=ns, body=body)
            return str(res.metadata.name)

        created = await asyncio.to_thread(_run)
        return {
            "namespace": ns,
            "secret": created,
            "keys": sorted(string_data.keys()),
            "created": True,
        }

    @mcp.tool()
    async def k8s_create_job(
        name: str,
        image: str,
        command: list[str] | None = None,
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Create a batch Job in an allowed namespace."""
        _require_mutations(settings)
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            from kubernetes import client as kclient

            body = kclient.V1Job(
                metadata=kclient.V1ObjectMeta(name=name),
                spec=kclient.V1JobSpec(
                    template=kclient.V1PodTemplateSpec(
                        spec=kclient.V1PodSpec(
                            containers=[
                                kclient.V1Container(name=name, image=image, command=command)
                            ],
                            restart_policy="Never",
                        )
                    )
                ),
            )
            res = _apis()["batch"].create_namespaced_job(namespace=ns, body=body)
            return str(res.metadata.name)

        return {"namespace": ns, "job": await asyncio.to_thread(_run), "created": True}

    @mcp.tool()
    async def k8s_list_jobs(namespace: str = "default") -> dict[str, Any]:
        """List batch Jobs in an allowed namespace."""
        ns = _check_namespace(settings, namespace)

        def _run() -> list[dict[str, Any]]:
            resp = _apis()["batch"].list_namespaced_job(ns)
            return [
                {
                    "name": j.metadata.name,
                    "succeeded": j.status.succeeded or 0,
                    "failed": j.status.failed or 0,
                }
                for j in resp.items
            ]

        return {"namespace": ns, "jobs": await asyncio.to_thread(_run)}

    @mcp.tool()
    async def k8s_get_logs(
        pod_name: str,
        namespace: str = "default",
        container: str | None = None,
        tail_lines: int = 100,
    ) -> dict[str, Any]:
        """Fetch recent logs from a pod in an allowed namespace."""
        ns = _check_namespace(settings, namespace)

        def _run() -> str:
            kwargs: dict[str, Any] = {"tail_lines": tail_lines}
            if container:
                kwargs["container"] = container
            return str(_apis()["core"].read_namespaced_pod_log(pod_name, ns, **kwargs))

        return {"namespace": ns, "pod": pod_name, "logs": await asyncio.to_thread(_run)}

    @mcp.tool()
    async def k8s_get_events(namespace: str = "default") -> dict[str, Any]:
        """List recent Kubernetes events in an allowed namespace."""
        ns = _check_namespace(settings, namespace)

        def _run() -> list[dict[str, Any]]:
            resp = _apis()["core"].list_namespaced_event(ns)
            return [
                {
                    "type": e.type,
                    "reason": e.reason,
                    "message": e.message,
                }
                for e in resp.items
            ]

        return {"namespace": ns, "events": await asyncio.to_thread(_run)}

    @mcp.tool()
    async def k8s_cluster_info() -> dict[str, Any]:
        """Return Kubernetes server version and node summary."""
        def _run() -> dict[str, Any]:
            apis = _apis()
            ver = apis["version"].get_code()
            nodes = apis["core"].list_node()
            return {
                "gitVersion": ver.git_version,
                "platform": ver.platform,
                "nodes": [n.metadata.name for n in nodes.items],
            }

        return await asyncio.to_thread(_run)

    return mcp
