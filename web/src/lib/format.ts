import type { SchemaProperty } from "../types";

export interface NormalizedTextSegment {
  kind: "markdown" | "json" | "text";
  text: string;
  parsedJson?: unknown;
}

/** Normalize literal escape sequences inside display strings only when safe, and keep hard returns. */
export function normalizeMultilineText(raw: string): string {
  return raw.replace(/\r\n/g, "\n");
}

/** Heuristic check for Markdown syntax so plain strings stay crisp pre-wrapped prose without losing line breaks. */
export function looksLikeMarkdown(text: string): boolean {
  return (
    /(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|>\s|```)/.test(text) ||
    /\[[^\]]+\]\([^)]+\)/.test(text) ||
    /\*\*[^*]+\*\*/.test(text) ||
    /(^|\n)\|.*\|/.test(text)
  );
}

export function classifyTextPayload(text: string): NormalizedTextSegment {
  const normalized = normalizeMultilineText(text);
  const trimmed = normalized.trim();
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed !== null && typeof parsed === "object") {
        return { kind: "json", text: normalized, parsedJson: parsed };
      }
    } catch {
      // Not valid JSON; fall back to Markdown or plain text.
    }
  }
  if (looksLikeMarkdown(normalized)) {
    return { kind: "markdown", text: normalized };
  }
  return { kind: "text", text: normalized };
}

export interface TemplateToken {
  type: "text" | "variable";
  value: string;
}

/** Split a Mustache/MLflow prompt template into text segments and `{{variable}}` tokens while preserving newlines. */
export function tokenizePromptTemplate(template: string): TemplateToken[] {
  const normalized = normalizeMultilineText(template);
  const re = /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g;
  const out: TemplateToken[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(normalized)) !== null) {
    if (match.index > cursor) {
      out.push({ type: "text", value: normalized.slice(cursor, match.index) });
    }
    out.push({ type: "variable", value: match[0] });
    cursor = match.index + match[0].length;
  }
  if (cursor < normalized.length) {
    out.push({ type: "text", value: normalized.slice(cursor) });
  }
  return out;
}

export function extractPromptVariables(template: string): string[] {
  const normalized = normalizeMultilineText(template);
  const re = /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g;
  const seen: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = re.exec(normalized)) !== null) {
    const key = match[1];
    if (!seen.includes(key)) {
      seen.push(key);
    }
  }
  return seen;
}

/** Substitute {{var}} placeholders identically to MLflowBridgedPrompt.render(). */
export function renderPromptTemplate(
  template: string,
  values: Record<string, string>,
): string {
  const normalized = normalizeMultilineText(template);
  return normalized.replace(/\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g, (full, key: string) => {
    const val = values[key];
    return val !== undefined && val !== "" ? val : full;
  });
}

export function extractSchemaDefaults(schema?: {
  properties?: Record<string, SchemaProperty>;
}): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  const props = schema?.properties || {};
  for (const [key, prop] of Object.entries(props)) {
    if (prop && prop.default !== undefined) {
      defaults[key] = prop.default;
    } else if (prop && Array.isArray(prop.enum) && prop.enum.length > 0) {
      defaults[key] = prop.enum[0];
    }
  }
  return defaults;
}

export function resolveSchemaType(prop?: SchemaProperty): string {
  if (!prop?.type) return "string";
  if (Array.isArray(prop.type)) {
    return prop.type.find((t) => t !== "null") || "string";
  }
  return prop.type;
}

export function firstLineSummary(text: string, maxLen = 120): string {
  const first = (text || "").trim().split("\n")[0]?.trim() || "";
  if (first.length <= maxLen) return first;
  return first.slice(0, maxLen - 1) + "…";
}

/** Format rich tool descriptions into clean separated paragraphs for readability. */
export function formatDescriptionParagraphs(text: string): string[] {
  const clean = normalizeMultilineText(text).trim();
  if (!clean) return [];
  const rawParas = clean
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (rawParas.length > 1) return rawParas;
  // Break long dense docstrings at common labeled sections like "Parameters:", "Data:", "Rules:"
  const broken = clean.replace(
    /\.\s+(?=(Parameters|Args|Arguments|Data|Rules|Returns|Example|Note|Usage):)/g,
    ".\n\n",
  );
  return broken
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function formatDuration(ms?: number | null): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms * 10) / 10} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}
