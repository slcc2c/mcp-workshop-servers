import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette } from "../components/CommandPalette";
import { PromptRenderer } from "../components/PromptRenderer";
import { PromptWorkbench } from "../components/PromptWorkbench";
import { SchemaForm } from "../components/SchemaForm";
import { SmartOutput } from "../components/SmartOutput";
import { computeLineDiff, buildSideBySideRows } from "../lib/diff";
import { normalizeMultilineText, tokenizePromptTemplate } from "../lib/format";
import { buildWorkbenchUrl, parseWorkbenchUrl } from "../lib/urlState";
import { resolveMlflowUiUrl } from "../lib/urls";
import { buildSpanWaterfall } from "../lib/waterfall";
import type { ToolItem } from "../types";
import { OverviewView } from "../views/OverviewView";
import { TracesView } from "../views/TracesView";

describe("Control Plane Workbench renderers", () => {
  it("preserves hard returns in Formatted SmartOutput and renders MCP images inline", () => {
    const resp = {
      ok: true,
      policyRefusal: false,
      server: "printer",
      tool: "today",
      durationMs: 412,
      contentBlocks: [
        { type: "text" as const, text: "Wednesday 25 November\nToday printed at 8:30 am.\nLine 3" },
        { type: "image" as const, mimeType: "image/png", data: "iVBORw0KGgo=" },
      ],
    };

    render(<SmartOutput response={resp} />);
    const formatted = screen.getByTestId("smart-output-formatted");
    expect(formatted.textContent).toContain("Wednesday 25 November");
    expect(formatted.textContent).toContain("Today printed at 8:30 am.");
    const textBox = screen.getByText(/Wednesday 25 November/);
    expect(textBox.className).toContain("whitespace-pre-wrap");

    const img = screen.getByAltText("MCP tool image output") as HTMLImageElement;
    expect(img.src).toContain("data:image/png;base64,iVBORw0KGgo=");

    fireEvent.click(screen.getByRole("button", { name: /Raw JSON/i }));
    expect(screen.getByTestId("smart-output-raw").textContent).toContain('"server": "printer"');
  });

  it("highlights {{variables}} and preserves newlines in PromptRenderer", () => {
    const tokens = tokenizePromptTemplate("Hello {{user}}\nLine {{count}}");
    expect(tokens.filter((t) => t.type === "variable").map((t) => t.value)).toEqual([
      "{{user}}",
      "{{count}}",
    ]);

    render(<PromptRenderer template={"Line 1 {{alpha}}\n\nLine 2 {{beta}}"} title="ai-assist" version={2} />);
    const body = screen.getByTestId("prompt-rendered-body");
    expect(body.className).toContain("whitespace-pre-wrap");
    expect(screen.getByText("{{alpha}}")).toBeInTheDocument();
    expect(screen.getByText("{{beta}}")).toBeInTheDocument();
  });

  it("generates schema form controls from JSON Schema and triggers run", () => {
    const tool: ToolItem = {
      name: "search",
      server: "music-brain",
      description: "Search notes",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query" },
          limit: { type: "integer", default: 10 },
          include_notes: { type: "boolean", default: false },
        },
        required: ["query"],
      },
    };
    const onChangeArgs = vi.fn();
    const onChangeRaw = vi.fn();
    const onRun = vi.fn();

    render(
      <SchemaForm
        tool={tool}
        argsObj={{ limit: 10, include_notes: false }}
        rawJson='{"limit": 10}'
        onChangeArgs={onChangeArgs}
        onChangeRawJson={onChangeRaw}
        onRun={onRun}
        running={false}
      />,
    );

    const queryInput = screen.getByLabelText("query");
    fireEvent.change(queryInput, { target: { value: "overbridge" } });
    expect(onChangeArgs).toHaveBeenCalledWith({ limit: 10, include_notes: false, query: "overbridge" });

    fireEvent.click(screen.getByRole("button", { name: /Run Tool/i }));
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(normalizeMultilineText("a\r\nb")).toBe("a\nb");
  });

  it("renders OverviewView safely with snake_case backend evalHistory payloads", () => {
    render(
      <OverviewView
        auth={{
          authenticated: true,
          authEnabled: true,
          clientId: "codex",
          clientName: "Codex CLI",
          allowedServers: ["*"],
          mlflowMutationsEnabled: false,
        }}
        health={{
          status: "healthy",
          version: "2.3.0",
          timestamp: "2026-11-26T00:00:00Z",
          composedRoute: "/mcp",
          defaultProfile: "core",
          servers: [
            {
              key: "printer",
              slug: "printer",
              route: "/servers/printer/mcp",
              status: "proxy",
              connectionStatus: "connected",
              external: true,
              toolCount: 20,
            },
          ],
          profiles: [{ name: "discover", route: "/profiles/discover/mcp", servers: ["gateway"] }],
        }}
        ready={{ status: "ready", timestamp: "2026-11-26T00:00:00Z", checks: {} }}
        watchdog={{
          components: { gateway: { healthy: true } },
          evalRegression: { status: "ok", min_score: 1.0, run_id: "r-1" },
        }}
        evalHistory={[
          { run_id: "abcdef123456", run_name: "placid-robin", min_score: 1.0, metrics: {} },
        ]}
        profileCounts={{ discover: 11 }}
        onOpenPlaygroundServer={vi.fn()}
        onProbeUpstream={vi.fn(async () => {})}
        onNavigateTraces={vi.fn()}
        onAfterAction={vi.fn(async () => {})}
      />,
    );

    expect(screen.getByText("v2.3.0")).toBeInTheDocument();
    expect(screen.getByText("1.00")).toBeInTheDocument();
    expect(screen.getByText("printer")).toBeInTheDocument();
  });

  it("computes line diffs and side-by-side alignment cleanly", () => {
    const diff = computeLineDiff("Line 1\nOld line\nLine 3", "Line 1\nNew line\nLine 3\nAdded");
    expect(diff.added).toBe(2);
    expect(diff.removed).toBe(1);
    expect(diff.unchanged).toBe(2);
    const sideRows = buildSideBySideRows(diff.lines);
    expect(sideRows.some((r) => r.left?.text === "Old line" && r.right?.text === "New line")).toBe(
      true,
    );
  });

  it("builds nested parent-child span waterfalls and handles missing timestamps", () => {
    const { rows, totalMs } = buildSpanWaterfall([
      {
        spanId: "root",
        parentId: null,
        name: "printer.today",
        status: "OK",
        startTimeMs: 1000,
        endTimeMs: 1100,
        durationMs: 100,
      },
      {
        spanId: "child",
        parentId: "root",
        name: "http.post",
        status: "OK",
        startTimeMs: 1020,
        endTimeMs: 1080,
        durationMs: 60,
      },
    ]);
    expect(totalMs).toBe(100);
    expect(rows.map((r) => [r.span.spanId, r.depth])).toEqual([
      ["root", 0],
      ["child", 1],
    ]);
    expect(rows[1].offsetPct).toBeCloseTo(20, 1);
    expect(rows[1].widthPct).toBeCloseTo(60, 1);

    const fallback = buildSpanWaterfall([
      { spanId: "s1", parentId: null, name: "tool", durationMs: 42 },
    ]);
    expect(fallback.rows[0].widthPct).toBe(100);
  });

  it("parses and builds deep-link URLs and maps remote MLflow UI hosts", () => {
    const parsed = parseWorkbenchUrl({
      pathname: "/ui/traces",
      search: "?trace=tr-abc123",
      hash: "",
    });
    expect(parsed).toEqual({
      tab: "traces",
      tool: null,
      server: null,
      profile: null,
      trace: "tr-abc123",
      prompt: null,
      version: null,
    });
    expect(
      buildWorkbenchUrl({ tab: "registry", prompt: "ai-assist", version: "2" }),
    ).toBe("/ui/registry?prompt=ai-assist&version=2");

    expect(
      resolveMlflowUiUrl("http://localhost:5002", {
        protocol: "https:",
        hostname: "mcp.slcc2c.com",
      }),
    ).toBe("https://mlflow.slcc2c.com");
  });

  it("builds MLflow experiment, run, and trace deep-link URLs cleanly", async () => {
    const { buildMlflowExperimentUrl } = await import("../lib/urls");
    expect(buildMlflowExperimentUrl("http://localhost:5002", null)).toBe("http://localhost:5002");
    expect(buildMlflowExperimentUrl("http://localhost:5002", "52")).toBe(
      "http://localhost:5002/#/experiments/52",
    );
    expect(buildMlflowExperimentUrl("http://localhost:5002", "52", { section: "traces" })).toBe(
      "http://localhost:5002/#/experiments/52/traces",
    );
    expect(
      buildMlflowExperimentUrl("http://localhost:5002", "52", {
        section: "runs",
        runId: "abc-123",
      }),
    ).toBe("http://localhost:5002/#/experiments/52/runs/abc-123");
  });

  it("supports keyboard ArrowDown + Enter on saved Presets in CommandPalette", () => {
    const onSelectPreset = vi.fn();
    const onClose = vi.fn();
    render(
      <CommandPalette
        open
        onClose={onClose}
        presets={[
          {
            id: "p-1",
            name: "First Preset",
            server: "printer",
            tool: "today",
            arguments: { date: "2026-11-25" },
            description: "Print today",
            pinned: true,
            createdAt: "2026-11-25T00:00:00Z",
            updatedAt: "2026-11-25T00:00:00Z",
          },
          {
            id: "p-2",
            name: "Second Preset",
            server: "photos",
            tool: "photos_list_albums",
            arguments: {},
            description: "",
            pinned: false,
            createdAt: "2026-11-25T00:00:00Z",
            updatedAt: "2026-11-25T00:00:00Z",
          },
        ]}
        servers={[]}
        tools={[]}
        prompts={[]}
        onSelectTab={vi.fn()}
        onSelectPreset={onSelectPreset}
        onSelectTool={vi.fn()}
        onSelectPrompt={vi.fn()}
      />,
    );

    const input = screen.getByPlaceholderText(/Jump to preset/i);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelectPreset).toHaveBeenCalledWith(
      expect.objectContaining({ id: "p-2", server: "photos", tool: "photos_list_albums" }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("renders PromptWorkbench versions, live {{var}} preview, and version diff", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("version_or_alias=1")) {
        return new Response(
          JSON.stringify({
            name: "ai-assist",
            version: 1,
            template: "Hello {{user}}\nOld instructions.",
            commitMessage: "initial",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          name: "ai-assist",
          version: 2,
          template: "Hello {{user}}\nUpdated {{style}} instructions.",
          commitMessage: "add style",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      render(
        <PromptWorkbench
          promptSummary={{
            name: "ai-assist",
            versions: [
              { version: 2, aliases: ["production"], commitMessage: "add style" },
              { version: 1, aliases: [], commitMessage: "initial" },
            ],
          }}
          selectedVersion="2"
          onSelectVersion={vi.fn()}
          mutationsEnabled
          mlflowUiBase="http://localhost:5002"
          onStartNewVersion={vi.fn()}
          onMutated={vi.fn(async () => {})}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId("prompt-rendered-body").textContent).toContain("Updated");
      });

      fireEvent.click(screen.getByRole("button", { name: /Live Preview/i }));
      const userInput = screen.getByPlaceholderText("Value for user...");
      fireEvent.change(userInput, { target: { value: "Spencer" } });
      expect(screen.getByTestId("prompt-live-preview-output").textContent).toContain(
        "Hello Spencer",
      );

      fireEvent.click(screen.getByRole("button", { name: /Diff/i }));
      await waitFor(() => {
        expect(screen.getByTestId("prompt-diff-view")).toBeInTheDocument();
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("renders trace assessments/tags, triggers Replay in Playground, and calls /promote-to-dataset", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/promote-to-dataset")) {
        return new Response(JSON.stringify({ promoted: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/v1/traces/tr-99")) {
        return new Response(
          JSON.stringify({
            traceId: "tr-99",
            state: "OK",
            durationMs: 45,
            server: "printer",
            tool: "today",
            tags: { "mcp.server": "printer" },
            assessments: [{ kind: "feedback", name: "human_review", value: true, rationale: "clean" }],
            spans: [
              {
                spanId: "sp-1",
                parentId: null,
                name: "printer.today",
                spanType: "TOOL",
                status: "OK",
                durationMs: 45,
                startTimeMs: 100,
                endTimeMs: 145,
                inputs: { format: "short" },
                outputs: { ok: true },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          available: true,
          experimentId: "1",
          experiments: [],
          traces: [
            {
              traceId: "tr-99",
              state: "OK",
              durationMs: 45,
              server: "printer",
              tool: "today",
            },
          ],
          evalHistory: [],
          facets: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      const onReplay = vi.fn();
      render(
        <TracesView
          initialTraceId="tr-99"
          onSelectTraceId={vi.fn()}
          onReplayInPlayground={onReplay}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId("trace-assessments")).toBeInTheDocument();
      });
      expect(screen.getByTestId("trace-tags").textContent).toContain("mcp.server=printer");
      expect(screen.getByTestId("span-waterfall")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Promote to Golden Dataset/i }));
      await waitFor(() => {
        expect(
          fetchMock.mock.calls.some(([u]) => String(u).includes("/api/v1/traces/tr-99/promote-to-dataset")),
        ).toBe(true);
      });

      fireEvent.click(screen.getByRole("button", { name: /Replay in Playground/i }));
      expect(onReplay).toHaveBeenCalledWith({
        server: "printer",
        tool: "today",
        arguments: { format: "short" },
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
