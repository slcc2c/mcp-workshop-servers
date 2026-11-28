"""Omnigent hub REST/SSE MCP server."""

from __future__ import annotations

import contextlib
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_stack import __version__
from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import MLflowTracingMiddleware
from mcp_stack.servers.memory import score_omnigent_memory_entry


def _extract_item_text(item: dict[str, Any]) -> str:
    data = item.get("data")
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, list):
            parts = [
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("text")
            ]
            if parts:
                return "\n".join(parts)
        if isinstance(content, str) and content:
            return content
        if isinstance(data.get("text"), str) and data["text"]:
            return data["text"]
    if isinstance(item.get("text"), str):
        return item["text"]
    return ""


def _compact_session_row(row: dict[str, Any], public_base: str) -> dict[str, Any]:
    sid = str(row.get("id", ""))
    return {
        "id": sid,
        "title": row.get("title"),
        "status": row.get("status"),
        "agentName": row.get("agent_name"),
        "projectId": row.get("project_id"),
        "workspace": row.get("workspace"),
        "pendingApprovals": row.get("pending_elicitations_count", 0),
        "archived": bool(row.get("archived", False)),
        "updatedAt": row.get("updated_at"),
        "sessionUrl": f"{public_base}/c/{sid}" if sid else None,
    }


def create_omnigent_server(
    settings: MCPStackSettings,
    *,
    secret_resolver: SecretResolver | None = None,
    http_client: httpx.AsyncClient | None = None,
    auth: Any | None = None,
) -> FastMCP:
    """Create the async Omnigent REST/SSE bridge MCP server."""
    resolver = secret_resolver or SecretResolver(settings.secrets)
    mcp = FastMCP("omnigent", auth=auth)
    mcp.add_middleware(MLflowTracingMiddleware(settings, "omnigent"))

    def _base_url() -> str:
        return settings.omnigent.base_url.rstrip("/")

    def _public_base_url() -> str:
        return (settings.omnigent.public_url or _base_url()).rstrip("/")

    def _session_url(session_id: str) -> str:
        return f"{_public_base_url()}/c/{session_id}"

    def _require_mutations(action: str) -> None:
        if not settings.omnigent.allow_mutations:
            raise ToolError(
                "Omnigent mutations are disabled (OMNIGENT_ALLOW_MUTATIONS=false); "
                f"cannot {action}."
            )

    async def _omni_request(
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        base = _base_url()
        url = f"{base}/{path.lstrip('/')}"
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": f"mcp-workshop-stack/{__version__}",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if method.upper() != "GET":
            headers["Origin"] = base
        token = resolver.resolve(settings.omnigent.token)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        try:
            if http_client is not None:
                resp = await http_client.request(
                    method, url, params=clean_params, json=json_body, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=settings.omnigent.timeout_seconds) as client:
                    resp = await client.request(
                        method, url, params=clean_params, json=json_body, headers=headers
                    )
        except httpx.HTTPError as exc:
            raise ToolError(f"Omnigent request {method} {path} failed: {exc}") from exc

        if resp.status_code >= 400:
            detail = resp.text[:400]
            with contextlib.suppress(Exception):
                body = resp.json()
                err = body.get("error")
                if isinstance(err, dict) and err.get("message"):
                    detail = str(err["message"])
                elif body.get("detail") or body.get("message"):
                    detail = str(body.get("detail") or body.get("message"))
            raise ToolError(f"Omnigent API {method} {path} failed ({resp.status_code}): {detail}")
        return resp.json() if resp.content else {}

    async def _resolve_project(project_name_or_id: str) -> dict[str, Any]:
        needle = project_name_or_id.strip()
        rows = (await _omni_request("GET", "/v1/projects")).get("data", [])
        for row in rows:
            if row.get("id") == needle:
                return row
        lowered = needle.lower()
        for row in rows:
            if str(row.get("name", "")).strip().lower() == lowered:
                return row
        raise ToolError(f"Unknown Omnigent project: {project_name_or_id!r}")

    async def _resolve_default_agent_id() -> str:
        if settings.omnigent.default_agent_id:
            return settings.omnigent.default_agent_id
        rows = (await _omni_request("GET", "/v1/agents", params={"limit": 100})).get("data", [])
        for row in rows:
            if row.get("name") == "polly" and row.get("id"):
                return str(row["id"])
        raise ToolError(
            "Default agent 'polly' was not found and OMNIGENT_DEFAULT_AGENT_ID is unset."
        )

    async def _resolve_default_host_id() -> str:
        if settings.omnigent.default_host_id:
            return settings.omnigent.default_host_id
        payload = await _omni_request("GET", "/v1/hosts")
        hosts = payload.get("hosts") or payload.get("data") or []
        for host in hosts:
            host_id = host.get("id") or host.get("host_id")
            if host.get("status") == "online" and host_id:
                return str(host_id)
        raise ToolError("No online Omnigent host found and OMNIGENT_DEFAULT_HOST_ID is unset.")

    async def _create_session_internal(
        *,
        prompt: str,
        project: str | None = None,
        title: str | None = None,
        agent_id: str | None = None,
        host_id: str | None = None,
        workspace: str | None = None,
        model_override: str | None = None,
        workflow_id: str | None = None,
        smart_routing: bool = True,
    ) -> dict[str, Any]:
        proj_id: str | None = None
        proj_cfg: dict[str, Any] = {}
        if project:
            proj = await _resolve_project(project)
            proj_id = proj.get("id")
            proj_cfg = proj.get("config") or {}

        resolved_agent = agent_id or proj_cfg.get("agent_id") or await _resolve_default_agent_id()
        resolved_host = host_id or proj_cfg.get("host_id") or await _resolve_default_host_id()
        resolved_workspace = workspace or proj_cfg.get("workspace")

        payload: dict[str, Any] = {
            "agent_id": resolved_agent,
            "initial_items": [],
            "host_id": resolved_host,
        }
        if proj_id:
            payload["project_id"] = proj_id
        if resolved_workspace:
            payload["workspace"] = resolved_workspace
        if title:
            payload["title"] = title
        if model_override:
            payload["model_override"] = model_override
        elif smart_routing:
            payload["cost_control_mode_override"] = "on"
            payload["subagent_routing_override"] = "off"
            if prompt.strip():
                payload["smart_routing_message"] = prompt
        if workflow_id:
            payload["workflow_id"] = workflow_id

        created = await _omni_request("POST", "/v1/sessions", json_body=payload)
        sid = str(created.get("id", ""))
        if sid and prompt.strip():
            await _omni_request(
                "POST",
                f"/v1/sessions/{sid}/events",
                json_body={
                    "type": "message",
                    "data": {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
                },
            )
        return {
            "id": sid,
            "title": created.get("title"),
            "status": created.get("status"),
            "projectId": created.get("project_id", proj_id),
            "workspace": created.get("workspace", resolved_workspace),
            "sessionUrl": _session_url(sid),
        }

    @mcp.tool()
    async def omnigent_get_status() -> dict[str, Any]:
        """Get Omnigent hub health, host online state, Inbox unread count, and automation counts."""
        health = await _omni_request("GET", "/health")
        info = await _omni_request("GET", "/v1/info")
        hosts_payload = await _omni_request("GET", "/v1/hosts")
        inbox = await _omni_request("GET", "/v1/inbox/items", params={"limit": 1})
        sched = await _omni_request("GET", "/v1/scheduled-tasks")

        hosts = hosts_payload.get("hosts") or hosts_payload.get("data") or []
        online_hosts = [
            {
                "id": h.get("id") or h.get("host_id"),
                "name": h.get("name"),
                "status": h.get("status"),
            }
            for h in hosts
            if h.get("status") == "online"
        ]
        tasks = sched.get("scheduled_tasks") or sched.get("data") or []
        active_count = sum(1 for t in tasks if t.get("state") == "active")
        paused_count = sum(1 for t in tasks if t.get("state") == "paused")

        return {
            "ok": health.get("status") == "ok" and len(online_hosts) > 0,
            "serverVersion": info.get("server_version"),
            "singleUser": bool(info.get("single_user", False)),
            "smartRoutingEnabled": bool(info.get("smart_routing_enabled", False)),
            "smartRoutingSources": info.get("smart_routing_sources") or {},
            "onlineHosts": online_hosts,
            "unreadInboxCount": inbox.get("unread_count", 0),
            "automationsTotal": len(tasks),
            "automationsActive": active_count,
            "automationsPaused": paused_count,
            "baseUrl": _base_url(),
            "publicUrl": _public_base_url(),
            "mutationsEnabled": settings.omnigent.allow_mutations,
        }

    def _compact_project_row(row: dict[str, Any], *, created: bool | None = None) -> dict[str, Any]:
        cfg = row.get("config") or {}
        out: dict[str, Any] = {
            "id": row.get("id"),
            "name": row.get("name"),
            "workspace": cfg.get("workspace"),
            "agentId": cfg.get("agent_id"),
            "hostId": cfg.get("host_id"),
            "useWorktree": cfg.get("use_worktree"),
            "baseBranch": cfg.get("base_branch"),
            "icon": cfg.get("icon"),
        }
        if created is not None:
            out["created"] = created
        return out

    @mcp.tool()
    async def omnigent_list_projects() -> list[dict[str, Any]]:
        """List Omnigent projects with their workspace and worktree defaults."""
        rows = (await _omni_request("GET", "/v1/projects")).get("data", [])
        return [_compact_project_row(row) for row in rows]

    @mcp.tool()
    async def omnigent_create_project(
        name: str,
        workspace: str,
        host_id: str | None = None,
        agent_id: str | None = None,
        icon: str | None = None,
        use_worktree: bool = False,
        base_branch: str | None = None,
    ) -> dict[str, Any]:
        """Create an Omnigent project for a repo or playground workspace (case-insensitive)."""
        _require_mutations("create a project")
        clean_name = name.strip()
        if not clean_name:
            raise ToolError("Project name must not be empty.")
        clean_workspace = workspace.strip()
        if not clean_workspace:
            raise ToolError("Project workspace must not be empty.")

        rows = (await _omni_request("GET", "/v1/projects")).get("data", [])
        lowered = clean_name.lower()
        existing = next(
            (r for r in rows if str(r.get("name", "")).strip().lower() == lowered),
            None,
        )
        if existing is not None:
            return _compact_project_row(existing, created=False)

        resolved_host = host_id or await _resolve_default_host_id()
        resolved_agent = agent_id or await _resolve_default_agent_id()
        config: dict[str, Any] = {
            "host_id": resolved_host,
            "workspace": clean_workspace,
            "agent_id": resolved_agent,
            "use_worktree": use_worktree,
        }
        if icon is not None:
            config["icon"] = icon
        if base_branch is not None:
            config["base_branch"] = base_branch

        created = await _omni_request(
            "POST",
            "/v1/projects",
            json_body={"name": clean_name, "config": config},
        )
        return _compact_project_row(created, created=True)

    @mcp.tool()
    async def omnigent_list_sessions(
        project_id: str | None = None,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List Omnigent sessions with optional project_id and status filtering."""
        clamped = min(max(1, limit), 100)
        params: dict[str, Any] = {"limit": clamped}
        if include_archived:
            params["include_archived"] = "true"
        rows = (await _omni_request("GET", "/v1/sessions", params=params)).get("data", [])
        pub = _public_base_url()
        out: list[dict[str, Any]] = []
        for row in rows:
            if project_id is not None and row.get("project_id") != project_id:
                continue
            if status is not None and row.get("status") != status:
                continue
            out.append(_compact_session_row(row, pub))
        return out

    @mcp.tool()
    async def omnigent_get_session(session_id: str, tail_items: int = 10) -> dict[str, Any]:
        """Get an Omnigent session snapshot, pending approvals, and recent messages."""
        sess = await _omni_request("GET", f"/v1/sessions/{session_id}")
        items = sess.get("items") or []
        limit = min(max(1, tail_items), 50)
        messages: list[dict[str, Any]] = []
        for it in items:
            if it.get("type") != "message":
                continue
            data = it.get("data") if isinstance(it.get("data"), dict) else {}
            text = _extract_item_text(it)
            messages.append(
                {
                    "id": it.get("id"),
                    "role": data.get("role") or it.get("role"),
                    "text": text,
                    "createdAt": it.get("created_at"),
                }
            )
        return {
            "id": sess.get("id", session_id),
            "title": sess.get("title"),
            "status": sess.get("status"),
            "agentName": sess.get("agent_name"),
            "llmModel": sess.get("llm_model"),
            "projectId": sess.get("project_id"),
            "workspace": sess.get("workspace"),
            "gitBranch": sess.get("git_branch"),
            "archived": bool(sess.get("archived", False)),
            "pendingElicitations": sess.get("pending_elicitations") or [],
            "sessionUrl": _session_url(str(sess.get("id", session_id))),
            "recentMessages": messages[-limit:],
        }

    @mcp.tool()
    async def omnigent_list_workflows() -> list[dict[str, Any]]:
        """List saved multi-step workflows in Omnigent."""
        payload = await _omni_request("GET", "/v1/workflows")
        rows = payload.get("workflows") or payload.get("data") or []
        return [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "description": row.get("description"),
            }
            for row in rows
        ]

    @mcp.tool()
    async def omnigent_list_automations() -> list[dict[str, Any]]:
        """List scheduled tasks and trigger automations in Omnigent."""
        payload = await _omni_request("GET", "/v1/scheduled-tasks")
        rows = payload.get("scheduled_tasks") or payload.get("data") or []
        return [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "state": row.get("state"),
                "rrule": row.get("rrule"),
                "timezone": row.get("timezone"),
                "modelOverride": row.get("model_override"),
                "lastRunStatus": row.get("last_run_status"),
                "lastRunAt": row.get("last_run_at"),
                "lastRunConversationId": row.get("last_run_conversation_id"),
            }
            for row in rows
        ]

    @mcp.tool()
    async def omnigent_list_inbox(
        status: Literal["all", "unread", "read"] = "unread",
        limit: int = 30,
    ) -> dict[str, Any]:
        """List Omnigent Inbox items and sessions currently waiting on user approval."""
        clamped = min(max(1, limit), 100)
        params: dict[str, Any] = {"limit": clamped}
        if status != "all":
            params["status"] = status
        inbox = await _omni_request("GET", "/v1/inbox/items", params=params)
        raw_items = inbox.get("data") or inbox.get("items") or []
        items = [
            {
                "id": it.get("id"),
                "status": it.get("status"),
                "kind": it.get("kind"),
                "title": it.get("title"),
                "topic": it.get("topic"),
                "bodyMd": it.get("body_md"),
                "sourceSessionId": it.get("source_session_id"),
                "createdAt": it.get("created_at"),
            }
            for it in raw_items
        ]
        sessions = (await _omni_request("GET", "/v1/sessions", params={"limit": 100})).get(
            "data", []
        )
        pub = _public_base_url()
        pending_approvals = [
            _compact_session_row(row, pub)
            for row in sessions
            if (row.get("pending_elicitations_count") or 0) > 0
        ]
        return {
            "unreadCount": inbox.get("unread_count", 0),
            "items": items,
            "pendingApprovalSessions": pending_approvals,
        }

    @mcp.tool()
    async def omnigent_start_session(
        prompt: str,
        project: str | None = None,
        title: str | None = None,
        agent_id: str | None = None,
        host_id: str | None = None,
        workspace: str | None = None,
        model_override: str | None = None,
        workflow_id: str | None = None,
        smart_routing: bool = True,
    ) -> dict[str, Any]:
        """Start a new Omnigent session, inheriting defaults from an optional project name or ID.

        Guidelines for callers:
        - For a new repo or playground, call `omnigent_create_project` first (or pass an
          explicit `workspace` directory such as `/Users/spencer/repos/<repo-name>`); do NOT
          attach unrelated coding sessions to `Ops & Digests` (reserved for scheduled digests/ops).
        - Leave `model_override` unset so Smart Routing (`smart_routing=True`) selects the
          top-level model automatically (while sub-agents keep their native subscription
          defaults) instead of defaulting straight to Fable.
        - Use `omnigent_update_session` to move, rename, archive, or update Smart Routing on
          an existing session.
        """
        _require_mutations("start a session")
        return await _create_session_internal(
            prompt=prompt,
            project=project,
            title=title,
            agent_id=agent_id,
            host_id=host_id,
            workspace=workspace,
            model_override=model_override,
            workflow_id=workflow_id,
            smart_routing=smart_routing,
        )

    @mcp.tool()
    async def omnigent_update_session(
        session_id: str,
        project: str | None = None,
        title: str | None = None,
        archived: bool | None = None,
        smart_routing: bool | None = None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing Omnigent session (project, title, archive, or model/Smart Routing)."""
        _require_mutations("update a session")
        body: dict[str, Any] = {}
        if project is not None:
            proj = await _resolve_project(project)
            body["project_id"] = proj["id"]
        if title is not None:
            body["title"] = title
        if archived is not None:
            body["archived"] = archived
        if model_override is not None:
            body["model_override"] = model_override
        if smart_routing is True:
            body["cost_control_mode_override"] = "on"
            body["subagent_routing_override"] = "off"
        elif smart_routing is False:
            body["cost_control_mode_override"] = "off"
            body["subagent_routing_override"] = "off"
        if not body:
            raise ToolError("Provide at least one field to update.")

        updated = await _omni_request(
            "PATCH",
            f"/v1/sessions/{session_id}",
            json_body=body,
        )
        sid = str(updated.get("id", session_id))
        return {
            "id": sid,
            "title": updated.get("title"),
            "projectId": updated.get("project_id"),
            "workspace": updated.get("workspace"),
            "archived": bool(updated.get("archived", False)),
            "costControlMode": updated.get("cost_control_mode_override"),
            "subagentRouting": updated.get("subagent_routing_override"),
            "modelOverride": updated.get("model_override"),
            "sessionUrl": _session_url(sid),
        }

    @mcp.tool()
    async def omnigent_send_message(session_id: str, message: str) -> dict[str, Any]:
        """Send a user message into an existing Omnigent session."""
        _require_mutations("send a session message")
        resp = await _omni_request(
            "POST",
            f"/v1/sessions/{session_id}/events",
            json_body={
                "type": "message",
                "data": {"role": "user", "content": [{"type": "input_text", "text": message}]},
            },
        )
        return {
            "sessionId": session_id,
            "accepted": True,
            "sessionUrl": _session_url(session_id),
            "response": resp,
        }

    @mcp.tool()
    async def omnigent_run_workflow(
        workflow: str,
        details: str = "",
        project: str | None = None,
        title: str | None = None,
        model_override: str | None = None,
        smart_routing: bool = True,
    ) -> dict[str, Any]:
        """Launch a saved Omnigent workflow by exact ID or case-insensitive name."""
        _require_mutations("run a workflow")
        payload = await _omni_request("GET", "/v1/workflows")
        rows = payload.get("workflows") or payload.get("data") or []
        needle = workflow.strip()
        match = next((w for w in rows if w.get("id") == needle), None)
        if match is None:
            lowered = needle.lower()
            match = next(
                (w for w in rows if str(w.get("name", "")).strip().lower() == lowered),
                None,
            )
        if match is None:
            raise ToolError(f"Unknown Omnigent workflow: {workflow!r}")

        wf_id = str(match["id"])
        wf_name = str(match.get("name") or wf_id)
        prompt = f'/workflow Run the saved workflow "{wf_name}" (ID {wf_id}).'
        if details.strip():
            prompt = f"{prompt}\n\n{details.strip()}"

        created = await _create_session_internal(
            prompt=prompt,
            project=project,
            title=title,
            model_override=model_override,
            workflow_id=wf_id,
            smart_routing=smart_routing,
        )
        return {
            **created,
            "workflowId": wf_id,
            "workflowName": wf_name,
        }

    @mcp.tool()
    async def omnigent_mark_inbox_item(
        item_id: str, status: Literal["read", "unread"] = "read"
    ) -> dict[str, Any]:
        """Mark an Omnigent Inbox item as read or unread."""
        _require_mutations("update an inbox item")
        resp = await _omni_request(
            "PATCH", f"/v1/inbox/items/{item_id}", json_body={"status": status}
        )
        item_obj = resp.get("item") if isinstance(resp.get("item"), dict) else {}
        return {
            "itemId": item_id,
            "status": item_obj.get("status", status),
            "unreadCount": resp.get("unread_count"),
        }

    @mcp.tool()
    async def omnigent_resolve_approval(
        session_id: str,
        elicitation_id: str,
        action: Literal["accept", "decline", "cancel"],
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a pending Omnigent elicitation/approval prompt for a session."""
        _require_mutations("resolve a pending approval")
        body: dict[str, Any] = {"action": action}
        if content is not None:
            body["content"] = content
        resp = await _omni_request(
            "POST",
            f"/v1/sessions/{session_id}/elicitations/{elicitation_id}/resolve",
            json_body=body,
        )
        return {
            "sessionId": session_id,
            "elicitationId": elicitation_id,
            "action": action,
            "resolved": True,
            "response": resp,
        }

    @mcp.tool()
    async def omnigent_memory_list(path_prefix: str = "") -> dict[str, Any]:
        """List entries in Omnigent unified memory (/v1/memory)."""
        clean_prefix = ("/" + path_prefix.strip().lstrip("/")) if path_prefix.strip() else ""
        params = {"prefix": clean_prefix} if clean_prefix else None
        resp = await _omni_request("GET", "/v1/memory/entries", params=params)
        entries = resp.get("entries") if isinstance(resp.get("entries"), list) else []
        return {"count": len(entries), "entries": entries}

    @mcp.tool()
    async def omnigent_memory_get(path: str) -> dict[str, Any]:
        """Read a single Omnigent unified memory entry by path (e.g. /feedback/workflow-rules)."""
        clean = "/" + path.strip().lstrip("/")
        return await _omni_request("GET", "/v1/memory/entry", params={"path": clean})

    @mcp.tool()
    async def omnigent_memory_search(
        query: str, path_prefix: str = "", limit: int = 10
    ) -> dict[str, Any]:
        """Search Omnigent unified memory by keyword query and optional path prefix."""
        clean_q = query.strip()
        clamped = max(1, min(limit, 50))
        clean_prefix = ("/" + path_prefix.strip().lstrip("/")) if path_prefix.strip() else ""
        body: dict[str, Any] = {"query": clean_q, "limit": clamped}
        if clean_prefix:
            body["path_prefix"] = clean_prefix
        try:
            return await _omni_request("POST", "/v1/memory/search", json_body=body)
        except ToolError as exc:
            msg = str(exc).lower()
            if "(404)" not in msg and "not available" not in msg:
                raise

        list_params = {"prefix": clean_prefix} if clean_prefix else None
        listing_resp = await _omni_request("GET", "/v1/memory/entries", params=list_params)
        raw_entries = listing_resp.get("entries")
        entries = raw_entries if isinstance(raw_entries, list) else []
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for item in entries:
            item_path = str(item.get("path") or "")
            if not item_path:
                continue
            try:
                ent = await _omni_request("GET", "/v1/memory/entry", params={"path": item_path})
            except ToolError as get_exc:
                if "(404)" in str(get_exc):
                    continue
                raise
            score = score_omnigent_memory_entry(ent, clean_q)
            if score > 0:
                scored.append((score, item_path, ent))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return {
            "hits": [{"entry": row[2], "score": row[0]} for row in scored[:clamped]],
            "searchMode": "client_scan",
        }

    @mcp.tool()
    async def omnigent_memory_write(
        path: str, content: str, description: str = ""
    ) -> dict[str, Any]:
        """Create or update an Omnigent unified memory entry."""
        _require_mutations("write unified memory")
        clean = "/" + path.strip().lstrip("/")
        return await _omni_request(
            "PUT",
            "/v1/memory/entry",
            json_body={
                "path": clean,
                "content": content,
                "description": description.strip() or None,
            },
        )

    @mcp.tool()
    async def omnigent_memory_delete(path: str) -> dict[str, Any]:
        """Delete an Omnigent unified memory entry by path."""
        _require_mutations("delete unified memory")
        clean = "/" + path.strip().lstrip("/")
        return await _omni_request("DELETE", "/v1/memory/entry", params={"path": clean})

    return mcp
