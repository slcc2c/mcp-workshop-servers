"""Co-hosted MLflow 3.18 ResponsesAgent (AgentServer @invoke / @stream) wired to Gateway MCP."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import mlflow
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mlflow.genai.agent_server import AgentServer, invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    create_function_call_item,
    create_function_call_output_item,
    create_text_delta,
    create_text_output_item,
)

from mcp_stack.core.config import MCPStackSettings
from mcp_stack.core.secrets import SecretResolver
from mcp_stack.core.tracing import get_or_create_gateway_logged_model
from mcp_stack.skill_registry import get_mlflow_skill_detail


def _extract_input_messages(request: ResponsesAgentRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in request.input:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        role = str(data.get("role") or "user")
        content = data.get("content")
        if isinstance(content, list):
            parts = [
                str(c.get("text") or c.get("content") or "")
                for c in content
                if isinstance(c, dict)
            ]
            text = "\n".join(p for p in parts if p)
        else:
            text = str(content or "")
        if text:
            messages.append({"role": role, "content": text})
    return messages


def _load_prompt_instruction(settings: MCPStackSettings, prompt_uri: str) -> str | None:
    if not prompt_uri:
        return None
    try:
        import mlflow.genai

        mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
        if settings.mlflow.experiment_name:
            mlflow.set_experiment(settings.mlflow.experiment_name)
        pv = mlflow.genai.load_prompt(prompt_uri)
        tmpl = getattr(pv, "template", None)
        return str(tmpl) if tmpl else None
    except Exception:
        return None


def _load_skills_instructions(settings: MCPStackSettings, skills: list[str]) -> str:
    sections: list[str] = []
    for skill_name in skills:
        clean = str(skill_name).strip()
        if not clean:
            continue
        try:
            detail = get_mlflow_skill_detail(settings, clean)
            md = detail.get("skillMd")
            if md:
                sections.append(f"## Skill: {clean}\n{md[:4000]}")
        except Exception:
            continue
    return "\n\n".join(sections)


def _mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for tool in tools:
        t_name = str(getattr(tool, "name", "") or "")
        if not t_name:
            continue
        params = getattr(tool, "inputSchema", None) or getattr(tool, "parameters", None)
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": t_name,
                    "description": (getattr(tool, "description", None) or "")[:500],
                    "parameters": params,
                },
            }
        )
    return specs


async def _chat_completion(
    http_client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float | None = None,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    if temperature is not None:
        payload["temperature"] = temperature
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    resp = await http_client.post(endpoint, headers=headers, json=payload, timeout=180.0)
    resp.raise_for_status()
    return dict(resp.json())


def _resolve_llm_config(
    settings: MCPStackSettings,
    custom_inputs: dict[str, Any],
) -> tuple[str, str, str]:
    resolver = SecretResolver(settings.secrets)
    base_url = str(
        custom_inputs.get("base_url")
        or settings.agent.llm_base_url
        or f"{settings.mlflow.tracking_uri.rstrip('/')}/gateway/mlflow/v1"
    ).strip()
    model = str(custom_inputs.get("model") or settings.agent.llm_model).strip()
    raw_key = custom_inputs.get("api_key") or settings.agent.llm_api_key
    api_key = ""
    if raw_key:
        try:
            api_key = resolver.resolve(raw_key) or ""
        except Exception:
            api_key = ""
    return base_url, model, api_key


async def stream_workshop_agent(
    request: ResponsesAgentRequest,
    *,
    settings: MCPStackSettings,
    http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    mcp_client_factory: Callable[[str], Client] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> AsyncIterator[ResponsesAgentStreamEvent]:
    """Run one streaming multi-turn ResponsesAgent execution wired to curated MCP tools."""
    mlflow.set_tracking_uri(settings.mlflow.tracking_uri)
    custom = dict(request.custom_inputs or {})
    profile = str(custom.get("profile") or settings.agent.default_profile or "discover").strip()
    raw_rounds = int(custom.get("max_tool_rounds") or settings.agent.max_tool_rounds)
    max_rounds = max(1, min(raw_rounds, 12))
    temperature = (
        float(custom["temperature"])
        if custom.get("temperature") is not None
        else request.temperature
    )
    base_url, model, api_key = _resolve_llm_config(settings, custom)

    system_parts = [
        (
            "You are the MCP Workshop Agent. Use connected MCP tools directly to verify facts; "
            "call only the tool(s) needed for the user request, cite exact observed identifiers, "
            "names, statuses, and counts, and never invent or extrapolate unobserved values. "
            "If a tool returns a read-only or sandbox policy refusal, state that clearly "
            "without retrying or fabricating outputs."
        ),
        f"Active gateway MCP profile: {profile}.",
    ]
    prompt_uri = str(custom.get("prompt_uri") or "").strip()
    if prompt_uri and (tmpl := _load_prompt_instruction(settings, prompt_uri)):
        system_parts.append(tmpl)
    raw_skills = custom.get("skills")
    if (
        isinstance(raw_skills, list)
        and raw_skills
        and (sk_text := _load_skills_instructions(settings, raw_skills))
    ):
        system_parts.append(sk_text)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        *_extract_input_messages(request),
    ]

    gw_base = f"http://{settings.gateway.host}:{settings.gateway.port}".rstrip("/")
    mcp_url = f"{gw_base}/profiles/{profile}/mcp"
    gw_token = next(iter(settings.gateway.clients.keys()), "")
    mcp_headers = {"Authorization": f"Bearer {gw_token}"} if gw_token else None

    if mcp_client_factory is not None:
        mcp_cli = mcp_client_factory(mcp_url)
    else:
        mcp_cli = Client(StreamableHttpTransport(mcp_url, headers=mcp_headers))

    created_http: httpx.AsyncClient | None = None
    http_client = http_client_factory() if http_client_factory else httpx.AsyncClient()
    if http_client_factory is None:
        created_http = http_client

    logged_model_id = (
        get_or_create_gateway_logged_model(settings)
        if settings.mlflow.tracing_enabled
        else None
    )
    _ = logged_model_id

    try:
        async with mcp_cli:
            raw_tools = await mcp_cli.list_tools()
            openai_tools = _mcp_tools_to_openai(list(raw_tools))
            estimated_schema_tokens = sum(
                max(1, len(json.dumps(t, default=str)) // 4) for t in openai_tools
            )
            prompt_tokens = 0
            completion_tokens = 0
            tool_call_names: list[str] = []
            if telemetry is not None:
                telemetry.update(
                    {
                        "profile": profile,
                        "model": model,
                        "toolCount": len(openai_tools),
                        "estimatedSchemaTokens": estimated_schema_tokens,
                        "promptTokens": 0,
                        "completionTokens": 0,
                        "toolCalls": tool_call_names,
                    }
                )

            final_text = ""
            for _round in range(max_rounds):
                with mlflow.start_span(name="agent_llm_turn", span_type="LLM") as llm_span:
                    llm_span.set_inputs(
                        {
                            "model": model,
                            "profile": profile,
                            "message_count": len(messages),
                            "tool_count": len(openai_tools),
                            "estimated_schema_tokens": estimated_schema_tokens,
                        }
                    )
                    completion = await _chat_completion(
                        http_client,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        tools=openai_tools,
                        temperature=temperature,
                    )
                    usage = dict(completion.get("usage") or {})
                    prompt_tokens += int(usage.get("prompt_tokens") or 0)
                    completion_tokens += int(usage.get("completion_tokens") or 0)
                    choice = (completion.get("choices") or [{}])[0]
                    msg = dict(choice.get("message") or {})
                    tool_calls = list(msg.get("tool_calls") or [])
                    round_calls = [
                        str((tc.get("function") or {}).get("name") or "") for tc in tool_calls
                    ]
                    tool_call_names.extend([c for c in round_calls if c])
                    if telemetry is not None:
                        telemetry["promptTokens"] = prompt_tokens
                        telemetry["completionTokens"] = completion_tokens
                    llm_span.set_outputs(
                        {
                            "choices": len(completion.get("choices") or []),
                            "tool_calls": round_calls,
                            "usage": usage,
                        }
                    )

                if not tool_calls:
                    final_text = str(msg.get("content") or "")
                    break

                messages.append(msg)
                for tc in tool_calls:
                    fn = dict(tc.get("function") or {})
                    tc_id = str(tc.get("id") or f"call_{uuid.uuid4().hex[:8]}")
                    t_name = str(fn.get("name") or "")
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args_dict = {}
                    call_item = create_function_call_item(
                        id=f"fc_{tc_id}",
                        call_id=tc_id,
                        name=t_name,
                        arguments=json.dumps(args_dict),
                    )
                    yield ResponsesAgentStreamEvent.model_validate(
                        {"type": "response.output_item.done", "item": call_item}
                    )
                    with mlflow.start_span(name=f"mcp.{t_name}", span_type="TOOL") as t_span:
                        t_span.set_inputs(args_dict)
                        try:
                            tool_res = await mcp_cli.call_tool(
                                t_name, args_dict, raise_on_error=False
                            )
                            out_txt = "\n".join(
                                str(getattr(c, "text", c)) for c in (tool_res.content or [])
                            )
                        except Exception as exc:
                            out_txt = json.dumps({"error": str(exc)})
                        t_span.set_outputs({"output": out_txt[:2000]})

                    out_item = create_function_call_output_item(call_id=tc_id, output=out_txt)
                    yield ResponsesAgentStreamEvent.model_validate(
                        {"type": "response.output_item.done", "item": out_item}
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "name": t_name, "content": out_txt}
                    )
            else:
                final_text = "Reached maximum tool-call rounds without a final assistant answer."

            item_id = f"msg_{uuid.uuid4().hex[:10]}"
            for idx in range(0, max(1, len(final_text)), 64):
                chunk = final_text[idx : idx + 64]
                if chunk:
                    yield ResponsesAgentStreamEvent(
                        **create_text_delta(delta=chunk, item_id=item_id)
                    )
            text_item = create_text_output_item(id=item_id, text=final_text)
            yield ResponsesAgentStreamEvent.model_validate(
                {"type": "response.output_item.done", "item": text_item}
            )
    finally:
        if created_http is not None:
            await created_http.aclose()


def create_agent_server_app(
    settings: MCPStackSettings,
    *,
    http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    mcp_client_factory: Callable[[str], Client] | None = None,
) -> FastAPI:
    """Create the MLflow AgentServer FastAPI app backed by @invoke and @stream handlers."""

    @stream()
    async def handle_stream(
        request: ResponsesAgentRequest,
    ) -> AsyncIterator[ResponsesAgentStreamEvent]:
        async for ev in stream_workshop_agent(
            request,
            settings=settings,
            http_client_factory=http_client_factory,
            mcp_client_factory=mcp_client_factory,
        ):
            yield ev

    @invoke()
    async def handle_invoke(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        outputs: list[Any] = []
        telemetry: dict[str, Any] = {}
        async for ev in stream_workshop_agent(
            request,
            settings=settings,
            http_client_factory=http_client_factory,
            mcp_client_factory=mcp_client_factory,
            telemetry=telemetry,
        ):
            if ev.type == "response.output_item.done":
                item = ev.model_dump().get("item")
                if item is not None:
                    outputs.append(item)
        trace_id = mlflow.get_last_active_trace_id()
        custom_out = {k: v for k, v in telemetry.items() if v is not None}
        if trace_id:
            custom_out["traceId"] = trace_id
        return ResponsesAgentResponse(
            output=outputs,
            custom_outputs=custom_out or None,
        )

    server = AgentServer("ResponsesAgent")
    return server.app
