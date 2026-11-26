import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OverviewView } from "../views/OverviewView";
import { PromptRenderer } from "../components/PromptRenderer";
import { SchemaForm } from "../components/SchemaForm";
import { SmartOutput } from "../components/SmartOutput";
import { normalizeMultilineText, tokenizePromptTemplate } from "../lib/format";
import type { ToolItem } from "../types";

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
});
