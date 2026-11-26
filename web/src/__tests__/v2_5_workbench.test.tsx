import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityDrawer } from "../components/ActivityDrawer";
import { AgentChatPanel } from "../components/AgentChatPanel";
import { Layout } from "../components/Layout";
import { ProfilesEditor } from "../components/ProfilesEditor";
import { SkillRegistryPanel } from "../components/SkillRegistryPanel";
import { buildWorkbenchUrl, parseWorkbenchUrl } from "../lib/urlState";
import { EvalsView } from "../views/EvalsView";
import { UpstreamsView } from "../views/UpstreamsView";

describe("v2.5 Control Plane Workbench", () => {
  it("renders grouped 3-section sidebar and maps legacy routes cleanly", () => {
    render(
      <Layout
        activeTab="evals"
        onSelectTab={vi.fn()}
        theme="dark"
        onToggleTheme={vi.fn()}
        version="2.5.0"
        readyStatus="ready"
        auth={{
          authenticated: true,
          authEnabled: true,
          clientId: "codex",
          clientName: "Codex CLI",
          allowedServers: ["*"],
          mlflowMutationsEnabled: true,
        }}
        autoRefreshMs={0}
        onChangeAutoRefresh={vi.fn()}
        onRefreshAll={vi.fn()}
        onOpenPalette={vi.fn()}
        onOpenShortcuts={vi.fn()}
        onOpenAuthModal={vi.fn()}
        onLogout={vi.fn()}
        activityCount={3}
        activityLive
        onOpenActivity={vi.fn()}
      >
        <div>Body</div>
      </Layout>,
    );

    expect(screen.getAllByText("Operate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MLflow GenAI").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Connect").length).toBeGreaterThan(0);
    expect(screen.getAllByText("v2.5.0").length).toBeGreaterThan(0);

    expect(parseWorkbenchUrl({ pathname: "/ui/chat", search: "", hash: "" })).toMatchObject({
      tab: "playground",
      sub: "omnigent",
    });
    expect(parseWorkbenchUrl({ pathname: "/ui/agent", search: "", hash: "" })).toMatchObject({
      tab: "playground",
      sub: "agent",
    });
    expect(parseWorkbenchUrl({ pathname: "/ui/skills", search: "", hash: "" })).toMatchObject({
      tab: "registry",
      sub: "skills",
    });
    expect(parseWorkbenchUrl({ pathname: "/ui/profiles", search: "", hash: "" })).toMatchObject({
      tab: "upstreams",
      sub: "profiles",
    });
    expect(buildWorkbenchUrl({ tab: "evals" })).toBe("/ui/evals");
  });

  it("renders ActivityDrawer events and trace click-through", () => {
    const onInspectTrace = vi.fn();
    const onClose = vi.fn();
    render(
      <ActivityDrawer
        open
        onClose={onClose}
        paused={false}
        streamState="live"
        onTogglePause={vi.fn()}
        onClear={vi.fn()}
        onInspectTrace={onInspectTrace}
        events={[
          {
            id: "ev-1",
            ts: "2026-11-26T12:00:00Z",
            kind: "tool_call",
            actor: "codex",
            server: "printer",
            tool: "today",
            status: "ok",
            durationMs: 42,
            traceId: "tr-live-123456",
            summary: "printer.today succeeded",
          },
        ]}
      />,
    );

    expect(screen.getByText("printer.today succeeded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Trace tr-live-1234/i }));
    expect(onInspectTrace).toHaveBeenCalledWith("tr-live-123456");
    expect(onClose).toHaveBeenCalled();
  });

  it("streams ResponsesAgent tool cards and text deltas in AgentChatPanel", async () => {
    const encoder = new TextEncoder();
    const ssePayload = [
      `data: ${JSON.stringify({ type: "response.output_item.done", item: { type: "function_call", call_id: "c1", name: "printer.today", arguments: "{}" } })}\n\n`,
      `data: ${JSON.stringify({ type: "response.output_item.done", item: { type: "function_call_output", call_id: "c1", output: "ok" } })}\n\n`,
      `data: ${JSON.stringify({ type: "response.output_text.delta", delta: "Printed today receipt.", custom_outputs: { traceId: "tr-agent-999" } })}\n\n`,
    ].join("");

    const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/agent/status")) {
        return new Response(
          JSON.stringify({
            reachable: true,
            agentUrl: "http://127.0.0.1:8092",
            defaultProfile: "core",
            defaultModel: "gpt-4o-mini",
            llmBaseUrl: "http://127.0.0.1:8000/v1",
            maxToolRounds: 6,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/v1/skills")) {
        return new Response(JSON.stringify({ skills: [{ name: "linear-issue" }] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/api/v1/agent/invocations")) {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(ssePayload));
            controller.close();
          },
        });
        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return new Response("{}", { status: 404 });
    });

    vi.stubGlobal("fetch", mockFetch);
    try {
      const onInspectTrace = vi.fn();
      render(
        <AgentChatPanel
          profiles={[{ name: "core", route: "/profiles/core/mcp", servers: ["gateway"] }]}
          prompts={[{ name: "ai-assist", versions: [] }]}
          onInspectTrace={onInspectTrace}
        />,
      );

      const input = screen.getByPlaceholderText(/Ask the agent/i);
      fireEvent.change(input, { target: { value: "Print today" } });
      fireEvent.click(screen.getByRole("button", { name: /^Send$/i }));

      await waitFor(() => {
        expect(screen.getByText("Printed today receipt.")).toBeInTheDocument();
      });
      expect(screen.getByText("printer.today")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Trace tr-agent-999/i }));
      expect(onInspectTrace).toHaveBeenCalledWith("tr-agent-999");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("shows graceful 3.18 unsupported banner in SkillRegistryPanel", async () => {
    const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/api/v1/mlflow/skills")) {
        return new Response(
          JSON.stringify({
            supported: false,
            serverVersion: "3.17.0",
            requiredVersion: "3.18.0",
            skills: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    });

    vi.stubGlobal("fetch", mockFetch);
    try {
      render(<SkillRegistryPanel />);
      await waitFor(() => {
        expect(screen.getByTestId("skill-registry-unsupported")).toBeInTheDocument();
      });
      expect(screen.getAllByText(/3\.17\.0/).length).toBeGreaterThan(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("renders EvalsView comparison deltas, TypeSafe p pill, and dataset records", async () => {
    const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/evals/datasets")) {
        return new Response(
          JSON.stringify({
            datasets: [{ datasetId: "d-1", name: "golden_core", recordCount: 1 }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/evals/datasets/d-1")) {
        return new Response(
          JSON.stringify({
            datasetId: "d-1",
            name: "golden_core",
            recordCount: 1,
            records: [{ datasetRecordId: "rec-1", inputs: { question: "hi" } }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/evals/runs?")) {
        return new Response(
          JSON.stringify({
            runs: [
              { run_id: "run-b", run_name: "candidate", min_score: 0.9, metrics: {} },
              { run_id: "run-a", run_name: "baseline", min_score: 0.8, metrics: {} },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/evals/runs/run-b")) {
        return new Response(
          JSON.stringify({
            runId: "run-b",
            runName: "candidate",
            minScore: 0.9,
            metrics: { "tool_execution_success/mean": 0.9 },
            params: {},
            tags: {},
            rows: [
              {
                evalId: "row-1",
                traceId: "tr-row-1",
                request: "check printer",
                response: "online",
                passed: true,
                typesafeProbability: 0.92,
                assessments: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/evals/compare")) {
        return new Response(
          JSON.stringify({
            runA: { runId: "run-a", runName: "baseline", metrics: {}, params: {}, tags: {}, rows: [] },
            runB: { runId: "run-b", runName: "candidate", metrics: {}, params: {}, tags: {}, rows: [] },
            deltas: [{ metric: "tool_execution_success/mean", baseline: 0.8, candidate: 0.9, delta: 0.1 }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    });

    vi.stubGlobal("fetch", mockFetch);
    try {
      render(
        <EvalsView
          profiles={[{ name: "core", route: "/profiles/core/mcp", servers: ["gateway"] }]}
          onInspectTrace={vi.fn()}
          onAfterRun={vi.fn(async () => {})}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText("p=0.92")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /^Compare$/i }));
      await waitFor(() => {
        expect(screen.getByTestId("eval-compare-deltas")).toBeInTheDocument();
      });
      expect(screen.getByText("+0.10")).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("renders ProfilesEditor creation and UpstreamsView curated counts & concise auth callout", async () => {
    const onChanged = vi.fn(async () => {});
    const mockFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/profiles") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            profile: { name: "research-ops", route: "/profiles/research-ops/mcp", servers: ["gateway"] },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/v1/upstreams")) {
        return new Response(
          JSON.stringify({
            configPath: "config/gateway.local.yaml",
            upstreams: [
              {
                slug: "linear",
                transport: "http",
                url: "https://mcp.linear.app/mcp",
                enabled: true,
                profiles: ["core"],
                governance: "external-proxy",
                description: "Linear",
                route: "/servers/linear/mcp",
                connectionStatus: "auth_required",
                authReasonCode: "OP_TIMEOUT",
                toolCount: 14,
                rawToolCount: 60,
                exposedToolCount: 14,
                detail: "1Password CLI timed out waiting for biometric/app unlock.",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    });

    vi.stubGlobal("fetch", mockFetch);
    try {
      const { unmount } = render(
        <ProfilesEditor
          profiles={[{ name: "core", route: "/profiles/core/mcp", servers: ["gateway"], builtin: true }]}
          servers={[{ key: "gateway", slug: "gateway", route: "/servers/gateway/mcp", status: "ready", toolCount: 9 }]}
          profileCounts={{ core: 9 }}
          onChanged={onChanged}
        />,
      );

      fireEvent.change(screen.getByLabelText("Profile name"), { target: { value: "research-ops" } });
      fireEvent.click(screen.getByRole("button", { name: /Create Profile/i }));
      await waitFor(() => {
        expect(onChanged).toHaveBeenCalled();
      });
      unmount();

      render(<UpstreamsView onAfterChange={vi.fn(async () => {})} />);
      await waitFor(() => {
        expect(screen.getByText("OP_TIMEOUT")).toBeInTheDocument();
      });
      expect(screen.getByText("14/60 tools (curated)")).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
