import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, ChevronDown, ChevronRight, Play, RotateCcw, Square, Wrench } from "lucide-react";
import { api } from "../lib/api";
import type {
  AgentStatusResponse,
  ProfileInventoryItem,
  RegistryPromptItem,
} from "../types";
import { StatusBadge } from "./StatusDot";

interface ToolTraceCard {
  id: string;
  name: string;
  arguments: string;
  output?: string;
}

interface AgentTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools?: ToolTraceCard[];
  traceId?: string | null;
  error?: string | null;
}

function parseSseBlock(raw: string): Array<Record<string, unknown>> {
  const events: Array<Record<string, unknown>> = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      const parsed = JSON.parse(payload);
      if (parsed && typeof parsed === "object") {
        events.push(parsed as Record<string, unknown>);
      }
    } catch {
      // Ignore partial or non-JSON SSE control frames.
    }
  }
  return events;
}

export function AgentChatPanel({
  profiles,
  prompts,
  onInspectTrace,
}: {
  profiles: ProfileInventoryItem[];
  prompts: RegistryPromptItem[];
  onInspectTrace: (traceId: string) => void;
}) {
  const [status, setStatus] = useState<AgentStatusResponse | null>(null);
  const [profile, setProfile] = useState<string>("core");
  const [model, setModel] = useState<string>("");
  const [promptUri, setPromptUri] = useState<string>("");
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [localSkills, setLocalSkills] = useState<string[]>([]);
  const [inputText, setInputText] = useState<string>("");
  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    api
      .agentStatus()
      .then((res) => {
        if (!active) return;
        setStatus(res);
        setProfile((prev) => prev || res.defaultProfile || "core");
        setModel((prev) => prev || res.defaultModel || "gpt-4o-mini");
      })
      .catch(() => {});

    api
      .skills()
      .then((res) => {
        if (!active) return;
        setLocalSkills((res.skills || []).map((s) => s.name));
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, []);

  const profileNames = useMemo(
    () => (profiles.length > 0 ? profiles.map((p) => p.name) : ["core", "discover", "full"]),
    [profiles],
  );

  const toggleSkill = (name: string) => {
    setSelectedSkills((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name],
    );
  };

  const stopStream = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  };

  const sendMessage = async () => {
    const prompt = inputText.trim();
    if (!prompt || streaming) return;

    const userTurn: AgentTurn = {
      id: `user-${Date.now()}`,
      role: "user",
      content: prompt,
    };
    const assistantId = `assistant-${Date.now()}`;
    const assistantTurn: AgentTurn = {
      id: assistantId,
      role: "assistant",
      content: "",
      tools: [],
      traceId: null,
    };

    const historyMessages = [
      ...turns.map((t) => ({ role: t.role, content: t.content })),
      { role: "user", content: prompt },
    ];

    setInputText("");
    setTurns((prev) => [...prev, userTurn, assistantTurn]);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await fetch("/api/v1/agent/invocations", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          input: historyMessages,
          stream: true,
          custom_inputs: {
            profile,
            ...(model.trim() ? { model: model.trim() } : {}),
            ...(promptUri ? { prompt_uri: promptUri } : {}),
            ...(selectedSkills.length > 0 ? { skills: selectedSkills } : {}),
          },
        }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }

      const contentType = resp.headers.get("content-type") || "";
      if (!contentType.includes("text/event-stream") || !resp.body) {
        const data = (await resp.json()) as Record<string, unknown>;
        const outputArr = Array.isArray(data.output) ? data.output : [];
        const textPieces: string[] = [];
        for (const item of outputArr) {
          if (item && typeof item === "object" && "content" in item && Array.isArray(item.content)) {
            for (const c of item.content) {
              if (c && typeof c === "object" && "text" in c && typeof c.text === "string") {
                textPieces.push(c.text);
              }
            }
          }
        }
        const traceId =
          typeof (data.custom_outputs as Record<string, unknown> | undefined)?.traceId === "string"
            ? String((data.custom_outputs as Record<string, unknown>).traceId)
            : null;
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId
              ? { ...t, content: textPieces.join("\n") || JSON.stringify(data), traceId }
              : t,
          ),
        );
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const applyEvents = (events: Array<Record<string, unknown>>) => {
        setTurns((prev) =>
          prev.map((t) => {
            if (t.id !== assistantId) return t;
            let content = t.content;
            const tools = [...(t.tools || [])];
            let traceId = t.traceId || null;

            for (const ev of events) {
              const evType = String(ev.type || "");
              const customOut = ev.custom_outputs as Record<string, unknown> | undefined;
              if (customOut && typeof customOut.traceId === "string") {
                traceId = customOut.traceId;
              }
              if (evType === "response.output_text.delta" && typeof ev.delta === "string") {
                content += ev.delta;
              } else if (evType === "response.output_item.done" && ev.item && typeof ev.item === "object") {
                const item = ev.item as Record<string, unknown>;
                const itemType = String(item.type || "");
                if (itemType === "function_call") {
                  tools.push({
                    id: String(item.call_id || item.id || tools.length),
                    name: String(item.name || "tool"),
                    arguments: String(item.arguments || "{}"),
                  });
                } else if (itemType === "function_call_output") {
                  const callId = String(item.call_id || "");
                  const match = tools.find((card) => card.id === callId);
                  if (match) {
                    match.output = String(item.output || "");
                  } else {
                    tools.push({
                      id: callId || `out-${tools.length}`,
                      name: "tool_output",
                      arguments: "{}",
                      output: String(item.output || ""),
                    });
                  }
                } else if (itemType === "message" && !content && Array.isArray(item.content)) {
                  const joined = item.content
                    .map((c) =>
                      c && typeof c === "object" && "text" in c ? String((c as Record<string, unknown>).text || "") : "",
                    )
                    .join("");
                  if (joined) content = joined;
                }
              }
            }
            return { ...t, content, tools, traceId };
          }),
        );
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          applyEvents(parseSseBlock(part));
        }
      }
      if (buffer.trim()) {
        applyEvents(parseSseBlock(buffer));
      }
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId
              ? { ...t, error: err instanceof Error ? err.message : String(err) }
              : t,
          ),
        );
      }
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-[var(--accent)]" />
            <div>
              <h2 className="text-[14px] font-semibold m-0">MLflow ResponsesAgent Server</h2>
              <p className="text-[11.5px] text-[var(--text-muted)] m-0">
                {status?.agentUrl || "http://127.0.0.1:8092"} · LLM {status?.llmBaseUrl || "configured"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge
              label={status?.reachable ? "Agent online" : "Agent offline"}
              tone={status?.reachable ? "ok" : "warn"}
            />
            <button
              type="button"
              onClick={() => setTurns([])}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[12px] cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Clear
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
          <label className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
            <span>MCP Profile</span>
            <select
              aria-label="Agent MCP Profile"
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] font-mono text-[var(--text-primary)]"
            >
              {profileNames.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
            <span>Model</span>
            <input
              type="text"
              aria-label="Agent Model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-4o-mini"
              className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] font-mono text-[var(--text-primary)]"
            />
          </label>

          <label className="text-[11.5px] text-[var(--text-secondary)] space-y-1">
            <span>System Prompt (MLflow Registry)</span>
            <select
              aria-label="Agent Prompt URI"
              value={promptUri}
              onChange={(e) => setPromptUri(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-2.5 py-1.5 text-[12.5px] font-mono text-[var(--text-primary)]"
            >
              <option value="">Default gateway prompt</option>
              {prompts.map((p) => (
                <option key={p.name} value={`prompts:/${p.name}@production`}>
                  prompts:/{p.name}@production
                </option>
              ))}
            </select>
          </label>
        </div>

        {localSkills.length > 0 && (
          <div className="space-y-1">
            <div className="text-[11px] text-[var(--text-muted)]">Attach Skills</div>
            <div className="flex flex-wrap gap-1.5">
              {localSkills.slice(0, 12).map((sk) => {
                const active = selectedSkills.includes(sk);
                return (
                  <button
                    key={sk}
                    type="button"
                    onClick={() => toggleSkill(sk)}
                    className={`px-2 py-0.5 rounded-md text-[11px] font-mono border cursor-pointer ${
                      active
                        ? "bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--accent)]"
                        : "bg-[var(--bg-subtle)] border-[var(--border-hairline)] text-[var(--text-secondary)]"
                    }`}
                  >
                    {sk}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {status && !status.reachable && status.detail && (
          <div className="rounded-lg border border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--warn-soft)] px-3 py-2 text-[12px] text-[var(--warn)]">
            {status.detail}. Start it with <code className="font-mono">mcp-stack serve agent</code>.
          </div>
        )}
      </div>

      {/* Transcript */}
      <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] p-4 space-y-3 min-h-[260px]">
        {turns.length === 0 ? (
          <div className="py-10 text-center text-[12.5px] text-[var(--text-muted)]">
            Send a prompt to stream MCP tool calls and answers through{" "}
            <code className="font-mono">/api/v1/agent/invocations</code>.
          </div>
        ) : (
          turns.map((turn) => (
            <div
              key={turn.id}
              data-testid={`agent-turn-${turn.role}`}
              className={`rounded-lg p-3 text-[13px] space-y-2 ${
                turn.role === "user"
                  ? "bg-[var(--accent-soft)] border border-[color-mix(in_srgb,var(--accent)_30%,transparent)] ml-8"
                  : "bg-[var(--bg-elevated)] border border-[var(--border-hairline)] mr-8"
              }`}
            >
              <div className="flex items-center justify-between gap-2 text-[11px] font-mono text-[var(--text-muted)]">
                <span>{turn.role === "user" ? "User" : "ResponsesAgent"}</span>
                {turn.traceId && (
                  <button
                    type="button"
                    onClick={() => onInspectTrace(turn.traceId!)}
                    className="text-[var(--accent)] hover:underline cursor-pointer"
                  >
                    Trace {turn.traceId.slice(0, 12)}
                  </button>
                )}
              </div>

              {turn.tools && turn.tools.length > 0 && (
                <div className="space-y-1.5">
                  {turn.tools.map((toolCard) => {
                    const key = `${turn.id}:${toolCard.id}`;
                    const open = Boolean(expandedTools[key]);
                    return (
                      <div
                        key={key}
                        className="rounded-md border border-[var(--border-hairline)] bg-[var(--code-bg)] text-[11.5px]"
                      >
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedTools((prev) => ({ ...prev, [key]: !prev[key] }))
                          }
                          className="w-full px-2.5 py-1.5 flex items-center justify-between gap-2 font-mono text-left cursor-pointer"
                        >
                          <span className="inline-flex items-center gap-1.5 text-[var(--text-primary)]">
                            {open ? (
                              <ChevronDown className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5" />
                            )}
                            <Wrench className="w-3 h-3 text-[var(--accent)]" />
                            {toolCard.name}
                          </span>
                          <StatusBadge
                            label={toolCard.output !== undefined ? "done" : "running"}
                            tone={toolCard.output !== undefined ? "ok" : "warn"}
                          />
                        </button>
                        {open && (
                          <div className="px-2.5 pb-2 pt-1 border-t border-[var(--border-hairline)] space-y-1.5">
                            <pre className="m-0 overflow-x-auto text-[11px] font-mono text-[var(--text-secondary)] whitespace-pre-wrap">
                              args: {toolCard.arguments}
                            </pre>
                            {toolCard.output !== undefined && (
                              <pre className="m-0 overflow-x-auto text-[11px] font-mono text-[var(--text-primary)] whitespace-pre-wrap max-h-48">
                                {toolCard.output}
                              </pre>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {turn.error ? (
                <div className="rounded-md bg-[var(--err-soft)] px-2.5 py-2 text-[12px] text-[var(--err)]">
                  {turn.error}
                </div>
              ) : (
                <div className="whitespace-pre-wrap leading-relaxed">
                  {turn.content || (streaming && turn.role === "assistant" ? "Streaming..." : "")}
                </div>
              )}
            </div>
          ))
        )}

        <div className="flex items-end gap-2 pt-2 border-t border-[var(--border-hairline)]">
          <textarea
            rows={2}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Ask the agent using the selected MCP profile..."
            className="flex-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--code-bg)] px-3 py-2 text-[13px] resize-y"
          />
          {streaming ? (
            <button
              type="button"
              onClick={stopStream}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-[var(--err)] text-white text-[12.5px] font-semibold cursor-pointer"
            >
              <Square className="w-3.5 h-3.5" />
              Stop
            </button>
          ) : (
            <button
              type="button"
              onClick={sendMessage}
              disabled={!inputText.trim()}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-[var(--accent)] hover:brightness-110 disabled:opacity-50 text-white text-[12.5px] font-semibold cursor-pointer"
            >
              <Play className="w-3.5 h-3.5" />
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
