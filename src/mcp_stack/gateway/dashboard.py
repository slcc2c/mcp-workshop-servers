"""Self-contained zero-build HTML/CSS/JS dashboard for the MCP Workshop Stack Gateway."""

from __future__ import annotations

import html


def render_dashboard_html(version: str) -> str:
    """Render the interactive Gateway Web Dashboard served at GET /ui."""
    safe_ver = html.escape(version)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MCP Workshop Stack Dashboard</title>
  <style>
    :root {{
      --bg: #0b1120;
      --panel: #111827;
      --panel-alt: #1f2937;
      --border: #334155;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --ok: #22c55e;
      --warn: #f59e0b;
      --err: #ef4444;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; }}
    .brand h1 {{ margin: 0; font-size: 1.1rem; font-weight: 600; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      background: var(--panel-alt);
      border: 1px solid var(--border);
    }}
    .pill.ok {{ color: var(--ok); border-color: rgba(34, 197, 94, 0.4); }}
    .pill.warn {{ color: var(--warn); border-color: rgba(245, 158, 11, 0.4); }}
    .pill.err {{ color: var(--err); border-color: rgba(239, 68, 68, 0.4); }}
    .auth-bar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    input, select {{
      background: var(--panel);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 0.85rem;
    }}
    button {{
      background: var(--panel-alt);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 0.85rem;
      cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); }}
    button.primary {{
      background: #0284c7;
      border-color: #0ea5e9;
      color: #fff;
      font-weight: 600;
    }}
    button:disabled {{ opacity: 0.55; cursor: not-allowed; }}
    main {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 20px 24px 48px;
      display: grid;
      gap: 18px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 0.95rem;
      color: var(--accent);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .muted {{ color: var(--muted); font-size: 0.84rem; }}
    code, pre {{ font-family: var(--mono); font-size: 0.8rem; }}
    pre {{
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      overflow-x: auto;
      max-height: 260px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
      align-items: center;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .kv {{ display: flex; justify-content: space-between; padding: 4px 0; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>MCP Workshop Stack Gateway</h1>
      <span class="pill">v{safe_ver}</span>
      <span id="overall-pill" class="pill warn">Checking...</span>
    </div>
    <div class="auth-bar">
      <input
        id="token-input"
        type="password"
        placeholder="Bearer token (sessionStorage only)"
        aria-label="Bearer token"
      />
      <button id="save-token-btn" class="primary" type="button">Connect</button>
      <button id="clear-token-btn" type="button">Clear</button>
      <button id="refresh-btn" type="button">Refresh All</button>
    </div>
  </header>

  <main>
    <section class="grid" id="health-grid">
      <div class="card">
        <h2>Gateway &amp; Dependencies</h2>
        <div id="ready-checks" class="muted">Loading /ready...</div>
      </div>
      <div class="card">
        <h2>Profiles &amp; Routes</h2>
        <div id="profiles-box" class="muted">Loading /health...</div>
      </div>
      <div class="card">
        <h2>Watchdog <span id="wd-pill" class="pill">--</span></h2>
        <div id="watchdog-box" class="muted">Connect token to load /api/v1/watchdog</div>
      </div>
    </section>

    <section class="card">
      <h2>Operational Actions (Bearer-Authenticated)</h2>
      <div class="actions">
        <button id="act-uc-btn" type="button">Refresh UC Tools</button>
        <button id="act-wd-btn" type="button">Run Watchdog Check (Dry Run)</button>
        <button id="act-eval-btn" type="button">Run Trace Eval (Last 20)</button>
        <span id="action-status" class="muted"></span>
      </div>
      <pre id="action-output" style="display:none; margin-top:10px;"></pre>
    </section>

    <section class="card">
      <h2>
        <span>Tool Browser <span id="tool-count" class="pill">0 tools</span></span>
        <span class="muted">Filter by server, profile, or keyword</span>
      </h2>
      <div class="toolbar">
        <select id="profile-filter"><option value="">All Profiles</option></select>
        <select id="server-filter"><option value="">All Servers</option></select>
        <input
          id="tool-search"
          type="search"
          placeholder="Search tools or descriptions..."
          style="min-width:260px;"
        />
      </div>
      <div id="tools-body" class="muted">
        Connect token (if auth enabled) to browse live tools...
      </div>
    </section>

    <section class="card">
      <h2>
        <span>Recent MLflow Traces &amp; Latest Eval</span>
        <a href="http://localhost:5002" target="_blank" rel="noopener">
          Open MLflow UI (:5002) &rarr;
        </a>
      </h2>
      <div id="eval-summary" class="muted" style="margin-bottom:10px;"></div>
      <div id="traces-body" class="muted">
        Connect token (if auth enabled) to load MLflow traces...
      </div>
    </section>
  </main>

  <script>
    const TOKEN_KEY = "mcp_gateway_token";
    const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (ch) => ({{
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }}[ch]));

    function getToken() {{
      return sessionStorage.getItem(TOKEN_KEY) || "";
    }}

    async function apiFetch(path, options = {{}}) {{
      const headers = new Headers(options.headers || {{}});
      const tok = getToken();
      if (tok) headers.set("Authorization", "Bearer " + tok);
      const res = await fetch(path, {{ ...options, headers }});
      const text = await res.text();
      let json = null;
      try {{ json = JSON.parse(text); }} catch {{}}
      if (!res.ok) {{
        const msg = json?.error?.message || ("HTTP " + res.status);
        const err = new Error(msg);
        err.status = res.status;
        throw err;
      }}
      return json;
    }}

    function badge(ok, okLabel = "healthy", failLabel = "degraded") {{
      const cls = ok ? "ok" : "err";
      return '<span class="pill ' + cls + '">' + esc(ok ? okLabel : failLabel) + "</span>";
    }}

    async function loadHealthAndReady() {{
      const [health, ready] = await Promise.all([apiFetch("/health"), apiFetch("/ready")]);
      const pill = document.getElementById("overall-pill");
      const isReady = ready.status === "ready";
      pill.textContent = ready.status.toUpperCase();
      pill.className = "pill " + (isReady ? "ok" : "warn");

      const checks = ready.checks || {{}};
      document.getElementById("ready-checks").innerHTML =
        Object.entries(checks).map(([k, v]) => {{
          const ok = Boolean(v.healthy ?? v.reachable);
          return '<div class="kv"><code>' + esc(k) + "</code>" +
            badge(ok, "ok", "down") + "</div>";
        }}).join("");

      const profiles = health.profiles || [];
      const profSel = document.getElementById("profile-filter");
      const prevProf = profSel.value;
      profSel.innerHTML = '<option value="">All Profiles</option>' + profiles.map(
        (p) => '<option value="' + esc(p.name) + '">' + esc(p.name) +
          " (" + esc(p.route) + ")</option>"
      ).join("");
      profSel.value = prevProf;

      const srvSel = document.getElementById("server-filter");
      const prevSrv = srvSel.value;
      const servers = health.servers || [];
      srvSel.innerHTML = '<option value="">All Servers</option>' + servers.map(
        (s) => '<option value="' + esc(s.slug) + '">' + esc(s.slug) + "</option>"
      ).join("");
      srvSel.value = prevSrv;

      document.getElementById("profiles-box").innerHTML = profiles.map((p) => (
        '<div class="kv"><code>' + esc(p.route) + '</code><span class="muted">' +
        esc((p.servers || []).length) + " servers</span></div>"
      )).join("") + '<div class="kv"><code>/mcp</code><span class="muted">' +
        esc(servers.length) + " total mounted</span></div>";
    }}

    async function loadWatchdog() {{
      const box = document.getElementById("watchdog-box");
      const wdPill = document.getElementById("wd-pill");
      try {{
        const data = await apiFetch("/api/v1/watchdog");
        const comps = data.components || {{}};
        const entries = Object.entries(comps);
        const allOk = entries.length > 0 && entries.every(([, v]) => Boolean(v.healthy));
        wdPill.textContent = entries.length ? (allOk ? "healthy" : "degraded") : "no state";
        wdPill.className = "pill " + (allOk ? "ok" : "warn");
        if (!entries.length) {{
          box.textContent = "No watchdog state file found yet.";
          return;
        }}
        box.innerHTML = entries.map(([name, info]) => (
          '<div class="kv"><code>' + esc(name) + "</code><span>" +
          badge(Boolean(info.healthy), "ok", "unhealthy") + "</span></div>"
        )).join("") + '<div class="muted" style="margin-top:6px;">Last check: ' +
          esc(data.lastRunAt || "n/a") + "</div>";
      }} catch (err) {{
        wdPill.textContent = err.status === 401 ? "locked" : "error";
        wdPill.className = "pill warn";
        box.textContent = err.status === 401
          ? "Enter Bearer token to view watchdog state."
          : err.message;
      }}
    }}

    async function loadTools() {{
      const body = document.getElementById("tools-body");
      const countEl = document.getElementById("tool-count");
      const profile = document.getElementById("profile-filter").value;
      const server = document.getElementById("server-filter").value;
      const q = document.getElementById("tool-search").value.trim();
      const params = new URLSearchParams();
      if (profile) params.set("profile", profile);
      if (server) params.set("server", server);
      if (q) params.set("q", q);
      const qs = params.toString() ? ("?" + params.toString()) : "";
      try {{
        const data = await apiFetch("/api/v1/tools" + qs);
        const tools = data.tools || [];
        countEl.textContent = tools.length + " tools";
        if (!tools.length) {{
          body.textContent = "No matching tools.";
          return;
        }}
        const rows = tools.slice(0, 150).map((t) => (
          "<tr><td><code>" + esc(t.name) + "</code></td>" +
          "<td><span class='pill'>" + esc(t.server) + "</span></td>" +
          "<td>" + esc(t.description || "") +
          "<details style='margin-top:4px;'><summary class='muted'>schema</summary><pre>" +
          esc(JSON.stringify(t.parameters || {{}}, null, 2)) + "</pre></details></td></tr>"
        )).join("");
        body.innerHTML =
          "<table><thead><tr><th>Tool</th><th>Server</th>" +
          "<th>Description &amp; Schema</th></tr></thead><tbody>" + rows + "</tbody></table>";
      }} catch (err) {{
        body.textContent = err.status === 401
          ? "Enter Bearer token to browse /api/v1/tools."
          : err.message;
      }}
    }}

    async function loadTraces() {{
      const body = document.getElementById("traces-body");
      const evalEl = document.getElementById("eval-summary");
      try {{
        const data = await apiFetch("/api/v1/traces?limit=15");
        if (!data.available) {{
          evalEl.textContent = "";
          body.textContent = "MLflow unavailable: " + (data.error || "unknown error");
          return;
        }}
        const latest = data.latestEvalRun;
        if (latest && latest.metrics) {{
          const pills = Object.entries(latest.metrics).map(
            ([k, v]) => '<span class="pill">' + esc(k) + "=" + esc(v) + "</span>"
          ).join(" ");
          evalEl.innerHTML =
            "<strong>Latest Eval Run</strong> <code>" +
            esc(latest.run_id) + "</code>: " + pills;
        }} else {{
          evalEl.textContent =
            "Experiment: " + (data.experiment || "n/a") + " (no eval metrics logged yet)";
        }}
        const traces = data.traces || [];
        if (!traces.length) {{
          body.textContent = "No recent MLflow traces in experiment.";
          return;
        }}
        const rows = traces.map((tr) => {{
          const st = tr.policyRefusal
            ? '<span class="pill warn">policy_refusal</span>'
            : badge(String(tr.state).includes("OK"), "OK", tr.state);
          return "<tr><td><code>" + esc(tr.traceId) + "</code></td>" +
            "<td><code>" + esc(tr.name || "") + "</code></td><td>" + st +
            "</td><td>" + esc(tr.durationMs ?? "-") + " ms</td></tr>";
        }}).join("");
        body.innerHTML =
          "<table><thead><tr><th>Trace ID</th><th>Span</th>" +
          "<th>Outcome</th><th>Duration</th></tr></thead><tbody>" + rows + "</tbody></table>";
      }} catch (err) {{
        evalEl.textContent = "";
        body.textContent = err.status === 401
          ? "Enter Bearer token to view /api/v1/traces."
          : err.message;
      }}
    }}

    async function runAction(path, payload, btn) {{
      const outEl = document.getElementById("action-output");
      const statusEl = document.getElementById("action-status");
      btn.disabled = true;
      statusEl.textContent = "Running " + path + "...";
      try {{
        const res = await apiFetch(path, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload || {{}}),
        }});
        statusEl.textContent = "Done.";
        outEl.style.display = "block";
        outEl.textContent = JSON.stringify(res, null, 2);
        await Promise.all([loadWatchdog(), loadTools(), loadTraces()]);
      }} catch (err) {{
        statusEl.textContent = "Failed: " + err.message;
        outEl.style.display = "block";
        outEl.textContent = err.message;
      }} finally {{
        btn.disabled = false;
      }}
    }}

    async function refreshAll() {{
      await loadHealthAndReady();
      await Promise.all([loadWatchdog(), loadTools(), loadTraces()]);
    }}

    document.getElementById("save-token-btn").addEventListener("click", () => {{
      const val = document.getElementById("token-input").value.trim();
      if (val) sessionStorage.setItem(TOKEN_KEY, val);
      refreshAll();
    }});
    document.getElementById("clear-token-btn").addEventListener("click", () => {{
      sessionStorage.removeItem(TOKEN_KEY);
      document.getElementById("token-input").value = "";
      refreshAll();
    }});
    document.getElementById("refresh-btn").addEventListener("click", refreshAll);
    document.getElementById("profile-filter").addEventListener("change", loadTools);
    document.getElementById("server-filter").addEventListener("change", loadTools);
    document.getElementById("tool-search").addEventListener("input", loadTools);
    document.getElementById("act-uc-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/refresh-uc", {{}}, e.target)
    );
    document.getElementById("act-wd-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/watchdog", {{ dry_run: true }}, e.target)
    );
    document.getElementById("act-eval-btn").addEventListener(
      "click", (e) => runAction("/api/v1/actions/eval", {{ limit: 20 }}, e.target)
    );

    if (getToken()) {{
      document.getElementById("token-input").value = getToken();
    }}
    refreshAll();
  </script>
</body>
</html>
"""
