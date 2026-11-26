import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SkillsView } from "../views/SkillsView";

describe("SkillsView", () => {
  it("renders skill matrix, collisions, and triggers dry-run sync", async () => {
    const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/skills")) {
        return new Response(
          JSON.stringify({
            available: true,
            manifestPath: "/tmp/skills-manifest.yaml",
            summary: {
              canonicalSkills: 1,
              targets: 2,
              syncedLinks: 1,
              driftIssues: 1,
              collisions: 1,
              legacyItems: 1,
              repoDualCopies: 0,
              pluginSkills: 1,
            },
            skills: [
              {
                name: "linear-issue",
                frontmatterName: "linear-issue",
                description: "Analyze Linear issues",
                sourceId: "atelier-personal",
                sourceKind: "canonical-repo",
                owner: "personal",
                canonicalPath: "/tmp/atelier/linear-issue",
                hash: "abc123",
                atelierManaged: false,
                targets: { "claude-code": "synced", codex: "drifted_copy" },
              },
            ],
            targets: {
              "claude-code": { dir: "~/.claude/skills", exists: true, expectedCount: 1, counts: {}, extraUnmanaged: [] },
              codex: { dir: "~/.codex/skills", exists: true, expectedCount: 1, counts: {}, extraUnmanaged: [] },
            },
            collisions: [
              {
                group: "grilling",
                kind: "alias-collision",
                occurrences: [{ layer: "claude-synced", path: "~/.claude/skills/synced/grilling" }],
                recommendation: "Keep plugin grilling.",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/v1/actions/skills-sync")) {
        return new Response(
          JSON.stringify({
            dryRun: true,
            quarantineLegacy: true,
            quarantineBatch: null,
            manifestFile: null,
            sourceWarnings: [],
            actionCount: 1,
            quarantinedCount: 1,
            symlinkedCount: 1,
            actions: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    });

    vi.stubGlobal("fetch", mockFetch);
    render(<SkillsView />);

    await waitFor(() => {
      expect(screen.getByText("linear-issue")).toBeInTheDocument();
    });
    expect(screen.getByText("Keep plugin grilling.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Preview Sync/i }));
    await waitFor(() => {
      expect(screen.getByText(/Dry-run preview/i)).toBeInTheDocument();
    });

    vi.unstubAllGlobals();
  });
});
