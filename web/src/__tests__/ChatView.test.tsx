import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { unwrapOmnigentResult } from "../lib/omnigentChat";
import type { CallToolResponse } from "../types";
import { ChatView } from "../views/ChatView";

function okTool(tool: string, result: unknown, traceId = "tr-omni-1"): CallToolResponse {
  return {
    ok: true,
    policyRefusal: false,
    server: "omnigent",
    tool,
    durationMs: 18,
    traceId,
    result,
  };
}

describe("ChatView (Omnigent Control Plane Chat)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockDefaultWorkspace(overrides?: { mutationsEnabled?: boolean; sessionStatus?: string }) {
    const mutationsEnabled = overrides?.mutationsEnabled ?? true;
    const sessionStatus = overrides?.sessionStatus ?? "idle";

    return vi.spyOn(api, "callTool").mockImplementation(async (_server, tool, args) => {
      if (tool === "omnigent_get_status") {
        return okTool(tool, {
          ok: true,
          serverVersion: "0.23.0",
          onlineHosts: [{ id: "host_1", name: "macstudio.local", status: "online" }],
          unreadInboxCount: 1,
          automationsTotal: 10,
          automationsActive: 9,
          automationsPaused: 1,
          mutationsEnabled,
        });
      }
      if (tool === "omnigent_list_projects") {
        return okTool(tool, [
          { id: "proj_printer", name: "printer", baseBranch: "main" },
          { id: "proj_atelier", name: "atelier", baseBranch: "main" },
        ]);
      }
      if (tool === "omnigent_list_workflows") {
        return okTool(tool, [
          {
            id: "wf_1",
            name: "polly-implement-and-cross-review",
            description: "Plan and implement in worktree",
          },
        ]);
      }
      if (tool === "omnigent_list_sessions") {
        return okTool(tool, [
          {
            id: "sess_1",
            title: "Existing Printer Session",
            status: sessionStatus,
            agentName: "polly",
            projectId: "proj_printer",
            pendingApprovals: 1,
            sessionUrl: "https://mac-studio.angora-arctic.ts.net:8446/c/sess_1",
          },
        ]);
      }
      if (tool === "omnigent_list_inbox") {
        return okTool(tool, {
          unreadCount: 1,
          items: [
            {
              id: "inbox_1",
              status: "unread",
              title: "Printer health digest",
              sourceSessionId: "sess_1",
            },
          ],
          pendingApprovalSessions: [],
        });
      }
      if (tool === "omnigent_start_session") {
        return okTool(
          tool,
          {
            id: "sess_new",
            title: "Started Chat",
            status: "idle",
            projectId: args.project || null,
            sessionUrl: "https://mac-studio.angora-arctic.ts.net:8446/c/sess_new",
          },
          "tr-start-1",
        );
      }
      if (tool === "omnigent_run_workflow") {
        return okTool(
          tool,
          {
            id: "sess_wf",
            workflowId: "wf_1",
            workflowName: "polly-implement-and-cross-review",
            status: "idle",
            sessionUrl: "https://mac-studio.angora-arctic.ts.net:8446/c/sess_wf",
          },
          "tr-wf-1",
        );
      }
      if (tool === "omnigent_get_session") {
        const sid = String(args.session_id || "sess_1");
        if (sid === "sess_new") {
          return okTool(
            tool,
            {
              id: "sess_new",
              title: "Started Chat",
              status: "idle",
              agentName: "polly",
              llmModel: "claude-opus-5",
              pendingElicitations: [],
              sessionUrl: "https://mac-studio.angora-arctic.ts.net:8446/c/sess_new",
              recentMessages: [{ id: "m1", role: "assistant", text: "Printer status is OK." }],
            },
            "tr-get-new",
          );
        }
        return okTool(tool, {
          id: sid,
          title: "Existing Printer Session",
          status: sessionStatus,
          agentName: "polly",
          llmModel: "claude-opus-5",
          gitBranch: "fix/ci",
          pendingElicitations: [
            { elicitation_id: "el_1", message: "Approve physical receipt print?" },
          ],
          sessionUrl: `https://mac-studio.angora-arctic.ts.net:8446/c/${sid}`,
          recentMessages: [
            { id: "m0", role: "user", text: "Check printer" },
            { id: "m1", role: "assistant", text: "Waiting on approval." },
          ],
        });
      }
      if (tool === "omnigent_send_message") {
        return okTool(tool, { sessionId: args.session_id, accepted: true });
      }
      if (tool === "omnigent_resolve_approval") {
        return okTool(tool, { sessionId: args.session_id, elicitationId: args.elicitation_id, resolved: true });
      }
      if (tool === "omnigent_mark_inbox_item") {
        return okTool(tool, { itemId: args.item_id, status: "read", unreadCount: 0 });
      }
      return okTool(tool, {});
    });
  }

  it("loads hub state, projects, sessions, and unread inbox on mount", async () => {
    const spy = mockDefaultWorkspace();
    render(
      <ChatView
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/v0\.23\.0 · macstudio\.local/i)).toBeInTheDocument();
    });
    expect(screen.getByText("Existing Printer Session")).toBeInTheDocument();
    expect(screen.getByText("Printer health digest")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_get_status", {});
  });

  it("starts a new session, renders transcript + Tailscale link, and inspects trace", async () => {
    const spy = mockDefaultWorkspace();
    const onSelectSessionId = vi.fn();
    const onInspectTrace = vi.fn();

    render(
      <ChatView
        initialSessionId={null}
        onSelectSessionId={onSelectSessionId}
        onInspectTrace={onInspectTrace}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Project")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "proj_printer" } });
    fireEvent.change(screen.getByLabelText("Task prompt"), {
      target: { value: "Check printer & MLflow health" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start session/i }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_start_session", {
        prompt: "Check printer & MLflow health",
        project: "proj_printer",
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Printer status is OK.")).toBeInTheDocument();
    });
    expect(onSelectSessionId).toHaveBeenCalledWith("sess_new");
    const link = screen.getByRole("link", { name: /Open in Omnigent/i }) as HTMLAnchorElement;
    expect(link.href).toBe("https://mac-studio.angora-arctic.ts.net:8446/c/sess_new");

    fireEvent.click(screen.getByRole("button", { name: /Inspect trace/i }));
    expect(onInspectTrace).toHaveBeenCalled();
  });

  it("runs a saved workflow when selected in the new session composer", async () => {
    const spy = mockDefaultWorkspace();
    render(
      <ChatView
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Saved Workflow")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Saved Workflow"), {
      target: { value: "polly-implement-and-cross-review" },
    });
    fireEvent.change(screen.getByLabelText("Task prompt"), {
      target: { value: "Fix issue #12" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Run workflow/i }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_run_workflow", {
        workflow: "polly-implement-and-cross-review",
        details: "Fix issue #12",
      });
    });
  });

  it("handles follow-up messages, approval resolution, and marking inbox read", async () => {
    const spy = mockDefaultWorkspace();
    render(
      <ChatView
        initialSessionId="sess_1"
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Approve physical receipt print?")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Follow-up message"), {
      target: { value: "Proceed carefully" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Send$/i }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_send_message", {
        session_id: "sess_1",
        message: "Proceed carefully",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_resolve_approval", {
        session_id: "sess_1",
        elicitation_id: "el_1",
        action: "accept",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: /Mark read/i }));
    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_mark_inbox_item", {
        item_id: "inbox_1",
        status: "read",
      });
    });
  });

  it("locks mutation actions when read-only and displays error banners when gateway calls fail", async () => {
    mockDefaultWorkspace({ mutationsEnabled: false });
    const { rerender } = render(
      <ChatView
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/OMNIGENT_ALLOW_MUTATIONS=false/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Start session/i })).toBeDisabled();

    vi.restoreAllMocks();
    vi.spyOn(api, "callTool").mockResolvedValue({
      ok: false,
      policyRefusal: false,
      server: "omnigent",
      tool: "omnigent_get_status",
      durationMs: 2,
      error: { code: "SERVER_NOT_FOUND", message: "Unknown 'omnigent'" },
    });

    rerender(
      <ChatView
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Refresh Omnigent Chat/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("launchctl kickstart");
    });
  });

  it("unwraps FastMCP structuredContent.result list envelopes without S.map crash", async () => {
    const unwrappedList = unwrapOmnigentResult<Array<{ id: string }>>({
      ok: true,
      policyRefusal: false,
      server: "omnigent",
      tool: "omnigent_list_projects",
      durationMs: 4,
      structuredContent: { result: [{ id: "p1" }] },
      result: [{ id: "p1" }],
    });
    expect(unwrappedList.data).toEqual([{ id: "p1" }]);

    const unwrappedInbox = unwrapOmnigentResult<{ unreadCount: number; items: unknown[] }>({
      ok: true,
      policyRefusal: false,
      server: "omnigent",
      tool: "omnigent_list_inbox",
      durationMs: 4,
      truncated: true,
      structuredContent: { unreadCount: 2, items: [{ id: "i1" }] },
      result: "{\"unreadCount\": 2, \"items\": [truncated",
    });
    expect(unwrappedInbox.data.unreadCount).toBe(2);
    expect(unwrappedInbox.data.items).toHaveLength(1);

    vi.spyOn(api, "callTool").mockImplementation(async (_server, tool) => {
      const wrap = (payload: unknown): CallToolResponse => ({
        ok: true,
        policyRefusal: false,
        server: "omnigent",
        tool,
        durationMs: 5,
        traceId: "tr-wrap-1",
        structuredContent: Array.isArray(payload)
          ? { result: payload }
          : (payload as Record<string, unknown>),
        result: payload,
      });
      if (tool === "omnigent_get_status") {
        return wrap({
          ok: true,
          serverVersion: "0.23.0",
          onlineHosts: [{ id: "h1", name: "macstudio.local", status: "online" }],
          mutationsEnabled: true,
        });
      }
      if (tool === "omnigent_list_projects") {
        return wrap([{ id: "proj_p1", name: "atelier" }]);
      }
      if (tool === "omnigent_list_workflows") {
        return wrap([{ id: "wf_w1", name: "nightly-audit" }]);
      }
      if (tool === "omnigent_list_sessions") {
        return wrap([{ id: "sess_w1", title: "Wrapped Session", status: "idle" }]);
      }
      if (tool === "omnigent_list_inbox") {
        return wrap({ unreadCount: 0, items: [] });
      }
      return wrap({});
    });

    render(
      <ChatView
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Wrapped Session")).toBeInTheDocument();
    });
    expect(screen.getAllByText("atelier").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("nightly-audit")).toBeInTheDocument();
  });

  it("defers Omnigent MCP calls while unauthenticated and loads automatically once signed in", async () => {
    const spy = mockDefaultWorkspace();
    const { rerender } = render(
      <ChatView
        authenticated={false}
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    expect(spy).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(
      <ChatView
        authenticated={true}
        initialSessionId={null}
        onSelectSessionId={vi.fn()}
        onInspectTrace={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/v0\.23\.0 · macstudio\.local/i)).toBeInTheDocument();
    });
    expect(screen.getByText("Existing Printer Session")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith("omnigent", "omnigent_get_status", {});
  });
});
