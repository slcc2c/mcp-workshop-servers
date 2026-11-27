/** Resolve the active gateway origin for shareable URLs and copied client configs. */
export function resolveGatewayBaseUrl(loc?: Pick<Location, "origin">): string {
  if (loc?.origin && loc.origin !== "null") {
    return loc.origin.replace(/\/+$/, "");
  }
  if (typeof window !== "undefined" && window.location?.origin && window.location.origin !== "null") {
    return window.location.origin.replace(/\/+$/, "");
  }
  return "http://127.0.0.1:8090";
}

/**
 * Resolve the MLflow UI URL cleanly for both local loopback (http://localhost:5002)
 * and remote Tailscale/Caddy subdomains (e.g. https://mcp.slcc2c.com -> https://mlflow.slcc2c.com).
 */
export function resolveMlflowUiUrl(
  configured?: string | null,
  loc?: Pick<Location, "protocol" | "hostname">,
): string {
  const activeLoc = loc ?? (typeof window !== "undefined" ? window.location : undefined);
  const cleanConfigured = (configured || "").trim().replace(/\/+$/, "");
  const isLocalConfigured =
    !cleanConfigured || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(cleanConfigured);

  if (activeLoc?.hostname && /^mcp\./i.test(activeLoc.hostname) && isLocalConfigured) {
    const proto = activeLoc.protocol === "https:" ? "https:" : "http:";
    const targetHost = activeLoc.hostname.replace(/^mcp\./i, "mlflow.");
    return `${proto}//${targetHost}`;
  }

  return cleanConfigured || "http://localhost:5002";
}

/**
 * Build a deep-link URL inside the MLflow UI for a specific experiment, runs/traces tab,
 * or individual run/trace rather than landing on the generic MLflow home view.
 */
export function buildMlflowExperimentUrl(
  mlflowUiBase: string,
  experimentId?: string | null,
  opts?: {
    section?: "traces" | "runs" | "evaluation-runs";
    runId?: string | null;
    traceId?: string | null;
  },
): string {
  const cleanBase = mlflowUiBase.trim().replace(/\/+$/, "") || "http://localhost:5002";
  const exp = (experimentId || "").trim();
  if (!exp) {
    return cleanBase;
  }
  const encExp = encodeURIComponent(exp);
  if (opts?.runId && opts.runId.trim()) {
    return `${cleanBase}/#/experiments/${encExp}/runs/${encodeURIComponent(opts.runId.trim())}`;
  }
  if (opts?.section === "traces" && opts?.traceId && opts.traceId.trim()) {
    return `${cleanBase}/#/experiments/${encExp}/traces?selectedTraceId=${encodeURIComponent(opts.traceId.trim())}`;
  }
  if (opts?.section) {
    return `${cleanBase}/#/experiments/${encExp}/${opts.section}`;
  }
  return `${cleanBase}/#/experiments/${encExp}`;
}
