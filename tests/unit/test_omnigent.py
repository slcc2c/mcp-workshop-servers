"""Unit tests for the async Omnigent REST/SSE bridge MCP server."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from mcp_stack.core.config import OmnigentSettings
from mcp_stack.gateway.app import build_gateway_app
from mcp_stack.servers.omnigent import create_omnigent_server

pytestmark = pytest.mark.unit


def _asgi_factory(app):
    def _factory(**kwargs):
        kwargs.pop("base_url", None)
        kwargs["follow_redirects"] = False
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            **kwargs,
        )

    return _factory


def _mock_read_routes(router: respx.MockRouter) -> None:
    router.get("http://omni.test/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    router.get("http://omni.test/v1/info").mock(
        return_value=httpx.Response(
            200,
            json={
                "server_version": "0.23.0",
                "single_user": True,
                "smart_routing_enabled": True,
                "smart_routing_sources": {"external": False, "oss": True},
            },
        )
    )
    router.get("http://omni.test/v1/hosts").mock(
        return_value=httpx.Response(
            200,
            json={
                "hosts": [
                    {"id": "host_1", "name": "macstudio.local", "status": "online"},
                    {"id": "host_2", "name": "stale", "status": "offline"},
                ]
            },
        )
    )
    router.get("http://omni.test/v1/inbox/items").mock(
        return_value=httpx.Response(
            200,
            json={
                "unread_count": 2,
                "data": [
                    {
                        "id": "inbox_1",
                        "status": "unread",
                        "kind": "info",
                        "title": "Daily Brief",
                        "topic": "health",
                        "body_md": "All good",
                        "source_session_id": "sess_1",
                        "created_at": 1795600000,
                    }
                ],
            },
        )
    )
    router.get("http://omni.test/v1/scheduled-tasks").mock(
        return_value=httpx.Response(
            200,
            json={
                "scheduled_tasks": [
                    {
                        "id": "task_1",
                        "name": "Morning Digest",
                        "state": "active",
                        "rrule": "FREQ=DAILY",
                        "timezone": "America/Chicago",
                        "model_override": "sonnet",
                        "last_run_status": "succeeded",
                        "last_run_at": 1795600000,
                        "last_run_conversation_id": "sess_1",
                    },
                    {
                        "id": "task_2",
                        "name": "Slack Self-DM",
                        "state": "paused",
                        "rrule": "FREQ=MINUTELY;INTERVAL=10",
                        "timezone": "America/Chicago",
                        "model_override": "haiku",
                        "last_run_status": None,
                        "last_run_at": None,
                        "last_run_conversation_id": None,
                    },
                ]
            },
        )
    )
    router.get("http://omni.test/v1/projects").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "proj_printer",
                        "name": "printer",
                        "config": {
                            "host_id": "host_1",
                            "workspace": "/repos/printer",
                            "agent_id": "agent_polly",
                            "use_worktree": True,
                            "base_branch": "main",
                            "icon": "printer",
                        },
                    }
                ]
            },
        )
    )
    router.get("http://omni.test/v1/sessions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "sess_1",
                        "title": "Fix printer CI",
                        "status": "idle",
                        "agent_name": "polly",
                        "project_id": "proj_printer",
                        "workspace": "/repos/printer",
                        "pending_elicitations_count": 1,
                        "archived": False,
                        "updated_at": 1795600000,
                    },
                    {
                        "id": "sess_2",
                        "title": "Other chat",
                        "status": "running",
                        "agent_name": "polly",
                        "project_id": "proj_other",
                        "workspace": "/repos/other",
                        "pending_elicitations_count": 0,
                        "archived": False,
                        "updated_at": 1795600100,
                    },
                ]
            },
        )
    )
    router.get("http://omni.test/v1/sessions/sess_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "sess_1",
                "title": "Fix printer CI",
                "status": "idle",
                "agent_name": "polly",
                "llm_model": "claude-opus-5",
                "project_id": "proj_printer",
                "workspace": "/repos/printer",
                "git_branch": "fix/ci",
                "archived": False,
                "pending_elicitations": [{"elicitation_id": "el_1"}],
                "items": [
                    {
                        "id": "it_1",
                        "type": "message",
                        "created_at": 1795600001,
                        "data": {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "CI is healthy."}],
                        },
                    }
                ],
            },
        )
    )
    router.get("http://omni.test/v1/workflows").mock(
        return_value=httpx.Response(
            200,
            json={
                "workflows": [
                    {
                        "id": "wf_1",
                        "name": "polly-implement-and-cross-review",
                        "description": "Implement in worktree and cross-review",
                    }
                ]
            },
        )
    )
    router.get("http://omni.test/v1/agents").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "agent_polly", "name": "polly"}]},
        )
    )


async def test_omnigent_read_tools_and_mutation_gate(make_settings) -> None:
    settings = make_settings(
        omnigent=OmnigentSettings(
            base_url="http://omni.test",
            public_url="https://studio.ts.net:8446",
            allow_mutations=False,
        )
    )

    with respx.mock(assert_all_called=False) as router:
        _mock_read_routes(router)
        async with httpx.AsyncClient() as http_cli:
            mcp = create_omnigent_server(settings, http_client=http_cli)
            async with Client(mcp) as client:
                raw_status = await client.call_tool("omnigent_get_status", {})
                status = json.loads(raw_status.content[0].text)
                assert status["ok"] is True
                assert status["serverVersion"] == "0.23.0"
                assert status["smartRoutingEnabled"] is True
                assert status["smartRoutingSources"] == {"external": False, "oss": True}
                assert status["automationsActive"] == 1
                assert status["automationsPaused"] == 1
                assert status["mutationsEnabled"] is False

                projects = json.loads(
                    (await client.call_tool("omnigent_list_projects", {})).content[0].text
                )
                assert projects[0]["name"] == "printer"
                assert projects[0]["baseBranch"] == "main"

                sessions = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_list_sessions", {"project_id": "proj_printer"}
                        )
                    ).content[0].text
                )
                assert len(sessions) == 1
                assert sessions[0]["sessionUrl"] == "https://studio.ts.net:8446/c/sess_1"

                detail = json.loads(
                    (await client.call_tool("omnigent_get_session", {"session_id": "sess_1"}))
                    .content[0]
                    .text
                )
                assert detail["recentMessages"][0]["text"] == "CI is healthy."
                assert detail["sessionUrl"] == "https://studio.ts.net:8446/c/sess_1"

                wfs = json.loads(
                    (await client.call_tool("omnigent_list_workflows", {})).content[0].text
                )
                assert wfs[0]["id"] == "wf_1"

                autos = json.loads(
                    (await client.call_tool("omnigent_list_automations", {})).content[0].text
                )
                assert len(autos) == 2

                inbox = json.loads(
                    (await client.call_tool("omnigent_list_inbox", {})).content[0].text
                )
                assert inbox["unreadCount"] == 2
                assert len(inbox["pendingApprovalSessions"]) == 1

                for tool_name, args in [
                    ("omnigent_create_project", {"name": "demo", "workspace": "/repos/demo"}),
                    ("omnigent_start_session", {"prompt": "hi"}),
                    ("omnigent_update_session", {"session_id": "sess_1", "archived": True}),
                    ("omnigent_send_message", {"session_id": "sess_1", "message": "hi"}),
                    ("omnigent_run_workflow", {"workflow": "polly-implement-and-cross-review"}),
                    ("omnigent_mark_inbox_item", {"item_id": "inbox_1"}),
                    (
                        "omnigent_resolve_approval",
                        {"session_id": "sess_1", "elicitation_id": "el_1", "action": "accept"},
                    ),
                ]:
                    with pytest.raises(ToolError, match="OMNIGENT_ALLOW_MUTATIONS=false"):
                        await client.call_tool(tool_name, args)


async def test_omnigent_mutation_tools_when_enabled(make_settings) -> None:
    settings = make_settings(
        omnigent=OmnigentSettings(
            base_url="http://omni.test",
            public_url="https://studio.ts.net:8446",
            allow_mutations=True,
        )
    )

    with respx.mock(assert_all_called=False) as router:
        _mock_read_routes(router)
        start_route = router.post("http://omni.test/v1/sessions").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "sess_new",
                    "title": "New Work",
                    "status": "running",
                    "project_id": "proj_printer",
                    "workspace": "/repos/printer",
                },
            )
        )
        msg_route = router.post("http://omni.test/v1/sessions/sess_1/events").mock(
            return_value=httpx.Response(202, json={"accepted": True})
        )
        new_msg_route = router.post("http://omni.test/v1/sessions/sess_new/events").mock(
            return_value=httpx.Response(202, json={"accepted": True})
        )
        inbox_route = router.patch("http://omni.test/v1/inbox/items/inbox_1").mock(
            return_value=httpx.Response(
                200,
                json={"item": {"id": "inbox_1", "status": "read"}, "unread_count": 1},
            )
        )
        elicit_route = router.post(
            "http://omni.test/v1/sessions/sess_1/elicitations/el_1/resolve"
        ).mock(return_value=httpx.Response(202, json={"ok": True}))
        project_route = router.post("http://omni.test/v1/projects").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "proj_demo",
                    "name": "demo-app",
                    "config": {
                        "host_id": "host_1",
                        "workspace": "/repos/demo-app",
                        "agent_id": "agent_polly",
                        "use_worktree": False,
                    },
                },
            )
        )
        patch_sess_route = router.patch("http://omni.test/v1/sessions/sess_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "sess_1",
                    "title": "Renamed Work",
                    "project_id": "proj_printer",
                    "workspace": "/repos/printer",
                    "archived": True,
                    "cost_control_mode_override": "on",
                    "subagent_routing_override": "off",
                    "model_override": None,
                },
            )
        )

        async with httpx.AsyncClient() as http_cli:
            mcp = create_omnigent_server(settings, http_client=http_cli)
            async with Client(mcp) as client:
                started = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_start_session",
                            {"prompt": "Check status", "project": "printer", "title": "New Work"},
                        )
                    ).content[0].text
                )
                assert started["id"] == "sess_new"
                assert started["sessionUrl"] == "https://studio.ts.net:8446/c/sess_new"
                sent_req = start_route.calls[0].request
                assert sent_req.headers["Origin"] == "http://omni.test"
                sent_body = json.loads(sent_req.content)
                assert "initial_input" not in sent_body
                assert sent_body["project_id"] == "proj_printer"
                assert sent_body["workspace"] == "/repos/printer"
                assert sent_body["agent_id"] == "agent_polly"
                assert sent_body["cost_control_mode_override"] == "on"
                assert sent_body["subagent_routing_override"] == "off"
                assert sent_body["smart_routing_message"] == "Check status"

                wf_started = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_run_workflow",
                            {
                                "workflow": "polly-implement-and-cross-review",
                                "details": "Fix issue #12",
                                "project": "printer",
                            },
                        )
                    ).content[0].text
                )
                assert wf_started["workflowId"] == "wf_1"
                wf_body = json.loads(start_route.calls[1].request.content)
                assert wf_body["workflow_id"] == "wf_1"
                assert "initial_input" not in wf_body
                assert wf_body["cost_control_mode_override"] == "on"
                assert wf_body["subagent_routing_override"] == "off"
                assert "Fix issue #12" in wf_body["smart_routing_message"]

                await client.call_tool(
                    "omnigent_start_session",
                    {
                        "prompt": "Pinned model",
                        "project": "printer",
                        "model_override": "claude-opus-5",
                    },
                )
                pinned_body = json.loads(start_route.calls[2].request.content)
                assert pinned_body["model_override"] == "claude-opus-5"
                assert "cost_control_mode_override" not in pinned_body
                assert "subagent_routing_override" not in pinned_body
                assert "smart_routing_message" not in pinned_body

                await client.call_tool(
                    "omnigent_start_session",
                    {
                        "prompt": "No smart routing",
                        "project": "printer",
                        "smart_routing": False,
                    },
                )
                unrouted_body = json.loads(start_route.calls[3].request.content)
                assert "model_override" not in unrouted_body
                assert "cost_control_mode_override" not in unrouted_body
                assert "subagent_routing_override" not in unrouted_body
                assert "smart_routing_message" not in unrouted_body

                assert new_msg_route.call_count == 4
                first_event = json.loads(new_msg_route.calls[0].request.content)
                assert first_event["data"]["content"][0]["text"] == "Check status"
                wf_event = json.loads(new_msg_route.calls[1].request.content)
                assert "Fix issue #12" in wf_event["data"]["content"][0]["text"]

                sent_msg = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_send_message",
                            {"session_id": "sess_1", "message": "Proceed"},
                        )
                    ).content[0].text
                )
                assert sent_msg["accepted"] is True
                assert msg_route.call_count == 1

                marked = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_mark_inbox_item", {"item_id": "inbox_1", "status": "read"}
                        )
                    ).content[0].text
                )
                assert marked["unreadCount"] == 1
                assert inbox_route.call_count == 1

                resolved = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_resolve_approval",
                            {
                                "session_id": "sess_1",
                                "elicitation_id": "el_1",
                                "action": "accept",
                            },
                        )
                    ).content[0].text
                )
                assert resolved["resolved"] is True
                assert elicit_route.call_count == 1

                existing_proj = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_create_project",
                            {"name": "Printer", "workspace": "/repos/printer"},
                        )
                    ).content[0].text
                )
                assert existing_proj["id"] == "proj_printer"
                assert existing_proj["created"] is False
                assert project_route.call_count == 0

                created_proj = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_create_project",
                            {"name": "demo-app", "workspace": "/repos/demo-app"},
                        )
                    ).content[0].text
                )
                assert created_proj["id"] == "proj_demo"
                assert created_proj["created"] is True
                assert project_route.call_count == 1
                proj_body = json.loads(project_route.calls[0].request.content)
                assert proj_body == {
                    "name": "demo-app",
                    "config": {
                        "host_id": "host_1",
                        "workspace": "/repos/demo-app",
                        "agent_id": "agent_polly",
                        "use_worktree": False,
                    },
                }

                updated_sess = json.loads(
                    (
                        await client.call_tool(
                            "omnigent_update_session",
                            {
                                "session_id": "sess_1",
                                "project": "printer",
                                "title": "Renamed Work",
                                "archived": True,
                                "smart_routing": True,
                            },
                        )
                    ).content[0].text
                )
                assert updated_sess["id"] == "sess_1"
                assert updated_sess["projectId"] == "proj_printer"
                assert updated_sess["archived"] is True
                assert updated_sess["costControlMode"] == "on"
                assert updated_sess["subagentRouting"] == "off"
                assert updated_sess["sessionUrl"] == "https://studio.ts.net:8446/c/sess_1"
                assert patch_sess_route.call_count == 1
                patch_body = json.loads(patch_sess_route.calls[0].request.content)
                assert patch_body == {
                    "project_id": "proj_printer",
                    "title": "Renamed Work",
                    "archived": True,
                    "cost_control_mode_override": "on",
                    "subagent_routing_override": "off",
                }


async def test_gateway_mounts_omnigent_and_ops_profile(make_settings) -> None:
    settings = make_settings()
    settings.mlflow.proxy_upstream_mcp = False
    settings.unity_catalog.dynamic_function_tools = False
    app = build_gateway_app(settings)
    factory = _asgi_factory(app)

    async with app.router.lifespan_context(app):
        async with Client(
            StreamableHttpTransport(
                "http://testserver/servers/omnigent/mcp", httpx_client_factory=factory
            )
        ) as omni_cli:
            names = {t.name for t in await omni_cli.list_tools()}
            assert "omnigent_get_status" in names
            assert "omnigent_create_project" in names
            assert "omnigent_update_session" in names
            assert "omnigent_resolve_approval" in names

        async with Client(
            StreamableHttpTransport(
                "http://testserver/profiles/ops/mcp", httpx_client_factory=factory
            )
        ) as ops_cli:
            ops_names = {t.name for t in await ops_cli.list_tools()}
            assert "omnigent_get_status" in ops_names
            assert "omnigent_memory_list" in ops_names
            assert "omnigent_memory_write" in ops_names


async def test_omnigent_unified_memory_tools_and_mutation_gate(make_settings) -> None:
    settings = make_settings()
    settings.omnigent = OmnigentSettings(
        base_url="http://omni.test",
        allow_mutations=False,
    )
    mem_store: dict[str, dict[str, object]] = {
        "/feedback/workflow-rules": {
            "path": "/feedback/workflow-rules",
            "content": "Workflow rule 1",
            "description": "Rules",
            "created_at": 1,
            "updated_at": 1,
        }
    }

    with respx.mock(assert_all_called=False) as router:
        entries_route = router.get("http://omni.test/v1/memory/entries").mock(
            return_value=httpx.Response(
                200,
                json={"entries": [{**v, "content": ""} for v in mem_store.values()]},
            )
        )
        router.get("http://omni.test/v1/memory/entry").mock(
            side_effect=lambda req: httpx.Response(
                200, json=mem_store[req.url.params["path"]]
            )
        )
        search_route = router.post("http://omni.test/v1/memory/search").mock(
            return_value=httpx.Response(
                200, json={"hits": [{"entry": mem_store["/feedback/workflow-rules"], "score": 1.0}]}
            )
        )
        put_route = router.put("http://omni.test/v1/memory/entry").mock(
            return_value=httpx.Response(
                200,
                json={
                    "path": "/notes/test",
                    "content": "hello",
                    "description": "d",
                    "created_at": 2,
                    "updated_at": 2,
                },
            )
        )
        del_route = router.delete("http://omni.test/v1/memory/entry").mock(
            return_value=httpx.Response(200, json={"deleted": True})
        )

        # Read-only mode permits read/search but blocks writes
        ro_srv = create_omnigent_server(settings)
        async with Client(ro_srv) as client:
            res_list = await client.call_tool("omnigent_memory_list", {"path_prefix": "/feedback"})
            listed = json.loads(res_list.content[0].text)
            assert listed["count"] == 1
            assert entries_route.calls[0].request.url.params.get("prefix") == "/feedback"
            got = json.loads(
                (
                    await client.call_tool(
                        "omnigent_memory_get", {"path": "/feedback/workflow-rules"}
                    )
                ).content[0].text
            )
            assert got["content"] == "Workflow rule 1"
            res_search = await client.call_tool("omnigent_memory_search", {"query": "rule"})
            hits = json.loads(res_search.content[0].text)
            assert len(hits["hits"]) == 1
            # When Omnigent /v1/memory/search returns 404, fall back to client_scan
            search_route.mock(
                return_value=httpx.Response(
                    404,
                    json={"error": {"code": "not_found", "message": "Search unavailable"}},
                )
            )
            fb_search = await client.call_tool("omnigent_memory_search", {"query": "rule"})
            fb_hits = json.loads(fb_search.content[0].text)
            assert fb_hits["searchMode"] == "client_scan"
            assert len(fb_hits["hits"]) == 1
            assert fb_hits["hits"][0]["entry"]["path"] == "/feedback/workflow-rules"
            with pytest.raises(ToolError, match="disabled"):
                await client.call_tool(
                    "omnigent_memory_write", {"path": "/notes/test", "content": "hello"}
                )

        # Mutations enabled permits write/delete with Origin header
        settings.omnigent.allow_mutations = True
        rw_srv = create_omnigent_server(settings)
        async with Client(rw_srv) as client:
            wr = json.loads(
                (
                    await client.call_tool(
                        "omnigent_memory_write",
                        {"path": "notes/test", "content": "hello", "description": "d"},
                    )
                ).content[0].text
            )
            assert wr["path"] == "/notes/test"
            assert put_route.call_count == 1
            assert put_route.calls[0].request.headers["Origin"] == "http://omni.test"

            res_del = await client.call_tool("omnigent_memory_delete", {"path": "/notes/test"})
            dl = json.loads(res_del.content[0].text)
            assert dl["deleted"] is True
            assert del_route.call_count == 1
            assert del_route.calls[0].request.headers["Origin"] == "http://omni.test"
