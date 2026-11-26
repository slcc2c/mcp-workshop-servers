import { api } from "./api";
import type { CallToolResponse } from "../types";

function extractErrorMessage(resp: CallToolResponse): string {
  if (typeof resp.error === "string" && resp.error.trim()) {
    return resp.error;
  }
  if (resp.error && typeof resp.error === "object" && resp.error.message) {
    return String(resp.error.message);
  }
  const blockText = resp.contentBlocks?.find((b) => b.type === "text" && b.text)?.text;
  if (blockText && blockText.trim()) {
    return blockText;
  }
  return `Omnigent tool '${resp.tool}' failed`;
}

export function unwrapOmnigentResult<T>(resp: CallToolResponse): {
  data: T;
  traceId: string | null;
} {
  if (!resp.ok) {
    throw new Error(extractErrorMessage(resp));
  }
  const traceId = resp.traceId ?? null;

  if (resp.structuredContent !== undefined && resp.structuredContent !== null) {
    const sc = resp.structuredContent as Record<string, unknown>;
    if (
      typeof sc === "object" &&
      !Array.isArray(sc) &&
      Object.keys(sc).length === 1 &&
      "result" in sc
    ) {
      return { data: sc.result as T, traceId };
    }
    return { data: resp.structuredContent as T, traceId };
  }

  if (resp.result !== undefined && resp.result !== null) {
    if (typeof resp.result === "string") {
      try {
        return { data: JSON.parse(resp.result) as T, traceId };
      } catch {
        return { data: resp.result as unknown as T, traceId };
      }
    }
    return { data: resp.result as T, traceId };
  }

  const textBlock = resp.contentBlocks?.find((b) => b.type === "text" && b.text)?.text;
  if (textBlock !== undefined && textBlock !== null) {
    try {
      return { data: JSON.parse(textBlock) as T, traceId };
    } catch {
      return { data: textBlock as unknown as T, traceId };
    }
  }

  throw new Error(`Omnigent tool '${resp.tool}' returned no payload`);
}

export async function callOmnigent<T>(
  tool: string,
  args: Record<string, unknown> = {},
): Promise<{ data: T; traceId: string | null }> {
  const resp = await api.callTool("omnigent", tool, args);
  return unwrapOmnigentResult<T>(resp);
}
